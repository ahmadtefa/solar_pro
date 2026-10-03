/**
 * Simple chat mode — lightweight LLM call WITHOUT the pi agent.
 *
 * This mode is for simple conversations that don't need file editing, bash,
 * or tool use. It calls the LLM API directly, using only ~500 tokens
 * (vs ~120,000 tokens for the full agent mode).
 *
 * This saves massive API quota — perfect for quick Q&A on issues.
 *
 * Triggered by:
 * - The "chat" label on an issue
 * - The "💬 Chat" issue template
 *
 * STILL saves to state/ (memory, session, audit) and commits to git.
 */

import type { IssueClawConfig, ProviderConfig } from "../config.ts";
import { getProviderChain } from "../config.ts";
import type { ParsedEvent } from "../github/events.ts";
import type { MemoryStore } from "../memory/store.ts";
import { classifyProviderError, providerErrorHint, redactSecrets } from "../utils/errors.ts";
import { log } from "../utils/log.ts";
import { errorMessage, isRetryableHttpError, retry, retryAfterMsFor } from "../utils/retry.ts";

export interface SimpleChatOptions {
  config: IssueClawConfig;
  memory: MemoryStore;
  event: ParsedEvent;
  existingMapping?: { sessionPath: string } | null;
}

export interface SimpleChatResult {
  success: boolean;
  response: string;
  providerUsed: ProviderConfig | null;
  tokensUsed: number;
  error?: string;
  durationMs: number;
}

/**
 * Build a minimal system prompt for simple chat.
 * Much smaller than pi's full system prompt (~200 tokens vs ~120K).
 */
function buildSystemPrompt(memory: MemoryStore): string {
  const parts: string[] = [
    "You are a helpful AI assistant running inside a GitHub repo via issueclaw.",
    "Respond concisely and helpfully. Use Markdown for formatting.",
  ];

  // Include personality if set (non-default)
  const personality = memory.readPersonality();
  if (personality && !personality.includes("TBD")) {
    parts.push(`\nYour identity:\n${personality}`);
  }

  // Include recent memory (last 10 lines, skip defaults)
  const memContent = memory.readMemory();
  if (memContent) {
    const lines = memContent
      .split("\n")
      .filter(
        (l) =>
          l.trim() && !l.startsWith("#") && !l.startsWith(">") && !l.includes("[uninitialized]"),
      )
      .slice(-10);
    if (lines.length > 0) {
      parts.push(`\nRecent memory:\n${lines.join("\n")}`);
    }
  }

  return parts.join("\n");
}

/**
 * Build the conversation history for the LLM.
 * For simple chat, we only include the current message (no session resume).
 * This keeps token count minimal.
 */
function buildUserMessage(event: ParsedEvent): string {
  if (event.type === "issue_comment.created") {
    return event.body;
  }
  return `${event.title}\n\n${event.body}`;
}

/**
 * Make a direct LLM API call (no pi, no tools, no agent).
 * Supports OpenAI-compatible APIs (Groq, Cerebras, OpenRouter, OpenAI, custom)
 * and Google Gemini's native API format.
 */
async function callLLM(
  provider: ProviderConfig,
  systemPrompt: string,
  userMessage: string,
): Promise<{ text: string; tokens: number }> {
  const apiKey = provider.apiKey;
  if (!apiKey || apiKey.includes("${")) {
    throw new Error(`${provider.type.toUpperCase()}_API_KEY not set`);
  }

  // Route to the appropriate API based on provider type
  if (provider.type === "gemini") {
    return callGemini(provider, apiKey, systemPrompt, userMessage);
  }
  // All other providers use OpenAI-compatible chat completions API
  return callOpenAICompatible(provider, apiKey, systemPrompt, userMessage);
}

/** Gemini API version path. `v1beta` is where current models live. */
export const GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta";

/**
 * Build the Gemini `generateContent` endpoint.
 *
 * Exported for tests: the API key must NEVER appear in the URL. Google's
 * current credential (the `AQ.` "auth" key issued by AI Studio) is only
 * accepted via the `x-goog-api-key` header — a key placed in `?key=` produces
 * an authentication/404 failure, and query strings additionally leak the
 * secret into proxy logs and stack traces.
 */
export function geminiGenerateContentUrl(model: string): string {
  return `${GEMINI_API_BASE}/models/${encodeURIComponent(model)}:generateContent`;
}

