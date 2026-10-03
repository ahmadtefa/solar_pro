/**
 * Provider error classification + secret redaction.
 *
 * WHY THIS EXISTS
 * ---------------
 * IssueClaw talks to several LLM backends. Each one reports failures with its
 * own wording: Google returns gRPC-ish JSON (`RESOURCE_EXHAUSTED`,
 * `UNAVAILABLE`, `NOT_FOUND`), OpenAI-compatible APIs return HTTP status codes,
 * and network layers throw plain fetch errors.
 *
 * Historically the lifecycle layer guessed the failure type with a single
 * regex over the *aggregated* multi-provider error summary. Because that
 * summary always contains the string `no API key set (needs GROQ_API_KEY)` for
 * every unconfigured fallback provider, the substring "API key" matched and
 * EVERY failure was reported as "Authentication error (403/401)" — including
 * real 404 "model retired" and 429 "quota exceeded" failures.
 *
 * This module classifies a single provider failure properly, so:
 *   1. retries only happen for genuinely transient errors (429/5xx/network),
 *   2. the GitHub comment tells the user what actually happened,
 *   3. secrets never end up in logs or comments.
 */

export type ProviderErrorKind =
  /** Per-minute throttling. Transient — retry with backoff. */
  | "rate_limit"
  /** Per-day / billing quota exhaustion. Not retryable in-run. */
  | "quota_exhausted"
  /** Provider overloaded (HTTP 5xx, Gemini UNAVAILABLE). Transient. */
  | "overloaded"
  /** Bad/revoked credential (401/403, PERMISSION_DENIED). Fatal. */
  | "auth"
  /** No credential configured at all — configuration, NOT a rejected key. */
  | "missing_credential"
  /** Model id is unknown, retired, or gated for this account (404). Fatal. */
  | "model_not_found"
  /** Prompt exceeds the model's token ceiling (413). Fatal. */
  | "request_too_large"
  /** Response blocked by safety/recitation filters. Fatal. */
  | "blocked"
  /** Transport failure (DNS, reset, timeout). Transient. */
  | "network"
  /** Anything we cannot classify. Treated as fatal by default. */
  | "unknown";

export interface ProviderErrorInfo {
  kind: ProviderErrorKind;
  /** Whether retrying the same request could plausibly succeed. */
  retryable: boolean;
  /** HTTP status code, when one could be extracted. */
  httpStatus?: number;
  /** Model id mentioned in the error, when present. */
  model?: string;
  /** Delay the provider explicitly asked us to wait (ms). */
  retryAfterMs?: number;
  /** Provider-suggested replacement model (e.g. retired model ids). */
  suggestedModel?: string;
  /** Short, human-readable classification summary. */
  summary: string;
  /** Original message, verbatim. */
  raw: string;
}

