#!/usr/bin/env bun
/**
 * Main agent lifecycle. Runs after preinstall.
 *
 * Pipeline:
 * 1. Parse event (already validated by preinstall)
 * 2. Initialize memory store
 * 3. Configure git
 * 4. Build prompt
 * 5. Run agent (with provider fallback)
 * 6. Save session mapping
 * 7. Commit & push state changes
 * 8. Comment on issue
 * 9. Cleanup reaction (finally)
 */

import { existsSync, readFileSync } from "node:fs";
import { type AgentRunResult, runAgent } from "../agent/runner.ts";
import { type IssueClawConfig, loadConfig } from "../config.ts";
import { GithubClient } from "../github/client.ts";
import { parseEvent } from "../github/events.ts";
import { MemoryStore } from "../memory/store.ts";
import type { IssueMapping } from "../memory/store.ts";
import {
  type ProviderErrorInfo,
  classifyProviderError,
  collectSecrets,
  redactSecrets,
} from "../utils/errors.ts";
import { GitClient } from "../utils/git.ts";
import { log } from "../utils/log.ts";
import { detectReadOnlyRequest, planCommitScope } from "../utils/policy.ts";
import { preflight } from "./preflight.ts";

/**
 * Build a helpful error message to post on the issue when the agent fails.
 * Includes the error, provider used, and actionable troubleshooting steps.
 */
/**
 * Rows extracted from the aggregated per-provider failure summary produced by
 * the runner/chat layer, e.g.
 *   `1. \`gemini/gemini-2.5-flash-lite\` (✓ key set): LLM API error: {"error":…}`
 *   `2. \`groq/llama-3.3-70b-versatile\` (✗ no key): skipped — no API key configured`
 */
interface ProviderFailureRow {
  label: string;
  model: string;
  hadKey: boolean;
  skipped: boolean;
  error: string;
}

function parseProviderFailures(errMsg: string): ProviderFailureRow[] {
  const rows: ProviderFailureRow[] = [];
  const lineRe = /^\s*\d+\.\s+`([^`]+)`\s*\(([^)]*)\):\s*(.*)$/gm;
  for (const match of errMsg.matchAll(lineRe)) {
    const label = match[1] ?? "";
    const status = (match[2] ?? "").toLowerCase();
    const body = match[3] ?? "";
    rows.push({
      label,
      model: label.includes("/") ? label.slice(label.indexOf("/") + 1) : label,
      hadKey: status.includes("key set"),
      skipped: /skip|no key/i.test(status) || /^skipped/i.test(body.trim()),
      error: body.trim(),
    });
  }
  return rows;
}

function buildErrorMessage(
  result: AgentRunResult,
  _provider: string,
  errMsg: string,
  config: IssueClawConfig,
): string {
  // Redact first: this text is posted as a public GitHub comment.
  const safeErrMsg = redactSecrets(errMsg, collectSecrets(config.providers));

  // Split the aggregated summary into per-provider rows.
  const rows = parseProviderFailures(safeErrMsg);
  const attempted = rows.filter((r) => !r.skipped);
  const allProvidersNoKey = rows.length > 0 && attempted.length === 0;

  // Classify the error from the providers we ACTUALLY called.
  //
  // The previous implementation regex-matched the whole summary for /API key/i,
  // which always matched the "no API key set (needs GROQ_API_KEY)" lines of the
  // unconfigured fallbacks. Every failure was therefore reported as
  // "Authentication error (403/401)" — including retired-model 404s and 429s.
  const infos: Array<{ row: ProviderFailureRow; info: ProviderErrorInfo }> = attempted.map((r) => ({
    row: r,
    info: classifyProviderError(r.error),
  }));

  const isAuthError = !allProvidersNoKey && infos.some((i) => i.info.kind === "auth");
  const isModelGone = !allProvidersNoKey && infos.some((i) => i.info.kind === "model_not_found");
  const isRateLimit = infos.some(
    (i) =>
      i.info.kind === "rate_limit" ||
      i.info.kind === "overloaded" ||
      i.info.kind === "quota_exhausted",
  );
  const isQuotaExhausted = infos.some((i) => i.info.kind === "quota_exhausted");
  const isTokenLimit = infos.some((i) => i.info.kind === "request_too_large");
  const isNetwork = infos.some((i) => i.info.kind === "network");
  const isMissingKey = attempted.length === 0 && !allProvidersNoKey;
  const hasAnyKeySet = attempted.length > 0;

  let hint = "";

  if (allProvidersNoKey) {
    hint = `**No API keys found in any provider.**

