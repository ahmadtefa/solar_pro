/**
 * Agent runner. Orchestrates the pi agent execution:
 * - Builds the prompt from issue title/body/memory/personality
 * - Selects the provider (with fallback)
 * - Invokes pi as a subprocess
 * - Captures output and extracts final message
 * - Tracks session file for resume
 */

import { existsSync, mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { IssueClawConfig, ProviderConfig } from "../config.ts";
import { getProviderChain } from "../config.ts";
import type { ParsedEvent } from "../github/events.ts";
import type { MemoryStore } from "../memory/store.ts";
import type { IssueMapping } from "../memory/store.ts";
import { buildProviderArgs } from "../providers/index.ts";
import { classifyProviderError, collectSecrets, redactSecrets } from "../utils/errors.ts";
import { log } from "../utils/log.ts";
import { errorMessage, isRetryableHttpError, retry, withTimeout } from "../utils/retry.ts";

/**
 * Retry budget for a single provider attempt when the failure is transient
 * (Gemini 429 / 503, network resets), overridable via env for slow free tiers.
 *
 * WHY: pi's own auto-retry only runs in interactive and RPC modes — in
 * `--print --mode json` (what CI uses) a single 429 or 503 aborts the run.
 * The observed failures were two 503 UNAVAILABLEs followed by a 429
 * `RESOURCE_EXHAUSTED`, all with zero retries.
 */
function maxTransientAttempts(): number {
  const raw = Number(process.env.ISSUECLAW_MAX_TRANSIENT_ATTEMPTS ?? "3");
  return Number.isFinite(raw) && raw >= 1 ? Math.min(raw, 8) : 3;
}

/**
 * Decide whether a failed provider attempt should be retried.
 *
 * Only transient classifications (429 per-minute throttling, 5xx/UNAVAILABLE
 * overloads, transport failures) are retried; rejected credentials (401/403)
 * and retired model ids (404) fail immediately because retrying cannot help.
 */
export function shouldRetryProviderFailure(
  error: unknown,
  attempt: number,
  maxAttempts: number,
): boolean {
  if (attempt >= maxAttempts) return false;
  return classifyProviderError(error).retryable;
}

/** Base delay between transient retries (ms), exponential, capped. */
function transientBackoffMs(attempt: number): number {
  const base = Number(process.env.ISSUECLAW_RETRY_BASE_MS ?? "10000");
  const safeBase = Number.isFinite(base) && base > 0 ? base : 10000;
  return Math.min(safeBase * 2 ** (attempt - 1), 90000);
}

/**
 * Resolve the pi binary path. Prefers:
 * 1. node_modules/.bin/pi (local install — always works)
 * 2. The full package via bunx (avoids conflict with `pi` npm package)
 * 3. Fallback to configured piCommand
 *
 * This is critical because `bunx pi` resolves to the wrong npm package
 * (pi-decimals) since the @earendil-works/pi-coding-agent was renamed.
 */
function resolvePiCommand(_configuredCmd: string): string[] {
  // Check for local install first
  const localBin = join(process.cwd(), "node_modules", ".bin", "pi");
  if (existsSync(localBin)) {
    log.debug("using local pi binary", { path: localBin });
    return [localBin];
  }
  // Use full package name to avoid bunx resolving to wrong `pi` package
  log.debug("using bunx with full package name");
  return ["bunx", "@earendil-works/pi-coding-agent"];
}

export interface AgentRunOptions {
  config: IssueClawConfig;
  memory: MemoryStore;
  event: ParsedEvent;
  existingMapping?: IssueMapping | null;
  /** Whether to actually invoke pi (false = mock). */
  executable?: boolean;
  /** Custom prompt override. */
  promptOverride?: string;
}

export interface AgentRunResult {
  success: boolean;
  response: string;
  sessionPath: string | null;
  providerUsed: ProviderConfig | null;
  error?: string;
  durationMs: number;
}

/**
 * Rough token estimate: ~4 chars per token for English text.
 * Used to decide if we need to truncate context to fit within provider limits.
 */
export function estimateTokens(text: string): number {
  return Math.ceil(text.length / 4);
}

/**
 * Strip GitHub issue template boilerplate.
 * Removes unfilled placeholder lines like "[Optional: ...]" and template instruction text.
 * Preserves real user content.
 */
function stripTemplateBoilerplate(body: string): string {
  if (!body) return "";
  let cleaned = body;

  // Remove lines that are pure placeholders (e.g. "[Optional: Any background info]")
  // These are unfilled template fields the user didn't edit
  cleaned = cleaned.replace(/^\s*\[[^\]]*\]\s*$/gm, "");

  // Remove template instruction lines (markdown headers that are just template structure)
  // Only remove if the NEXT non-empty line is a placeholder or empty
  const templateHeaders = [
    "What do you want the agent to do\\?",
    "Description the task in detail[^\\]]*",
    "Any background info[^\\]]*",
    "Success Criteria",
    "Optional:[^\\]]*",
    "Bug Description",
    "What's broken\\?",
    "Reproduction Steps",
    "Expected vs Actual",
    "Environment",
  ];
  for (const header of templateHeaders) {
    // Remove "## Header" line if followed by empty line or placeholder
    const re = new RegExp(`^##\\s+${header}\\s*\\n(?=\\s*(\\n|\\[|$))`, "gim");
    cleaned = cleaned.replace(re, "");
    // Also remove "[Header]" style
    const re2 = new RegExp(`^\\[${header}\\]\\s*\\n(?=\\s*(\\n|\\[|$))`, "gim");
    cleaned = cleaned.replace(re2, "");
  }

  // Remove "Read `.pi/BOOTSTRAP.md`..." hatch template line
  cleaned = cleaned.replace(/^Read `\.pi\/BOOTSTRAP\.md`.*$/gm, "");
  // Collapse multiple blank lines
  cleaned = cleaned.replace(/\n{3,}/g, "\n\n");
  return cleaned.trim();
}