/** Extract an HTTP status code from an error message, if one is present. */
export function extractHttpStatus(message: string): number | undefined {
  // JSON-ish shapes first: `"code": 429`, `code: 503`, `HTTP 404`, `(404)`.
  const jsonish = message.match(/["']?code["']?\s*[:=]\s*(\d{3})/i);
  if (jsonish?.[1]) return Number(jsonish[1]);
  const http = message.match(/\bHTTP[/ ]?(\d{3})\b/i);
  if (http?.[1]) return Number(http[1]);
  const paren = message.match(/\((\d{3})\)/);
  if (paren?.[1]) return Number(paren[1]);
  const bare = message.match(/\b(4\d{2}|5\d{2})\b/);
  if (bare?.[1]) return Number(bare[1]);
  return undefined;
}

/**
 * Parse the delay a provider asked us to wait for.
 *
 * Gemini returns e.g. `"retryDelay": "43.835229498s"` and a human hint
 * `Please retry in 43.835229498s`. OpenAI-compatible gateways use the
 * `Retry-After` header (seconds or an HTTP date), which callers append to the
 * error message as `retry-after: 30`.
 */
export function parseRetryDelayMs(message: string): number | undefined {
  if (!message) return undefined;

  const attempts: Array<RegExp> = [
    /retry-?after["']?\s*[:=]\s*(\d+(?:\.\d+)?)\s*(ms|s|seconds?)?/i,
    /retryDelay["']?\s*[:=]\s*["']?(\d+(?:\.\d+)?)\s*(ms|s|seconds?)?["']?/i,
    /retry in\s+(\d+(?:\.\d+)?)\s*(ms|s|seconds?)?/i,
    /try again in\s+(\d+(?:\.\d+)?)\s*(ms|s|seconds?)?/i,
  ];

  for (const re of attempts) {
    const m = message.match(re);
    if (!m?.[1]) continue;
    const value = Number(m[1]);
    if (!Number.isFinite(value) || value < 0) continue;
    const unit = (m[2] ?? "s").toLowerCase();
    const ms = unit.startsWith("ms") ? value : value * 1000;
    // Guard against absurd values (a provider returning a date, a token count…).
    if (ms > 0 && ms <= 15 * 60 * 1000) return Math.round(ms);
  }
  return undefined;
}

/** Extract a model id from an error message (`models/gemini-2.5-flash-lite`). */
export function extractModelFromError(message: string): string | undefined {
  const m = message.match(/models\/([a-z0-9._-]+)/i);
  if (m?.[1]) return m[1];
  // Quoted or bare: `"model": "gemini-3.8-flash"` / `model: gemini-3.8-flash`.
  const named = message.match(
    /(?:model|model_id)["']?\s*[:=]\s*["']?([a-z0-9][a-z0-9._-]{2,})["']?/i,
  );
  return named?.[1];
}

/** Pull Google's "please use models/x" suggestion out of a 404 body. */
export function extractSuggestedModel(message: string): string | undefined {
  const m = message.match(/use\s+models\/([a-z0-9._-]+)/i);
  return m?.[1];
}

/**
 * "No credential configured" is deliberately kept separate from "credential
 * rejected". Conflating them is what produced the bogus 403/401 diagnosis: the
 * aggregated failure summary always contains the phrase "no API key configured
 * (needs GROQ_API_KEY)" for every unconfigured fallback provider.
 */
const MISSING_CREDENTIAL_PATTERNS: RegExp[] = [
  /no api key/i,
  /api key (?:is )?not set/i,
  /missing[_ ]api[_ ]key/i,
  /needs [A-Z0-9_]*API_KEY/i,
  /requires? (?:an? )?[A-Z0-9_]*API_KEY/i,
  /credential (?:is )?not (?:set|configured)/i,
];

const AUTH_PATTERNS: RegExp[] = [
  /API key not valid/i,
  /API key expired/i,
  /api[_ ]?key[_ ]?invalid/i,
  /invalid[_ ]api[_ ]key/i,
  /invalid api key/i,
  /\bUNAUTHENTICATED\b/,
  /\bPERMISSION_DENIED\b/,
  /\bForbidden\b/,
  /\bUnauthorized\b/,
  /is not authorized/i,
  /billing (?:is )?not enabled/i,
];

const MODEL_NOT_FOUND_PATTERNS: RegExp[] = [
  /\bNOT_FOUND\b/,
  /is no longer available/i,
  /no longer supported/i,
  /has been (?:retired|deprecated|shut down)/i,
  /not found for API version/i,
  /not supported for generateContent/i,
  /does not exist/i,
  /unknown model/i,
  /unsupported model/i,
];

/**
 * Signals that a 429 is a *daily* / billing limit rather than a per-minute
 * throttle. Google reports both as `RESOURCE_EXHAUSTED`, so the distinction
 * has to come from the wording: per-minute limits come with a
 * "Please retry in Ns" hint, daily limits say "per day"/"RPD".
 */
const QUOTA_EXHAUSTED_PATTERNS: RegExp[] = [
  /per day/i,
  /per-day/i,
  /daily (?:limit|quota)/i,
  /\bRPD\b/,
  /requests? per day/i,
  /insufficient[_ ]quota/i,
  /out of budget/i,
  /billing (?:details|account|required|not enabled)/i,
];

const RATE_LIMIT_PATTERNS: RegExp[] = [
  /\bRESOURCE_EXHAUSTED\b/,
  /rate.?limit/i,
  /too many requests/i,
  /\b429\b/,
];

const OVERLOADED_PATTERNS: RegExp[] = [
  /\bUNAVAILABLE\b/,
  /high demand/i,
  /overloaded/i,
  /service.?unavailable/i,
  /\b(500|502|503|504|524)\b/,
  /internal.?error/i,
];

const NETWORK_PATTERNS: RegExp[] = [
  /fetch failed/i,
  /ECONNRESET|ECONNREFUSED|ETIMEDOUT|EPIPE|EAI_AGAIN/i,
  /socket hang up/i,
  /network.?error/i,
  /connection.?error/i,
  /timed? out/i,
  /timeout/i,
  /terminated/i,
];

const TOO_LARGE_PATTERNS: RegExp[] = [
  /\b413\b/,
  /request too large/i,
  /exceeds the maximum number of tokens/i,
  /token count.*exceeds/i,
];

const BLOCKED_PATTERNS: RegExp[] = [
  /blockReason/i,
  /\bSAFETY\b/,
  /\bRECITATION\b/,
  /PROHIBITED_CONTENT/,
  /content was blocked/i,
  /finishReason["']?\s*:\s*["']?(SAFETY|RECITATION|PROHIBITED_CONTENT|BLOCKLIST)/i,
];

function matches(patterns: RegExp[], text: string): boolean {
  return patterns.some((re) => re.test(text));
}

/**
 * Classify a single provider failure.
 *
 * Order matters: auth and model errors must be checked before generic 4xx/5xx
 * handling, and quota wording must be checked before plain rate-limit wording
 * because Gemini reuses `RESOURCE_EXHAUSTED` for both.
 */
export function classifyProviderError(error: unknown): ProviderErrorInfo {
  const raw = error instanceof Error ? error.message : String(error ?? "");
  const status = extractHttpStatus(raw);
  const retryAfterMs = parseRetryDelayMs(raw);
  const model = extractModelFromError(raw);
  const suggestedModel = extractSuggestedModel(raw);
  const base = { raw, httpStatus: status, retryAfterMs, model, suggestedModel };

  // 401/403 are authoritative — never let another pattern override them.
  if (status === 401 || status === 403) {
    return { ...base, kind: "auth", retryable: false, summary: "API key rejected" };
  }
  if (matches(MISSING_CREDENTIAL_PATTERNS, raw) && !matches(AUTH_PATTERNS, raw)) {
    return {
      ...base,
      kind: "missing_credential",
      retryable: false,
      summary: "No credential configured for this provider",
    };
  }
  if (matches(AUTH_PATTERNS, raw)) {
    return {
      ...base,
      kind: "auth",
      retryable: false,
      summary: status ? `API key rejected (HTTP ${status})` : "API key rejected",
    };
  }

  // 404 for a model id — almost always "the model was retired".
  if (status === 404 || matches(MODEL_NOT_FOUND_PATTERNS, raw)) {
    return {
      ...base,
      kind: "model_not_found",
      retryable: false,
      summary: model ? `Model "${model}" is not available` : "Model is not available",
    };
  }

  if (status === 413 || matches(TOO_LARGE_PATTERNS, raw)) {
    return { ...base, kind: "request_too_large", retryable: false, summary: "Request too large" };
  }

  if (matches(BLOCKED_PATTERNS, raw)) {
    return { ...base, kind: "blocked", retryable: false, summary: "Response blocked by provider" };
  }

  const isThrottle = status === 429 || matches(RATE_LIMIT_PATTERNS, raw);
  if (isThrottle) {
    // Gemini's free tier returns 429 with "Please retry in 43.8s" for per-minute
    // limits (transient) and "limit: N ... per day" for daily limits (fatal).
    // An explicit retry hint always wins: the API only asks us to wait when
    // waiting actually helps.
    const hasRetryHint = retryAfterMs !== undefined || /please retry|retry in/i.test(raw);
    const dailyOnly =
      matches(QUOTA_EXHAUSTED_PATTERNS, raw) && !/per minute|RPM/i.test(raw) && !hasRetryHint;
    if (dailyOnly) {
      return {
        ...base,
        kind: "quota_exhausted",
        retryable: false,
        summary: "Daily quota exhausted",
      };
    }
    return { ...base, kind: "rate_limit", retryable: true, summary: "Rate limited (429)" };
  }

  if (matches(OVERLOADED_PATTERNS, raw)) {
    return { ...base, kind: "overloaded", retryable: true, summary: "Provider overloaded" };
  }

  if (matches(NETWORK_PATTERNS, raw)) {
    return { ...base, kind: "network", retryable: true, summary: "Network error" };
  }

  return { ...base, kind: "unknown", retryable: false, summary: "Unclassified provider error" };
}

/**
 * Actionable, model-aware advice for a failed provider attempt.
 * Deliberately never contains any part of a credential.
 */
export function providerErrorHint(info: ProviderErrorInfo, providerType: string): string {
  switch (info.kind) {
    case "auth":
      return `${providerType}: credential rejected. Re-check the repository secret (regenerate the key if it was revoked).`;
    case "missing_credential":
      return `${providerType}: no credential configured — set the matching repository secret.`;
    case "model_not_found":
      return info.suggestedModel
        ? `${providerType}: model ${info.model ?? "(unknown)"} is retired — switch to ${info.suggestedModel}`
        : `${providerType}: model ${info.model ?? "(unknown)"} is unavailable for this account.`;
    case "quota_exhausted":
      return `${providerType}: daily quota exhausted (resets at midnight Pacific). Add another provider or a paid tier.`;
    case "rate_limit":
      return `${providerType}: per-minute rate limit — retried with backoff.`;
    case "overloaded":
      return `${providerType}: provider temporarily overloaded — retried with backoff.`;
    case "request_too_large":
      return `${providerType}: prompt exceeds the model's token limit.`;
    case "blocked":
      return `${providerType}: response blocked by the provider's safety filters.`;
    case "network":
      return `${providerType}: transport error.`;
    default:
      return `${providerType}: unclassified error.`;
  }
}

// ============================================================================
// Secret redaction
// ============================================================================

/** Well-known credential shapes (Google AI Studio keys, OpenAI, GitHub, Slack…). */
const SECRET_PATTERNS: RegExp[] = [
  // Google AI Studio "auth" keys (AQ.…) and legacy "standard" keys (AIzaSy…).
  /\bAQ\.[A-Za-z0-9_.-]{8,}[A-Za-z0-9_-]/g,
  /\bAIza[0-9A-Za-z_-]{10,}/g,
  /\bsk-[A-Za-z0-9_-]{16,}/g,
  /\bsk-ant-[A-Za-z0-9_-]{16,}/g,
  /\bsk-or-v1-[A-Za-z0-9_-]{16,}/g,
  /\bgsk_[A-Za-z0-9_-]{16,}/g,
  /\bcsk-[A-Za-z0-9_-]{16,}/g,
  /\bghp_[A-Za-z0-9]{20,}/g,
  /\bgho_[A-Za-z0-9]{20,}/g,
  /\bghs_[A-Za-z0-9]{20,}/g,
  /\bghu_[A-Za-z0-9]{20,}/g,
  /\bghr_[A-Za-z0-9]{20,}/g,
  /\bgithub_pat_[A-Za-z0-9_]{20,}/g,
];

const ENV_SECRET_NAME_RE =
  /(?:^(?:GEMINI|GOOGLE|GROQ|CEREBRAS|OPENROUTER|ANTHROPIC|OPENAI)_API_KEY$|^(?:GITHUB_TOKEN|GH_TOKEN)$|(?:_API_KEY|_SECRET|_TOKEN|_PASSWORD)$)/i;

/**
 * Redact secrets from arbitrary text before it is logged, persisted to a
 * session/state file, or posted publicly.
 *
 * @param text      text that may contain secrets
 * @param secrets   exact secret values to scrub (e.g. resolved API keys)
 */
export function redactSecrets(text: string, secrets: Array<string | undefined> = []): string {
  if (!text) return text;
  let out = text;

  // Exact values first (most reliable), then credential-shaped patterns.
  for (const secret of secrets) {
    if (!secret) continue;
    const trimmed = secret.trim();
    if (secret.length >= 8) {
      out = out.split(secret).join("***");
    }
    if (trimmed.length >= 8 && trimmed !== secret) {
      out = out.split(trimmed).join("***");
    }
  }
  for (const re of SECRET_PATTERNS) {
    out = out.replace(re, "***");
  }

  // Env/header assignments for known secret names (e.g. GEMINI_API_KEY=..., "x-goog-api-key":"...")
  out = out.replace(
    /(\b(?:GEMINI_API_KEY|GOOGLE_API_KEY|GROQ_API_KEY|CEREBRAS_API_KEY|OPENROUTER_API_KEY|ANTHROPIC_API_KEY|OPENAI_API_KEY|GITHUB_TOKEN|GH_TOKEN|x-goog-api-key)\b\s*(?:=|"?:?\s*"?))([^\s"'`,;}\\]+)/gi,
    (full, prefix: string, val: string) => {
      if (val.startsWith("${") || val === "***" || val.length < 6) return full;
      return `${prefix}***`;
    },
  );

  // Query-string credentials: `?key=…`, `api_key=…`, `access_token=…`.
  out = out.replace(/([?&](?:key|api_key|apikey|access_token)=)[^&\s"'`]+/gi, "$1***");
  return out;
}

/**
 * Describe a credential WITHOUT revealing it.
 *
 * Knowing the key *shape* is what distinguishes a current AI Studio auth key
 * from a legacy standard key — the single most common cause of unexplained
 * Gemini 401/403/404 responses — without ever printing the secret itself.
 */
export function describeCredential(secret: string | undefined): string {
  if (!secret) return "not set";
  if (secret.includes("${")) return `unresolved reference ${secret}`;
  const trimmed = secret.trim();
  const format = !trimmed
    ? "empty"
    : /^AQ\./.test(trimmed)
      ? "AI Studio auth key (AQ.…)"
      : /^AIza/.test(trimmed)
        ? "legacy standard key (AIzaSy…)"
        : "unrecognized format";
  const whitespace = trimmed !== secret ? " — WARNING: contains leading/trailing whitespace" : "";
  return `${format}, ${secret.length} chars${whitespace}`;
}

/** True when a secret value looks usable (non-empty and already resolved). */
export function hasUsableSecret(secret: string | undefined): boolean {
  return Boolean(secret && secret.trim().length > 0 && !secret.includes("${"));
}

/**
 * Collect every resolved credential in a config (and optionally ambient
 * environment), for redaction purposes.
 */
export function collectSecrets(
  providers: Array<{ apiKey?: string; headers?: Record<string, string> }> = [],
  env?: Record<string, string | undefined>,
): string[] {
  const seen = new Set<string>();
  const add = (val: string | undefined) => {
    if (!val) return;
    const trimmed = val.trim();
    if (trimmed.length >= 8 && !trimmed.includes("${")) {
      seen.add(val);
      if (trimmed !== val) seen.add(trimmed);
    }
  };

  for (const p of providers) {
    add(p.apiKey);
    if (p.headers) {
      for (const v of Object.values(p.headers)) {
        add(v);
      }
    }
  }

  if (env) {
    for (const [key, value] of Object.entries(env)) {
      if (ENV_SECRET_NAME_RE.test(key)) {
        add(value);
      }
    }
  }

  return Array.from(seen);
}