You need to set at least ONE API key as a GitHub secret:

1. Go to **Settings → Secrets and variables → Actions**
2. Add one of these secrets (pick a provider):
   - \`GEMINI_API_KEY\` — get free at https://aistudio.google.com/app/apikey (RECOMMENDED, 1M TPM)
   - \`CEREBRAS_API_KEY\` — get free at https://inference.cerebras.ai/
   - \`OPENROUTER_API_KEY\` — get free at https://openrouter.ai/keys
   - \`GROQ_API_KEY\` — get free at https://console.groq.com/keys
   - \`ANTHROPIC_API_KEY\` — paid
   - \`OPENAI_API_KEY\` — paid

3. The secret name MUST match exactly (case-sensitive)
4. Push a new commit or re-run the workflow

**Current config providers:**
${config.providers.map((p, i) => `${i + 1}. \`${p.type}/${p.model}\` — needs \`${p.type.toUpperCase()}_API_KEY\` (currently ${p.apiKey?.includes("${") ? "❌ NOT SET" : "✓ set"})`).join("\n")}`;
  } else if (isMissingKey && !hasAnyKeySet) {
    hint = `**API key missing for the configured provider.**

The error shows a provider requires an API key that isn't set. Check:

1. **Which provider is your default?** Look at \`issueclaw.config.json\` — the one with \`"default": true\`
2. **Is the matching secret set?** Go to **Settings → Secrets and variables → Actions**
   - Provider type → Required secret name:
   - \`gemini\` → \`GEMINI_API_KEY\`
   - \`cerebras\` → \`CEREBRAS_API_KEY\`
   - \`openrouter\` → \`OPENROUTER_API_KEY\`
   - \`groq\` → \`GROQ_API_KEY\`
   - \`anthropic\` → \`ANTHROPIC_API_KEY\`
   - \`openai\` → \`OPENAI_API_KEY\`
3. **Secret names are case-sensitive** — must be exactly as shown above

**Get a free key:**
- Gemini (recommended, 1M TPM): https://aistudio.google.com/app/apikey
- Cerebras: https://inference.cerebras.ai/
- OpenRouter: https://openrouter.ai/keys`;
  } else if (isTokenLimit) {
    hint = `**Token limit exceeded (413 error).**

The prompt (including system prompt, tools, and context) exceeded the provider's tokens-per-minute (TPM) limit.

**How to fix:**
1. **Use Gemini** — it has 1,000,000 TPM (vs Groq's 12,000). Set \`GEMINI_API_KEY\` and make it default.
2. **Wait and retry** — TPM limits reset every 60 seconds
3. **Add multiple fallback providers** in \`issueclaw.config.json\``;
  } else if (isRateLimit) {
    hint = `**${isQuotaExhausted ? "Quota exhausted (429)" : "Rate limited or provider overloaded (429/503)"}**

IssueClaw already retries transient 429/503 responses with exponential backoff and honours
the provider's own \`Please retry in Ns\` hint, so this means the limit was still exceeded
after the retry budget was spent.

**How to fix:**
1. **Wait and re-run** — per-minute limits reset within 60s; daily quotas reset at midnight Pacific
2. **Add fallback providers/models** in \`issueclaw.config.json\` — the chain tries the next entry
3. **Check the provider's quota dashboard**:
   - Gemini: https://ai.google.dev/gemini-api/docs/rate-limits (free tier is 5–15 RPM per model)
   - Groq: https://console.groq.com/settings/limits
   - OpenRouter: https://openrouter.ai/activity
4. **Gemini free tier tip**: switch the default model to a Flash-Lite id
   (\`gemini-3.5-flash-lite\`) — it has the highest free RPM/RPD ceiling`;
  } else if (isModelGone) {
    const gone = infos.filter((i) => i.info.kind === "model_not_found");
    hint = `**The configured model no longer exists (HTTP 404).**

This is a configuration problem, not an authentication problem — the API key was accepted.

${gone
  .map(
    (g) =>
      `- \`${g.row.label}\`${g.info.model ? ` — model \`${g.info.model}\` was retired` : ""}${
        g.info.suggestedModel ? `. The API suggests \`${g.info.suggestedModel}\` instead.` : "."
      }`,
  )
  .join("\n")}

**How to fix:**
1. Update the \`model\` for the \`gemini\` provider in \`issueclaw.config.json\`
   (current free-tier Flash-Lite ids: \`gemini-3.5-flash-lite\`, \`gemini-flash-lite-latest\`)
2. Or set the \`ISSUECLAW_MODEL\` repository variable
3. \`issueclaw doctor\` flags retired Gemini ids before a run starts`;
  } else if (isAuthError) {
    hint = `**Authentication error (401/403).**

The provider rejected the credential for a provider that was actually attempted.

**How to fix:**
1. **Verify the secret matches the provider** — \`GEMINI_API_KEY\` for \`gemini\`, etc.
   (Secret names are case-sensitive; empty secrets are treated as "not set".)
2. **Modern Gemini keys must be sent as the \`x-goog-api-key\` header.** AI Studio now
   issues \`AQ.\`-prefixed "auth" keys; legacy \`AIzaSy…\` keys are being rejected.
   IssueClaw/pi already use the header — if you forked the provider code, check that
   the key is not passed as a \`?key=\` query parameter.
3. **Remove stale stored credentials** — pi prefers \`~/.pi/agent/auth.json\` over the
   environment. CI points pi at a clean agent dir, but a self-hosted runner with a
   persisted home directory can shadow the secret.
4. **Regenerate the key** if it was revoked, then update the repository secret`;
  } else if (isNetwork) {
    hint = `**Network error.**

This is usually transient. Try again in a moment.`;
  } else {
    hint = `**Unexpected error.**

Check the workflow logs in the Actions tab for the full error details.`;
  }

  const providers = config.providers
    .map((p, i) => `${i + 1}. \`${p.type}/${p.model}\`${p.default ? " (default)" : ""}`)
    .join("\n");

  // Precise per-provider diagnosis: which provider was actually called, what
  // the provider said, and whether the failure is retryable.
  const diagnosis =
    infos.length > 0
      ? infos
          .map(
            (i) =>
              `- \`${i.row.label}\` → **${i.info.summary}** (${i.info.kind}, ${
                i.info.retryable ? "retryable" : "not retryable"
              })`,
          )
          .join("\n")
      : "- No provider with a credential was reachable.";

  // The error message from the runner now contains ALL provider failures
  // Show it in a collapsible details section
  const errDisplay =
    safeErrMsg.length > 3000
      ? `${safeErrMsg.slice(0, 3000)}\n\n...(truncated, see full logs in Actions tab)`
      : safeErrMsg;

  return `## ⚠️ Agent Error

The agent failed to produce a response after trying all configured providers.

${hint}

---

<details>
<summary>🔍 Provider attempts (click to expand)</summary>

${errDisplay}

</details>

---

<details>
<summary>📋 Configuration</summary>

**Diagnosis (classified from the providers that were actually called):**
${diagnosis}

**Provider fallback chain:**
${providers}

**Config file**: \`issueclaw.config.json\`
**Tools**: ${config.agent.tools?.length ?? 0} enabled
**Session file**: \`${result.sessionPath ?? "none"}\`
**Duration**: ${result.durationMs}ms

</details>

---

**To debug further:**
1. Check the workflow run logs in the **Actions** tab (look for "provider failed, trying next")
2. Download the \`issueclaw-session-*\` artifact for full JSONL output
3. Run \`bun run src/cli.ts doctor\` locally

_If this keeps happening, [open an issue](https://github.com/maruf009sultan/issueclaw/issues/new?labels=bug) with the diagnostics above._`;
}