/**
 * Build the prompt to send to the agent. Includes context from memory,
 * personality, and the issue/comment body.
 *
 * Token budget management:
 * - Groq free tier: 12,000 TPM (tokens per minute)
 * - We target a max of ~6,000 tokens for the prompt (leaves room for system + tools)
 * - If prompt exceeds budget, we truncate memory/personality/user context first
 */
export function buildPrompt(
  event: ParsedEvent,
  memory: MemoryStore,
  config: IssueClawConfig,
): string {
  const MAX_PROMPT_TOKENS = 6000; // Conservative for Groq free tier (12K TPM)
  const parts: string[] = [];

  // The actual user message FIRST (always included, highest priority)
  let userMessage: string;
  if (event.type === "issue_comment.created") {
    userMessage = event.body;
  } else if (event.type === "issues.opened") {
    userMessage = `${event.title}\n\n${event.body}`;
  } else {
    userMessage = `${event.title}\n\n${event.body}`;
  }

  // Strip issue template boilerplate (reduces token count significantly)
  userMessage = stripTemplateBoilerplate(userMessage);

  // Inject persistent context (only if non-default)
  const personality = memory.readPersonality();
  if (personality && !personality.includes("TBD") && !personality.includes("TBD —")) {
    parts.push(`## Your Identity\n\n${personality}`);
  }

  const user = memory.readUser();
  if (user && !user.includes("Unknown") && !user.includes("(none") && !user.includes("(unknown")) {
    parts.push(`## About Your Human\n\n${user}`);
  }

  // Recent memory — start with last 20 lines, truncate further if over budget
  const memoryContent = memory.readMemory();
  if (memoryContent) {
    const lines = memoryContent.split("\n").filter((l) => l.trim());
    // Skip if memory is still in default/uninitialized state
    const hasRealContent = lines.some(
      (l) => !l.includes("[uninitialized]") && !l.startsWith("#") && !l.startsWith(">"),
    );
    if (hasRealContent) {
      // Start with last 20 lines, will truncate later if needed
      const recentLines = lines.filter((l) => !l.startsWith("#") && !l.startsWith(">")).slice(-20);
      if (recentLines.length > 0) {
        parts.push(`## Recent Memory\n\n${recentLines.join("\n")}`);
      }
    }
  }

  parts.push(`## Current Request\n\n${userMessage}`);

  // Compact instructions (shorter than before)
  parts.push(
    "## Instructions\n\n" +
      "Read `AGENTS.md` for guidelines. Update `state/personality.md`, `state/user.md`, `state/memory.md` as needed. Changes auto-commit to git.",
  );

  // Hatch label triggers bootstrap
  if (event.labels.includes(config.github.hatchLabel)) {
    parts.push(
      `\n## ⚠️ HATCH TRIGGER\n\nThis issue has the \`${config.github.hatchLabel}\` label. Read \`.pi/BOOTSTRAP.md\` and follow the bootstrap flow to establish your identity. Update \`state/personality.md\` and \`state/user.md\` with what you learn.\n`,
    );
  }

  let prompt = parts.join("\n\n---\n\n");

  // Token budget enforcement: if prompt is too large, progressively strip context
  const tokenCount = estimateTokens(prompt);
  if (tokenCount > MAX_PROMPT_TOKENS) {
    log.warn("prompt exceeds token budget, truncating context", {
      tokens: tokenCount,
      max: MAX_PROMPT_TOKENS,
    });

    // Strategy: drop Recent Memory and About Your Human first, keep identity + request + instructions
    const requestPart = `## Current Request\n\n${userMessage}`;
    const instructionsPart =
      "## Instructions\n\nRead `AGENTS.md` for guidelines. Update state files as needed. Changes auto-commit.";
    const hatchPart = event.labels.includes(config.github.hatchLabel)
      ? "\n\n---\n\n## ⚠️ HATCH TRIGGER\n\nRead `.pi/BOOTSTRAP.md` and bootstrap your identity."
      : "";

    // Try with just personality + request + instructions
    const personalityPart =
      personality && !personality.includes("TBD") && !personality.includes("TBD —")
        ? `## Your Identity\n\n${personality}\n\n---\n\n`
        : "";

    prompt = `${personalityPart}${requestPart}\n\n---\n\n${instructionsPart}${hatchPart}`;

    // If STILL too large, truncate the user message itself
    if (estimateTokens(prompt) > MAX_PROMPT_TOKENS) {
      const maxUserChars = MAX_PROMPT_TOKENS * 4 - 500; // leave room for instructions
      const truncatedMsg = userMessage.slice(0, maxUserChars);
      prompt = `## Current Request\n\n${truncatedMsg}\n\n*(message truncated to fit token limit)*\n\n---\n\n${instructionsPart}${hatchPart}`;
      log.warn("user message truncated to fit token budget", {
        originalLength: userMessage.length,
        truncatedLength: truncatedMsg.length,
      });
    }
  }

  log.info("prompt built", {
    tokens: estimateTokens(prompt),
    chars: prompt.length,
    withinBudget: estimateTokens(prompt) <= MAX_PROMPT_TOKENS,
  });

  return prompt;
}