/**
 * Extract the assistant-visible text from a Gemini `generateContent` response.
 *
 * Reasoning models (Gemini 2.5+/3.x) return *thought* parts alongside the
 * answer and may split the answer across several parts, so reading only
 * `parts[0].text` yields an empty string for perfectly good responses.
 */
export function extractGeminiText(data: {
  candidates?: Array<{
    content?: { parts?: Array<{ text?: string; thought?: boolean }> };
    finishReason?: string;
    finishMessage?: string;
  }>;
  promptFeedback?: { blockReason?: string; blockReasonMessage?: string };
}): string {
  const parts = data.candidates?.[0]?.content?.parts ?? [];
  return parts
    .filter((part) => part.thought !== true)
    .map((part) => part.text ?? "")
    .join("")
    .trim();
}

/**
 * Call Google Gemini's native API.
 * Endpoint: POST {GEMINI_API_BASE}/models/{model}:generateContent
 * Auth:     `x-goog-api-key` header (see geminiGenerateContentUrl docs).
 */
async function callGemini(
  provider: ProviderConfig,
  apiKey: string,
  systemPrompt: string,
  userMessage: string,
): Promise<{ text: string; tokens: number }> {
  const model = provider.model.trim().replace(/^models\//, "");
  const url = geminiGenerateContentUrl(model);

  const body = {
    contents: [
      {
        role: "user",
        parts: [{ text: userMessage }],
      },
    ],
    systemInstruction: {
      parts: [{ text: systemPrompt }],
    },
    generationConfig: {
      temperature: provider.temperature ?? 0.7,
      // Reasoning models spend this budget on internal thinking before any
      // visible text, so a small cap produces MAX_TOKENS with no answer.
      maxOutputTokens: provider.maxTokens ?? 32768,
    },
  };

  const resp = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-goog-api-key": apiKey,
    },
    body: JSON.stringify(body),
  });

  if (!resp.ok) {
    const errText = await resp.text();
    const retryAfter = resp.headers.get("retry-after");
    const hint = retryAfter ? ` retry-after: ${retryAfter}` : "";
    // Surface the status + body so the classifier can tell 401/403 (bad key)
    // apart from 404 (retired model), 429 (rate limit) and 503 (overloaded).
    throw new Error(`Gemini API error (${resp.status})${hint}: ${errText.slice(0, 500)}`);
  }

  const data = (await resp.json()) as {
    candidates?: Array<{
      content?: { parts?: Array<{ text?: string; thought?: boolean }> };
      finishReason?: string;
      finishMessage?: string;
    }>;
    promptFeedback?: { blockReason?: string; blockReasonMessage?: string };
    usageMetadata?: { totalTokenCount?: number };
  };

  const text = extractGeminiText(data);
  const tokens = data.usageMetadata?.totalTokenCount ?? 0;

  if (!text) {
    // Explain *why* the response had no text instead of a bare "empty response"
    // that previously got misreported as an authentication failure.
    const reason = data.promptFeedback?.blockReason
      ? `blocked by Gemini (${data.promptFeedback.blockReason})`
      : data.candidates?.[0]?.finishReason === "MAX_TOKENS"
        ? "Gemini exhausted the output budget on internal reasoning — raise agent/providers[].maxTokens"
        : data.candidates?.[0]?.finishReason
          ? `finishReason=${data.candidates[0].finishReason}`
          : "no candidates returned";
    throw new Error(`Gemini returned an empty response for model "${model}": ${reason}`);
  }

  return { text, tokens };
}

/**
 * Call an OpenAI-compatible chat completions API.
 * Works with: Groq, Cerebras, OpenRouter, OpenAI, Together, Groq, vLLM, etc.
 */
async function callOpenAICompatible(
  provider: ProviderConfig,
  apiKey: string,
  systemPrompt: string,
  userMessage: string,
): Promise<{ text: string; tokens: number }> {
  // Determine base URL based on provider type
  const baseUrl = getBaseUrl(provider);
  const url = `${baseUrl}/chat/completions`;

  const body = {
    model: provider.model,
    messages: [
      { role: "system", content: systemPrompt },
      { role: "user", content: userMessage },
    ],
    temperature: provider.temperature ?? 0.7,
    max_tokens: provider.maxTokens ?? 8192,
  };

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Authorization: `Bearer ${apiKey}`,
  };
  if (provider.headers) {
    for (const [k, v] of Object.entries(provider.headers)) {
      headers[k] = v;
    }
  }

  const resp = await fetch(url, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });

  if (!resp.ok) {
    const errText = await resp.text();
    const retryAfter = resp.headers.get("retry-after");
    const hint = retryAfter ? ` retry-after: ${retryAfter}` : "";
    throw new Error(`LLM API error (${resp.status})${hint}: ${errText.slice(0, 500)}`);
  }

  const data = (await resp.json()) as {
    choices?: Array<{
      message?: { content?: string };
      finish_reason?: string;
    }>;
    usage?: { total_tokens?: number };
  };

  const text = data.choices?.[0]?.message?.content ?? "";
  const tokens = data.usage?.total_tokens ?? 0;

  if (!text) {
    throw new Error("LLM returned empty response");
  }

  return { text, tokens };
}

