/**
 * The reported "403/401" failures were produced here: the classifier matched
 * /API key/i inside the "skipped — no API key configured (needs …)" lines of
 * the unconfigured fallback providers, so every failure was labelled as an
 * authentication error. These tests pin the corrected behaviour.
 */
import { describe, expect, it } from "vitest";
import type { AgentRunResult } from "../../src/agent/runner.ts";
import type { IssueClawConfig } from "../../src/config.ts";
import { buildErrorMessage } from "../../src/lifecycle/main.ts";

function makeConfig(): IssueClawConfig {
  return {
    version: 1,
    providers: [
      {
        type: "gemini",
        model: "gemini-2.5-flash-lite",
        apiKey: "AQ.example-secret-value-1234",
        default: true,
      },
      { type: "groq", model: "llama-3.3-70b-versatile", apiKey: "" },
      { type: "cerebras", model: "llama-3.3-70b", apiKey: "" },
    ],
    memory: {
      stateDir: "./state",
      memoryFile: "memory.md",
      personalityFile: "personality.md",
      userFile: "user.md",
      auditFile: "audit.log",
      maxSessionSize: 10485760,
      autoCompact: true,
    },
    github: {
      onIssueOpened: true,
      onIssueComment: true,
      onPullRequest: false,
      allowedAssociations: ["OWNER", "MEMBER", "COLLABORATOR"],
      hatchLabel: "hatch",
      reactionWhileProcessing: true,
      maxCommentLength: 60000,
      concurrencyGroup: "x",
    },
    agent: {
      piCommand: "bunx pi",
      timeoutMs: 60000,
      skills: false,
      extensions: false,
      appendSystemPrompt: ".pi/APPEND_SYSTEM.md",
      agentsFile: "AGENTS.md",
    },
    runtime: { dryRun: false, logLevel: "info", logJson: false, offline: false },
  };
}

function makeResult(error: string): AgentRunResult {
  return {
    success: false,
    response: "",
    sessionPath: null,
    providerUsed: null,
    error,
    durationMs: 1234,
  };
}

/** Mirrors the failure summary the runner builds. */
function failureSummary(entries: Array<[string, string]>): string {
  return `All ${entries.length} provider(s) failed:\n\n${entries
    .map(
      ([label, error], i) =>
        `${i + 1}. \`${label}\` (${error.includes("skipped") ? "✗ no key" : "✓ key set"}): ${error}`,
    )
    .join("\n")}`;
}

describe("buildErrorMessage classification", () => {
  it("does NOT report an auth error when the only real failure is a retired model", () => {
    const error = failureSummary([
      [
        "gemini/gemini-2.5-flash-lite",
        'LLM API error: {"error":{"code":404,"status":"NOT_FOUND","message":"This model models/gemini-2.5-flash-lite is no longer available to new users. Please update your code to use models/gemini-3.5-flash-lite."}}',
      ],
      [
        "groq/llama-3.3-70b-versatile",
        "skipped — no API key configured (needs GROQ_API_KEY secret)",
      ],
      ["cerebras/llama-3.3-70b", "skipped — no API key configured (needs CEREBRAS_API_KEY secret)"],
    ]);

    const comment = buildErrorMessage(makeResult(error), "gemini", error, makeConfig());

    expect(comment).not.toContain("Authentication error (403/401)");
    expect(comment).toContain("no longer exists (HTTP 404)");
    expect(comment).toContain("gemini-3.5-flash-lite");
    expect(comment).toContain("model_not_found");
  });

  it("reports a genuine 429 as a rate limit", () => {
    const error = failureSummary([
      [
        "gemini/gemini-3.8-flash",
        'LLM API error: {"error":{"code":429,"status":"RESOURCE_EXHAUSTED","message":"Quota exceeded for metric: ... limit: 5 ... Please retry in 43.8s."}}',
      ],
      [
        "groq/llama-3.3-70b-versatile",
        "skipped — no API key configured (needs GROQ_API_KEY secret)",
      ],
    ]);

    const comment = buildErrorMessage(makeResult(error), "gemini", error, makeConfig());

    expect(comment).not.toContain("Authentication error (403/401)");
    expect(comment).toContain("Rate limited");
    expect(comment).toContain("rate_limit");
  });

  it("still reports a real rejected credential as an auth error", () => {
    const error = failureSummary([
      ["gemini/gemini-3.5-flash-lite", "Gemini API error (403): API key not valid"],
      [
        "groq/llama-3.3-70b-versatile",
        "skipped — no API key configured (needs GROQ_API_KEY secret)",
      ],
    ]);

    const comment = buildErrorMessage(makeResult(error), "gemini", error, makeConfig());

    expect(comment).toContain("Authentication error (401/403)");
    expect(comment).toContain("x-goog-api-key");
  });

  it("reports a missing secret when every provider was skipped", () => {
    const error = failureSummary([
      [
        "groq/llama-3.3-70b-versatile",
        "skipped — no API key configured (needs GROQ_API_KEY secret)",
      ],
      ["cerebras/llama-3.3-70b", "skipped — no API key configured (needs CEREBRAS_API_KEY secret)"],
    ]);

    const comment = buildErrorMessage(makeResult(error), "groq", error, makeConfig());

    expect(comment).not.toContain("Authentication error (403/401)");
    expect(comment).toContain("No API keys found");
  });

  it("redacts credentials that a provider echoed back", () => {
    const secret = "AQ.example-secret-value-1234";
    const error = failureSummary([
      [
        "gemini/gemini-3.5-flash-lite",
        `Gemini API error (400): bad header x-goog-api-key: ${secret}`,
      ],
      [
        "groq/llama-3.3-70b-versatile",
        "skipped — no API key configured (needs GROQ_API_KEY secret)",
      ],
    ]);

    const comment = buildErrorMessage(makeResult(error), "gemini", error, makeConfig());

    expect(comment).not.toContain(secret);
    expect(comment).toContain("***");
  });

  it("includes a per-provider diagnosis with retryability", () => {
    const error = failureSummary([
      [
        "gemini/gemini-3.8-flash",
        '{"error":{"code":503,"status":"UNAVAILABLE","message":"high demand"}}',
      ],
      [
        "groq/llama-3.3-70b-versatile",
        "skipped — no API key configured (needs GROQ_API_KEY secret)",
      ],
    ]);

    const comment = buildErrorMessage(makeResult(error), "gemini", error, makeConfig());

    expect(comment).toContain("Diagnosis");
    expect(comment).toContain("overloaded");
    expect(comment).toContain("retryable");
  });
});