/**
 * Run the pi agent. Tries providers in fallback chain order.
 */
export async function runAgent(options: AgentRunOptions): Promise<AgentRunResult> {
  const startTime = Date.now();
  const { config, memory, event, existingMapping, executable = true, promptOverride } = options;

  const prompt = promptOverride ?? buildPrompt(event, memory, config);
  const providers = getProviderChain(config);

  log.info("starting agent run", {
    issue: event.issueNumber,
    promptLength: prompt.length,
    providers: providers.map((p) => `${p.type}/${p.model}`),
    providerCount: providers.length,
  });

  // Track ALL provider failures so we can show the user exactly what happened
  // with each provider — not just the last one.
  const failures: Array<{ provider: string; model: string; error: string; hasKey: boolean }> = [];
  let lastError: string | undefined;
  let lastSessionPath: string | null = null;
  // Never let a credential reach a log line or the issue comment.
  const secrets = collectSecrets(config.providers);

  for (const provider of providers) {
    const providerLabel = `${provider.type}/${provider.model}`;
    const hasKey = Boolean(
      provider.apiKey && provider.apiKey.length > 0 && !provider.apiKey.includes("${"),
    );

    // SKIP providers with no API key — don't waste time trying them.
    // This makes the fallback chain work: if Gemini key isn't set, skip to Cerebras, etc.
    if (!hasKey && executable) {
      log.info("skipping provider (no API key)", {
        provider: provider.type,
        model: provider.model,
        hint: `Set ${provider.type.toUpperCase()}_API_KEY secret to enable`,
      });
      failures.push({
        provider: provider.type,
        model: provider.model,
        error: `skipped — no API key set (needs ${provider.type.toUpperCase()}_API_KEY secret)`,
        hasKey: false,
      });
      continue;
    }

    const maxAttempts = executable ? maxTransientAttempts() : 1;
    // Keep the whole run (including retries) inside the configured agent
    // timeout so the job never gets killed before it can report the failure.
    const budgetMs = config.agent.timeoutMs;
    // When an attempt fails after reaching the provider, pi has already written
    // a session file. Resuming it keeps the tool calls/results so a retry does
    // not pay for the whole prompt again.
    let resume: IssueMapping | null | undefined = existingMapping;
    let attemptTimeoutMs = Math.min(config.agent.timeoutMs, budgetMs);

    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
      try {
        const result = await runWithProvider({
          provider,
          config,
          prompt,
          memory,
          existingMapping: resume,
          executable,
          timeoutMs: attemptTimeoutMs,
        });

        if (result.success) {
          log.info("agent run succeeded", {
            provider: providerLabel,
            attempt,
            durationMs: Date.now() - startTime,
          });
          return { ...result, durationMs: Date.now() - startTime };
        }

        lastError = result.error;
        if (result.sessionPath) {
          lastSessionPath = result.sessionPath;
          const now = new Date().toISOString();
          resume = resume
            ? { ...resume, sessionPath: result.sessionPath, updatedAt: now }
            : {
                issueNumber: event.issueNumber,
                sessionPath: result.sessionPath,
                createdAt: now,
                updatedAt: now,
                turnCount: 0,
              };
        }

        const info = classifyProviderError(result.error ?? "");
        if (!shouldRetryProviderFailure(result.error, attempt, maxAttempts)) {
          failures.push({
            provider: provider.type,
            model: provider.model,
            error: result.error ?? "unknown error",
            hasKey,
          });
          log.warn("provider failed, trying next", {
            provider: provider.type,
            model: provider.model,
            kind: info.kind,
            retryable: info.retryable,
            error: redactSecrets(result.error ?? "", secrets),
            hasKey,
          });
          break;
        }

        const waitMs = Math.min(info.retryAfterMs ?? transientBackoffMs(attempt), 90000);
        const remainingMs = budgetMs - (Date.now() - startTime) - waitMs;
        if (remainingMs < 30_000) {
          failures.push({
            provider: provider.type,
            model: provider.model,
            error: result.error ?? "unknown error",
            hasKey,
          });
          log.warn("provider still failing but the time budget is exhausted", {
            provider: providerLabel,
            kind: info.kind,
            attempt,
            remainingMs,
          });
          break;
        }
        log.warn("provider transient failure, retrying same provider", {
          provider: providerLabel,
          kind: info.kind,
          attempt,
          maxAttempts,
          waitMs,
          remainingMs,
          reason: redactSecrets(info.summary, secrets),
        });
        await sleep(waitMs);
        attemptTimeoutMs = Math.max(remainingMs, 30_000);
      } catch (err) {
        lastError = errorMessage(err);
        const info = classifyProviderError(err);
        if (!info.retryable || attempt >= maxAttempts) {
          failures.push({
            provider: provider.type,
            model: provider.model,
            error: lastError,
            hasKey,
          });
          log.warn("provider threw, trying next", {
            provider: provider.type,
            model: provider.model,
            kind: info.kind,
            error: redactSecrets(lastError, secrets),
            hasKey,
          });
          break;
        }
        const waitMs = Math.min(info.retryAfterMs ?? transientBackoffMs(attempt), 90000);
        const remainingMs = budgetMs - (Date.now() - startTime) - waitMs;
        if (remainingMs < 30_000) break;
        log.warn("provider threw a transient error, retrying", {
          provider: providerLabel,
          kind: info.kind,
          attempt,
          waitMs,
          remainingMs,
          error: redactSecrets(lastError, secrets),
        });
        await sleep(waitMs);
        attemptTimeoutMs = Math.max(remainingMs, 30_000);
      }
    }
  }

  // Build a detailed error showing ALL provider attempts
  const failureSummary = failures
    .map((f, i) => {
      const keyStatus = f.hasKey ? "✓ key set" : "✗ no key";
      const errShort = f.error.length > 200 ? `${f.error.slice(0, 200)}...` : f.error;
      return `${i + 1}. \`${f.provider}/${f.model}\` (${keyStatus}): ${errShort}`;
    })
    .join("\n");

  const detailedError = `All ${providers.length} provider(s) failed:\n\n${failureSummary}`;

  return {
    success: false,
    response: "",
    sessionPath: lastSessionPath,
    providerUsed: null,
    error: detailedError,
    durationMs: Date.now() - startTime,
  };
}