async function main(config: IssueClawConfig): Promise<void> {
  const startTime = Date.now();
  log.info("main: starting agent lifecycle");

  // Parse event
  const event = parseEvent();
  log.info("main: parsed event", { type: event.type, issue: event.issueNumber });

  // Initialize memory
  const memory = new MemoryStore(config.memory);
  memory.init();
  memory.appendAudit("agent_run_start", { issue: event.issueNumber, type: event.type });

  // Configure git
  const git = new GitClient({});
  await git.configure();

  // Preflight: probe the configured provider/model so a bad credential or a
  // retired Gemini model is reported as itself, before any agent work happens.
  // Advisory only — the run continues regardless (the provider chain may still
  // succeed), and it is skipped in offline/dry-run mode.
  if (!config.runtime.offline) {
    try {
      const check = await preflight(config);
      if (!check.ok) {
        log.warn("preflight reported configuration problems", {
          checked: check.checked.map((c) => `${c.provider}/${c.model}: ${c.status}`),
        });
      }
    } catch (err) {
      log.warn("preflight could not run", {
        error: err instanceof Error ? err.message : String(err),
      });
    }
  }

  // Read existing mapping for resume
  const existingMapping = memory.getMapping(event.issueNumber);
  let _mode = "new";
  if (existingMapping?.sessionPath && existsSync(existingMapping.sessionPath)) {
    _mode = "resume";
    log.info("main: resuming session", { session: existingMapping.sessionPath });
  }

  // Read reaction state
  const reactionState = existsSync("/tmp/reaction-state.json")
    ? JSON.parse(readFileSync("/tmp/reaction-state.json", "utf-8"))
    : null;

  try {
    // Detect mode based on issue labels:
    //   "agent" or "task" label → full agent mode (pi + tools, ~120K tokens)
    //   "hatch" label           → agent mode + bootstrap identity flow
    //   default (no label)      → simple chat mode (~500 tokens, works with Groq)
    //
    // RATIONALE: Groq's free tier has only 12K TPM, but agent mode needs ~120K
    // tokens (pi's system prompt + tool definitions). So agent mode ALWAYS fails
    // on Groq with 413. Making chat the default means Groq works for the common
    // case (quick questions). Use the "agent" label only when you need file
    // editing / tool use, and ideally with Gemini (1M TPM) as the provider.
    const isAgentMode =
      event.labels.includes("agent") ||
      event.labels.includes("task") ||
      event.labels.includes(config.github.hatchLabel);
    const isHatchMode = event.labels.includes(config.github.hatchLabel);
    const mode = isHatchMode ? "hatch" : isAgentMode ? "agent" : "chat";

    log.info("main: running in mode", { mode, issue: event.issueNumber, labels: event.labels });

    // Result type — both runAgent and runSimpleChat produce compatible shapes
    let result: AgentRunResult;

    if (mode === "chat") {
      // Simple chat: direct LLM call, no agent, no tools — saves ~99% of API tokens
      // This is the DEFAULT mode — works with Groq's 12K TPM free tier.
      const { runSimpleChat } = await import("../agent/simple-chat.ts");
      const chatResult = await runSimpleChat({
        config,
        memory,
        event,
        existingMapping,
      });
      result = {
        success: chatResult.success,
        response: chatResult.response,
        sessionPath: null, // simple chat doesn't create a session file
        providerUsed: chatResult.providerUsed,
        error: chatResult.error,
        durationMs: chatResult.durationMs,
      };
      log.info("main: simple chat finished", {
        success: chatResult.success,
        durationMs: chatResult.durationMs,
        tokensUsed: chatResult.tokensUsed,
        provider: chatResult.providerUsed?.type,
      });
      memory.appendAudit("simple_chat_complete", {
        issue: event.issueNumber,
        success: chatResult.success,
        durationMs: chatResult.durationMs,
        provider: chatResult.providerUsed?.type,
        tokensUsed: chatResult.tokensUsed,
        responseLength: chatResult.response.length,
      });
    } else {
      // Full agent mode: pi agent with tools, file editing, session management
      // Needs ~120K tokens — requires Gemini (1M TPM) or Cerebras (60K TPM).
      // Will FAIL on Groq (12K TPM) with 413 error.
      result = await runAgent({
        config,
        memory,
        event,
        existingMapping,
        executable: !config.runtime.offline,
      });

      log.info("main: agent finished", {
        success: result.success,
        durationMs: result.durationMs,
        responseLength: result.response.length,
        provider: result.providerUsed
          ? `${result.providerUsed.type}/${result.providerUsed.model}`
          : null,
      });

      memory.appendAudit("agent_run_complete", {
        issue: event.issueNumber,
        success: result.success,
        durationMs: result.durationMs,
        provider: result.providerUsed?.type,
        responseLength: result.response.length,
      });
    }

    // Save session mapping (only for agent mode — chat mode has no session file)
    if (result.sessionPath) {
      const now = new Date().toISOString();
      const mapping: IssueMapping = {
        issueNumber: event.issueNumber,
        sessionPath: result.sessionPath,
        createdAt: existingMapping?.createdAt ?? now,
        updatedAt: now,
        turnCount: (existingMapping?.turnCount ?? 0) + 1,
      };
      memory.saveMapping(mapping);
      log.info("main: mapping saved", { issue: event.issueNumber, session: result.sessionPath });
    }

    // Commit & push (unless dry-run)
    if (!config.runtime.dryRun) {
      // Honour an explicit read-only request: stage only IssueClaw's own state
      // so the run cannot modify application code, whatever the model did.
      const readOnly = detectReadOnlyRequest(`${event.title}\n${event.body}`);
      const scope = planCommitScope(await git.status(), readOnly);
      if (scope.restricted) {
        if (scope.skipped.length > 0) {
          log.warn("read-only request: changes outside state/ will not be committed", {
            count: scope.skipped.length,
            files: scope.skipped.slice(0, 20),
          });
        } else {
          log.info("read-only request: no changes outside state/ detected");
        }
      }
      await git.add(scope.paths);
      const committed = await git.commit(
        `issueclaw: work on issue #${event.issueNumber} (${mode})`,
      );
      if (committed) {
        const branch = await git.currentBranch();
        await git.push("origin", branch);
        log.info("main: pushed changes", { branch });
      } else {
        log.info("main: no changes to commit");
      }
    } else {
      log.info("main: dry-run mode, skipping commit/push");
    }

    // Comment on issue (unless dry-run)
    if (!config.runtime.dryRun) {
      const gh = new GithubClient();
      let commentBody: string;

      if (result.success && result.response) {
        commentBody = result.response;
        // Truncate if too long, with notice
        if (commentBody.length > config.github.maxCommentLength) {
          const truncated = commentBody.slice(0, config.github.maxCommentLength - 200);
          commentBody = `${truncated}\n\n---\n\n⚠️ Response truncated (original was ${commentBody.length} chars, max is ${config.github.maxCommentLength}). See full response in the session file at \`${result.sessionPath ?? "state/sessions/"}\`.`;
        }
      } else {
        // Agent FAILED — post a clear error message with diagnostics
        const provider = result.providerUsed
          ? `${result.providerUsed.type}/${result.providerUsed.model}`
          : "unknown";
        const errMsg = result.error ?? "unknown error";
        commentBody = buildErrorMessage(result, provider, errMsg, config);
        log.error("main: agent failed, posting error comment", {
          issue: event.issueNumber,
          error: errMsg,
          provider,
        });
      }

      await gh.commentOnIssue(event.issueNumber, commentBody);
      memory.appendAudit("comment_posted", {
        issue: event.issueNumber,
        bodyLength: commentBody.length,
        success: result.success,
        truncated: result.success && result.response.length > config.github.maxCommentLength,
      });
    } else if (config.runtime.dryRun) {
      log.info("main: dry-run mode, would have commented", {
        success: result.success,
        responsePreview: result.response.slice(0, 200),
        error: result.error,
      });
    }
  } finally {
    // Cleanup reaction
    if (reactionState?.reactionId && !config.runtime.dryRun) {
      try {
        const gh = new GithubClient();
        const target =
          reactionState.reactionTarget === "comment" && reactionState.commentId
            ? { type: "comment" as const, id: reactionState.commentId }
            : { type: "issue" as const, id: reactionState.issueNumber };
        await gh.deleteReaction(target, reactionState.reactionId);
        log.info("main: reaction cleaned up");
      } catch (err) {
        log.warn("main: failed to cleanup reaction", {
          error: err instanceof Error ? err.message : String(err),
        });
      }
    }

    const totalMs = Date.now() - startTime;
    log.info("main: lifecycle complete", { totalMs });
    memory.appendAudit("agent_run_end", { issue: event.issueNumber, totalMs });
  }
}

// Run if invoked directly
if (import.meta.path === process.argv[1] || process.argv[1]?.endsWith("main.ts")) {
  const config = loadConfig();
  // Apply log level from config
  process.env.ISSUECLAW_LOG_LEVEL = config.runtime.logLevel;
  await main(config).catch((err) => {
    log.error("main failed", { error: err instanceof Error ? err.message : String(err) });
    process.exit(1);
  });
}

// Exported for tests: classification of aggregated provider failures.
export { buildErrorMessage, main };
