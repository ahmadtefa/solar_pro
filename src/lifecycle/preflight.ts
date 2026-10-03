#!/usr/bin/env bun
/**
 * Preflight credential/model check.
 *
 * Runs BEFORE the agent so a configuration problem is reported as itself
 * (bad key / retired model / missing secret) instead of surfacing later as a
 * vague "authentication error" after the run.
 *
 * Checks performed:
 *   1. Is a credential present for the default provider? (presence only — the
 *      value is never read into a log line)
 *   2. Is the configured Gemini model id still serviced by Google?
 *      (`GET /v1beta/models/{id}` with the `x-goog-api-key` header — the current
 *      authentication format for AI Studio `AQ.` keys)
 *   3. Does a stored pi credential exist that would shadow the GitHub secret?
 *      pi resolves `~/.pi/agent/auth.json` BEFORE the environment.
 *
 * Exit code is 0 (advisory) unless ISSUECLAW_PREFLIGHT_STRICT=true, so a
 * provider outage never blocks the agent from trying its fallbacks.
 */

import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { type IssueClawConfig, loadConfig } from "../config.ts";
import { checkGeminiModel } from "../providers/gemini.ts";
import { classifyProviderError, providerErrorHint, redactSecrets } from "../utils/errors.ts";
import { log } from "../utils/log.ts";

const GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta";

/** Providers we can actively probe before the run. */
const PROBEABLE = new Set(["gemini"]);

function defaultProvider(config: IssueClawConfig) {
  return config.providers.find((p) => p.default) ?? config.providers[0];
}

/**
 * Report any stored pi credential for a provider — it takes precedence over
 * the environment variable, so a stale key silently wins over the secret.
 */
function checkStoredPiCredentials(providerType: string): string | null {
  const agentDir = process.env.PI_CODING_AGENT_DIR ?? join(homedir(), ".pi", "agent");
  const authPath = join(agentDir, "auth.json");
  if (!existsSync(authPath)) return null;
  try {
    const data = JSON.parse(readFileSync(authPath, "utf-8")) as Record<string, { type?: string }>;
    const providerId = providerType === "gemini" ? "google" : providerType;
    if (data[providerId]) {
      return `stored pi credential found for "${providerId}" at ${authPath} — pi prefers it over the environment. Remove it (or set PI_CODING_AGENT_DIR to a clean directory) so the repository secret is used.`;
    }
  } catch {
    // Unreadable/absent auth store is not a problem.
  }
  return null;
}

interface PreflightResult {
  ok: boolean;
  checked: Array<{ provider: string; model: string; status: string; detail: string }>;
}

/**
 * Probe a Gemini model id. Returns a human-readable status; never returns or
 * logs the credential.
 */
export async function probeGeminiModel(
  model: string,
  apiKey: string,
): Promise<{ ok: boolean; status: string; detail: string }> {
  const status = checkGeminiModel(model.trim().replace(/^models\//, ""));
  if (status.error) {
    return { ok: false, status: "retired", detail: status.error };
  }

  const url = `${GEMINI_API_BASE}/models/${encodeURIComponent(model)}`;
  try {
    const resp = await fetch(url, {
      method: "GET",
      // Current auth format. Never put the key in the URL query string.
      headers: { "x-goog-api-key": apiKey, accept: "application/json" },
    });
    const body = await resp.text();
    const safeBody = redactSecrets(body.slice(0, 300), [apiKey]);

    if (resp.ok) {
      return { ok: true, status: "available", detail: `HTTP ${resp.status}` };
    }

    const info = classifyProviderError(`HTTP ${resp.status}: ${body}`);
    return {
      ok: false,
      status: info.kind,
      detail: `${providerErrorHint(info, "gemini")} (HTTP ${resp.status}) ${safeBody}`,
    };
  } catch (err) {
    const info = classifyProviderError(err);
    return {
      ok: false,
      status: info.kind,
      detail: `${info.summary}: ${redactSecrets(info.raw, [apiKey]).slice(0, 200)}`,
    };
  }
}

export async function preflight(config: IssueClawConfig): Promise<PreflightResult> {
  const result: PreflightResult = { ok: true, checked: [] };
  const provider = defaultProvider(config);

  if (!provider) {
    console.log("✗ No provider configured");
    return { ok: false, checked: [] };
  }

  const label = `${provider.type}/${provider.model}`;
  const secretName = `${provider.type.toUpperCase()}_API_KEY`;

  if (!provider.apiKey) {
    console.log(`✗ ${label}: secret ${secretName} is not set (empty or not exported)`);
    result.ok = false;
    return result;
  }

  // 1. Stored-credential shadowing.
  const stored = checkStoredPiCredentials(provider.type);
  if (stored) {
    console.log(`⚠️  ${label}: ${stored}`);
  }

  // 2. Live model probe (Gemini only — other providers are OpenAI-compatible
  //    and validating a key against /models is not always permitted).
  if (PROBEABLE.has(provider.type)) {
    const probe = await probeGeminiModel(provider.model, provider.apiKey);
    if (probe.ok) {
      console.log(`✓ ${label}: ${probe.status} (${probe.detail})`);
    } else {
      console.log(`✗ ${label}: ${probe.status} — ${probe.detail}`);
      result.ok = false;
    }
    result.checked.push({
      provider: provider.type,
      model: provider.model,
      status: probe.status,
      detail: probe.detail,
    });
  } else {
    console.log(`✓ ${provider.type}: credential present (${secretName})`);
  }

  return result;
}

if (import.meta.path === process.argv[1] || process.argv[1]?.endsWith("preflight.ts")) {
  const config = loadConfig();
  process.env.ISSUECLAW_LOG_LEVEL = config.runtime.logLevel;
  const strict = process.env.ISSUECLAW_PREFLIGHT_STRICT === "true";

  const result = await preflight(config).catch((err) => {
    // A probe failure must never mask the real run.
    log.warn("preflight failed to run", {
      error: err instanceof Error ? err.message : String(err),
    });
    return { ok: true, checked: [] } as PreflightResult;
  });

  if (!result.ok) {
    log.warn("preflight found configuration problems — the agent will still run", {
      strict,
    });
    if (strict) process.exit(1);
  }
}