interface ProviderRunOptions {
  provider: ProviderConfig;
  config: IssueClawConfig;
  prompt: string;
  memory: MemoryStore;
  existingMapping?: IssueMapping | null;
  executable: boolean;
  /** Timeout for this attempt (ms). Defaults to config.agent.timeoutMs. */
  timeoutMs?: number;
}

async function runWithProvider(opts: ProviderRunOptions): Promise<AgentRunResult> {
  const { provider, config, prompt, memory, existingMapping, executable } = opts;
  const attemptTimeoutMs = Math.max(opts.timeoutMs ?? config.agent.timeoutMs, 30_000);

  // Every error path below is scrubbed before it can reach a log or the issue
  // comment — provider errors sometimes echo the credential back.
  const secrets = collectSecrets(config.providers);
  const scrub = (text: string | undefined): string | undefined =>
    text === undefined ? undefined : redactSecrets(text, secrets);

  // Validate provider config (skip in mock mode for easier local testing)
  if (executable) {
    const validation = validateProvider(provider);
    if (validation) {
      return failure(redactSecrets(validation, secrets));
    }
  }

  // Build pi args (skip validation in mock mode)
  let providerArgs: string[] = [];
  let providerEnv: Record<string, string | undefined> = {};
  if (executable) {
    const built = buildProviderArgs(provider);
    providerArgs = built.args;
    providerEnv = built.env;
  } else {
    // Mock mode: build args without validation
    providerArgs = ["--provider", provider.type, "--model", provider.model];
    providerEnv = {};
  }

  // Resolve pi binary (avoids bunx resolving to wrong `pi` package)
  const piBin = resolvePiCommand(config.agent.piCommand);

  const piArgs = [
    ...piBin,
    "--mode",
    "json",
    "--session-dir",
    memory.getSessionsDir(),
    "--approve", // Bypass interactive trust prompt (CI/non-interactive)
    "-p",
    prompt,
    ...providerArgs,
  ];

  if (config.agent.tools?.length) {
    piArgs.push("--tools", config.agent.tools.join(","));
  }
  if (config.agent.excludeTools?.length) {
    piArgs.push("--exclude-tools", config.agent.excludeTools.join(","));
  }
  // Load pi extensions from .pi/extensions/*.ts (only files that exist)
  if (config.agent.extensions) {
    const extDir = join(process.cwd(), ".pi", "extensions");
    if (existsSync(extDir)) {
      try {
        const { readdirSync } = await import("node:fs");
        const exts = readdirSync(extDir).filter((f) => f.endsWith(".ts") || f.endsWith(".js"));
        for (const ext of exts) {
          const extPath = join(extDir, ext);
          piArgs.push("--extension", extPath);
          log.debug("loaded extension", { path: extPath });
        }
      } catch (err) {
        log.warn("failed to read extensions dir", { dir: extDir, error: errorMessage(err) });
      }
    }
  }
  // Thinking level comes from the provider config, already in providerArgs
  if (existingMapping?.sessionPath && existsSync(existingMapping.sessionPath)) {
    piArgs.push("--session", existingMapping.sessionPath);
    log.debug("resuming session", { session: existingMapping.sessionPath });
  }

  log.debug("invoking pi", {
    cmd: piArgs.join(" "),
    envKeys: Object.keys(providerEnv),
  });

  if (!executable) {
    return {
      success: true,
      response: `[MOCK MODE] Would have invoked: ${piArgs.join(" ")}`,
      sessionPath: null,
      providerUsed: provider,
      durationMs: 0,
    };
  }

  // Run pi with timeout
  try {
    const result = await withTimeout(
      invokePi(piArgs, providerEnv, attemptTimeoutMs),
      attemptTimeoutMs,
    );

    // ALWAYS find the latest session file — even on failure, pi creates one
    // and we want to save the mapping so the user can debug / resume later.
    const sessionPath = memory.getLatestSession();
    if (!sessionPath) {
      log.warn("no session file found after agent run");
    }

    if (!result.success) {
      return {
        success: false,
        response: result.response,
        sessionPath, // preserve session path even on failure
        providerUsed: provider,
        error: scrub(result.error),
        durationMs: 0,
      };
    }

    return {
      success: true,
      response: result.response,
      sessionPath,
      providerUsed: provider,
      durationMs: 0,
    };
  } catch (err) {
    // Even on exception, try to find the session file
    const sessionPath = memory.getLatestSession();
    return {
      success: false,
      response: "",
      sessionPath,
      providerUsed: provider,
      error: scrub(errorMessage(err)),
      durationMs: 0,
    };
  }
}