/**
 * Get the base URL for an OpenAI-compatible provider.
 */
function getBaseUrl(provider: ProviderConfig): string {
  if (provider.baseUrl) return provider.baseUrl.replace(/\/$/, "");

  switch (provider.type) {
    case "groq":
      return "https://api.groq.com/openai/v1";
    case "cerebras":
      return "https://api.cerebras.ai/v1";
    case "openrouter":
      return "https://openrouter.ai/api/v1";
    case "openai":
      return "https://api.openai.com/v1";
    case "ollama":
      return "http://localhost:11434/v1";
    default:
      return "https://api.openai.com/v1";
  }
}

/**
 * Run a simple chat — direct LLM call, no agent, no tools.
 * Saves ~99% of API tokens compared to full agent mode.
 */
export async function runSimpleChat(options: SimpleChatOptions): Promise<SimpleChatResult> {
  const startTime = Date.now();
  const { config, memory, event } = options;

  const systemPrompt = buildSystemPrompt(memory);
  const userMessage = buildUserMessage(event);

  log.info("starting simple chat", {
    issue: event.issueNumber,
    systemPromptTokens: Math.ceil(systemPrompt.length / 4),
    userMessageTokens: Math.ceil(userMessage.length / 4),
  });

  const providers = getProviderChain(config);
  const failures: Array<{ provider: string; model: string; error: string; skipped: boolean }> = [];
  const secrets = providers.map((p) => p.apiKey);

  for (const provider of providers) {
    const hasKey = Boolean(
      provider.apiKey && provider.apiKey.length > 0 && !provider.apiKey.includes("${"),
    );
    if (!hasKey) {
      log.info("simple chat: skipping provider (no key)", { provider: provider.type });
      failures.push({
        provider: provider.type,
        model: provider.model,
        error: `skipped — no API key configured (needs ${provider.type.toUpperCase()}_API_KEY secret)`,
        skipped: true,
      });
      continue;
    }

    try {
      const result = await retry(() => callLLM(provider, systemPrompt, userMessage), {
        maxAttempts: 4,
        name: `simple-chat ${provider.type}/${provider.model}`,
        retryIf: isRetryableHttpError,
        // Honour Gemini's "Please retry in 43.8s" instead of hammering the API.
        retryAfterMs: retryAfterMsFor,
        initialDelayMs: 5000,
        maxDelayMs: 60000,
      });

      log.info("simple chat succeeded", {
        provider: `${provider.type}/${provider.model}`,
        tokens: result.tokens,
        durationMs: Date.now() - startTime,
      });

      return {
        success: true,
        response: result.text,
        providerUsed: provider,
        tokensUsed: result.tokens,
        durationMs: Date.now() - startTime,
      };
    } catch (err) {
      const errMsg = errorMessage(err);
      const info = classifyProviderError(err);
      failures.push({
        provider: provider.type,
        model: provider.model,
        error: errMsg,
        skipped: false,
      });
      log.warn("simple chat: provider failed, trying next", {
        provider: provider.type,
        model: provider.model,
        kind: info.kind,
        retryable: info.retryable,
        error: redactSecrets(errMsg, secrets),
        hint: providerErrorHint(info, provider.type),
      });
    }
  }

  const failureSummary = failures
    .map((f, i) => {
      const keyStatus = f.skipped ? "skipped" : "failed";
      return `${i + 1}. \`${f.provider}/${f.model}\` (${keyStatus}): ${redactSecrets(f.error, secrets)}`;
    })
    .join("\n");

  return {
    success: false,
    response: "",
    providerUsed: null,
    tokensUsed: 0,
    error: `All ${providers.length} provider(s) failed in simple chat mode:\n\n${failureSummary}`,
    durationMs: Date.now() - startTime,
  };
}
