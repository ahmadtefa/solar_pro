/**
 * Google Gemini provider.
 *
 * AUTHENTICATION (2026)
 * ---------------------
 * Google AI Studio now issues **AUTH-style keys** with the `AQ.` prefix (bound
 * to a Cloud service account). The older `AIzaSy…` "standard" keys are being
 * rejected outright. Both must be sent in the HTTP request as the
 * `x-goog-api-key` header — the legacy `?key=<API_KEY>` query parameter is not
 * accepted for `AQ.` keys.
 *
 * This provider does not build requests itself: it hands the key to pi via
 * `GEMINI_API_KEY`, and pi's native `google` provider (through `@google/genai`)
 * sends it as `x-goog-api-key` against
 * `https://generativelanguage.googleapis.com/v1beta`. That is the format Google
 * currently documents, so agent mode stays compatible.
 *
 * IMPORTANT: pi resolves credentials from `~/.pi/agent/auth.json` FIRST and
 * only falls back to `GEMINI_API_KEY`. A stale stored credential therefore
 * silently shadows the GitHub secret. In CI we point pi at a clean agent dir
 * (see `PI_CODING_AGENT_DIR` in the workflow) so the secret always wins.
 *
 * MODEL LIFETIME
 * --------------
 * Google retires Gemini models aggressively, and a retired id fails with
 * HTTP 404 `NOT_FOUND` — which used to be reported as "authentication error".
 * `GEMINI_RETIRED_MODELS` below lets us fail fast with an actionable message
 * and a replacement id instead.
 *
 * Get a free API key: https://aistudio.google.com/app/apikey
 */

import type { ProviderConfig } from "../config.ts";
import type { Provider, ProviderArgs } from "./types.ts";

/**
 * Gemini models currently served on the free tier (Flash / Flash-Lite only —
 * Pro models left the free tier in April 2026).
 */
export const GEMINI_DEFAULT_MODELS = [
  "gemini-3.5-flash-lite", // 500 free RPD — recommended default for agents
  "gemini-3.8-flash", // free tier, stronger reasoning, ~5 RPM / 20 RPD
  "gemini-flash-lite-latest", // Google-managed alias, always current
  "gemini-flash-latest", // Google-managed alias, always current
  "gemini-3.1-flash-lite",
] as const;

/**
 * Models Google has retired (or gated behind a paid tier / legacy users).
 * Keyed by the retired id, valued by the documented replacement.
 *
 * Sources: the API's own 404 body ("This model models/<id> is no longer
 * available to new users. Please update your code to use models/<new>") and
 * Google's Gemini deprecation notices.
 */
export const GEMINI_RETIRED_MODELS: Record<string, string> = {
  "gemini-1.5-flash": "gemini-3.5-flash-lite",
  "gemini-1.5-flash-8b": "gemini-3.5-flash-lite",
  "gemini-1.5-pro": "gemini-3.1-pro-preview",
  "gemini-2.0-flash": "gemini-3.5-flash",
  "gemini-2.0-flash-exp": "gemini-3.5-flash",
  "gemini-2.0-flash-lite": "gemini-3.5-flash-lite",
  "gemini-2.0-flash-preview-image-generation": "gemini-3.5-flash",
  "gemini-2.5-flash-lite": "gemini-3.5-flash-lite",
  "gemini-2.5-flash": "gemini-3.5-flash",
  "gemini-2.5-flash-preview": "gemini-3.5-flash",
  "gemini-2.5-pro": "gemini-3.1-pro-preview",
  "gemini-pro": "gemini-3.5-flash",
  "gemini-pro-vision": "gemini-3.5-flash",
};

/** Models that exist but are not usable on the free tier (informational). */
export const GEMINI_PAID_ONLY_MODELS = [
  "gemini-2.5-pro",
  "gemini-3-pro-preview",
  "gemini-3.1-pro-preview",
  "gemini-3.1-pro-preview-customtools",
] as const;

export interface GeminiModelStatus {
  ok: boolean;
  /** Retired ids are rejected up-front; unknown ids are allowed but flagged. */
  retired?: boolean;
  replacement?: string;
  paidOnly?: boolean;
  warning?: string;
  error?: string;
}

/**
 * Check whether a configured Gemini model id is usable.
 *
 * Only *known-retired* ids are treated as errors so a brand-new model Google
 * ships tomorrow still works without a code change.
 */
export function checkGeminiModel(model: string): GeminiModelStatus {
  const id = model.trim().replace(/^models\//, "");

  const replacement = GEMINI_RETIRED_MODELS[id];
  if (replacement) {
    return {
      ok: false,
      retired: true,
      replacement,
      error: `Gemini model "${id}" has been retired by Google and now returns HTTP 404 (NOT_FOUND). Use "${replacement}" instead — update issueclaw.config.json or the ISSUECLAW_MODEL repository variable.`,
    };
  }

  if ((GEMINI_PAID_ONLY_MODELS as readonly string[]).includes(id)) {
    return {
      ok: true,
      paidOnly: true,
      warning: `Gemini model "${id}" is not available on the free tier (paid tier only).`,
    };
  }

  if (!(GEMINI_DEFAULT_MODELS as readonly string[]).includes(id)) {
    return {
      ok: true,
      warning: `Gemini model "${id}" is not in IssueClaw's known-good list (${GEMINI_DEFAULT_MODELS.join(", ")}). It may be new, renamed, or unavailable.`,
    };
  }

  return { ok: true };
}

export const geminiProvider: Provider = {
  type: "gemini",

  buildArgs(config: ProviderConfig): ProviderArgs {
    // Use pi's NATIVE google provider (reads GEMINI_API_KEY, sends the key as
    // the x-goog-api-key header — required for the new AQ. auth keys).
    const args = ["--provider", "google", "--model", config.model];
    if (config.thinking) {
      args.push("--thinking", config.thinking);
    }
    const env: Record<string, string | undefined> = {};
    if (config.apiKey) {
      env.GEMINI_API_KEY = config.apiKey;
      // Clear the ambient alias so it cannot take precedence over the secret.
      // (@google/genai prefers GOOGLE_API_KEY when both are set.)
      env.GOOGLE_API_KEY = undefined;
    }
    return { args, env };
  },

  validate(config: ProviderConfig): string | null {
    if (!config.model) return "Gemini provider requires a model";
    if (!config.apiKey) {
      return "Gemini provider requires GEMINI_API_KEY (get free at https://aistudio.google.com/app/apikey)";
    }
    // Retired model ids fail fast with an actionable message instead of
    // burning a run on a guaranteed HTTP 404. Warnings (new/unlisted models)
    // are surfaced by `issueclaw doctor` and the workflow preflight, not here.
    const status = checkGeminiModel(config.model);
    if (!status.ok) return status.error ?? "Gemini model is not available";
    return null;
  },
};

/**
 * Non-fatal diagnostics for a Gemini model id (used by `issueclaw doctor` and
 * the workflow preflight step).
 */
export function geminiModelWarnings(model: string): string[] {
  const status = checkGeminiModel(model);
  const warnings: string[] = [];
  if (status.error) warnings.push(status.error);
  if (status.warning) warnings.push(status.warning);
  return warnings;
}