interface PiResult {
  success: boolean;
  response: string;
  error?: string;
}

async function invokePi(
  args: string[],
  env: Record<string, string | undefined>,
  _timeoutMs: number,
): Promise<PiResult> {
  // Merge provider env over the ambient env. An explicit `undefined` value
  // UNSETS the variable (spreading alone would leave the ambient value in
  // place, which is how a stray GOOGLE_API_KEY could shadow GEMINI_API_KEY).
  const mergedEnv: Record<string, string> = {};
  for (const [key, value] of Object.entries(process.env)) {
    if (value !== undefined) mergedEnv[key] = value;
  }
  for (const [key, value] of Object.entries(env)) {
    if (value === undefined) delete mergedEnv[key];
    else mergedEnv[key] = value;
  }

  // pi resolves credentials from ~/.pi/agent/auth.json BEFORE falling back to
  // the environment (see pi-ai's envApiKeyAuth). On a runner with a persisted
  // home directory a stale stored key would silently shadow the repository
  // secret — the classic "the key works in AI Studio but not in CI" symptom.
  // In CI, point pi at a throwaway agent dir so the injected secret always wins.
  if (
    !mergedEnv.PI_CODING_AGENT_DIR &&
    (process.env.CI === "true" || process.env.GITHUB_ACTIONS === "true")
  ) {
    try {
      mergedEnv.PI_CODING_AGENT_DIR = mkdtempSync(join(tmpdir(), "issueclaw-pi-agent-"));
      log.debug("using ephemeral pi agent dir", { dir: mergedEnv.PI_CODING_AGENT_DIR });
    } catch (err) {
      log.warn("could not create ephemeral pi agent dir", { error: errorMessage(err) });
    }
  }

  // The prompt is the last argument (passed to -p flag).
  // Pi accepts it as a direct string argument.
  // We pass args as-is to avoid shell escaping issues (Bun.spawn doesn't use a shell).

  const proc = Bun.spawn(args, {
    stdout: "pipe",
    stderr: "pipe",
    stdin: "ignore", // Don't wait for stdin (non-interactive mode)
    env: mergedEnv,
  });

  // Tee output to a log file for debugging
  const rawLogPath = `/tmp/agent-raw-${process.pid}.jsonl`;
  const tee = Bun.spawn(["tee", rawLogPath], {
    stdin: proc.stdout,
    stdout: "pipe",
  });

  const [_ignored, stderr] = await Promise.all([
    new Response(tee.stdout).text(),
    new Response(proc.stderr).text(),
  ]);
  const exitCode = await proc.exited;

  if (exitCode !== 0) {
    return {
      success: false,
      response: "",
      error: `pi exited with code ${exitCode}: ${stderr.slice(0, 500)}`,
    };
  }

  // Extract final ASSISTANT message text from JSONL
  const response = extractFinalMessage(rawLogPath);

  // If no assistant response, check for an error message from pi
  if (response.length === 0) {
    const errMsg = extractErrorMessage(rawLogPath);
    if (errMsg) {
      log.warn("pi returned an error", { error: errMsg });
      return {
        success: false,
        response: "",
        error: `LLM API error: ${errMsg}`,
      };
    }
    return {
      success: false,
      response: "",
      error: "no assistant response in pi output (the LLM call may have failed silently)",
    };
  }

  return {
    success: true,
    response,
  };
}

/**
 * Extract the final ASSISTANT message text from pi's JSONL output.
 *
 * CRITICAL: Only returns assistant messages, never user messages.
 * When the LLM call fails, pi still logs the user's message as a message_end
 * event. If we don't filter by role, we'd return the user's prompt as the
 * "response" — which would post the prompt as a comment on the issue.
 */
export function extractFinalMessage(jsonPath: string): string {
  try {
    const content = readFileSync(jsonPath, "utf-8");
    const lines = content.trim().split("\n");
    // Find the last ASSISTANT message_end event with actual text content
    for (let i = lines.length - 1; i >= 0; i--) {
      const line = lines[i];
      if (!line.trim()) continue;
      try {
        const evt = JSON.parse(line);
        // Only accept assistant messages — NEVER user messages
        if (
          evt.type === "message_end" &&
          evt.message?.role === "assistant" &&
          evt.message?.content
        ) {
          const texts = evt.message.content
            .filter((c: { type: string }) => c.type === "text")
            .map((c: { text: string }) => c.text);
          if (texts.length > 0) {
            return texts.join("");
          }
        }
      } catch {
        // skip malformed lines
      }
    }
    return "";
  } catch (err) {
    log.warn("failed to extract final message", { error: errorMessage(err) });
    return "";
  }
}

/**
 * Extract any error message from pi's JSONL output.
 * Looks for message_end events with stopReason "error" or errorMessage field.
 */
export function extractErrorMessage(jsonPath: string): string | null {
  try {
    const content = readFileSync(jsonPath, "utf-8");
    const lines = content.trim().split("\n");
    for (let i = lines.length - 1; i >= 0; i--) {
      const line = lines[i];
      if (!line.trim()) continue;
      try {
        const evt = JSON.parse(line);
        if (evt.type === "message_end" && evt.message?.errorMessage) {
          return String(evt.message.errorMessage);
        }
        if (evt.type === "turn_end" && evt.message?.errorMessage) {
          return String(evt.message.errorMessage);
        }
        if (evt.type === "error") {
          return String(evt.message ?? evt.error ?? "unknown error");
        }
      } catch {
        // skip
      }
    }
    return null;
  } catch {
    return null;
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function failure(error: string): AgentRunResult {
  return {
    success: false,
    response: "",
    sessionPath: null,
    providerUsed: null,
    error,
    durationMs: 0,
  };
}

function validateProvider(provider: ProviderConfig): string | null {
  try {
    buildProviderArgs(provider);
    return null;
  } catch (err) {
    return errorMessage(err);
  }
}

// re-export for testing
export { retry, isRetryableHttpError };
