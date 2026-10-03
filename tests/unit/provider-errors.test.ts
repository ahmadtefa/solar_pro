/**
 * Regression tests for the failure that caused the reported incident:
 * IssueClaw reported "Authentication error (403/401)" for runs whose real
 * errors were an unhelpful "empty response" and a retired-model HTTP 404.
 */
import { describe, expect, it } from "vitest";
import {
  classifyProviderError,
  collectSecrets,
  describeCredential,
  extractHttpStatus,
  hasUsableSecret,
  parseRetryDelayMs,
  providerErrorHint,
  redactSecrets,
} from "../../src/utils/errors.ts";
import { isRetryableHttpError, retryAfterMsFor } from "../../src/utils/retry.ts";

// Real bodies captured from the failing GitHub Actions runs.
const GEMINI_429_RPM = `Gemini API error (429): {
  "error": {
    "code": 429,
    "message": "You exceeded your current quota, please check your plan and billing details. \\
* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, \\
limit: 5, model: gemini-3.8-flash\\nPlease retry in 43.835229498s.",
    "status": "RESOURCE_EXHAUSTED"
  }
}`;

const GEMINI_503 = `{"error":{"message":"{\\n  \\"error\\": {\\n    \\"code\\": 503,\\n    \\"message\\": \\"This model is currently experiencing high demand. Spikes in demand are usually temporary. Please try again later.\\",\\n    \\"status\\": \\"UNAVAILABLE\\"\\n  }\\n}\\n","code":503,"status":"Service Unavailable"}}`;

const GEMINI_404_RETIRED = `Gemini API error (404): {
  "error": {
    "code": 404,
    "message": "This model models/gemini-2.5-flash-lite is no longer available to new users. \\
Please update your code to use models/gemini-3.5-flash-lite for the latest features and improvements.",
    "status": "NOT_FOUND"
  }
}`;

describe("extractHttpStatus", () => {
  it("reads JSON-ish codes, HTTP prefixes, and parenthesised codes", () => {
    expect(extractHttpStatus(GEMINI_429_RPM)).toBe(429);
    expect(extractHttpStatus("LLM API error (503): upstream unavailable")).toBe(503);
    expect(extractHttpStatus("HTTP 404 Not Found")).toBe(404);
  });
});

describe("parseRetryDelayMs", () => {
  it("parses Gemini's retryDelay and human hint", () => {
    expect(parseRetryDelayMs('"retryDelay": "43.8s"')).toBe(43800);
    expect(parseRetryDelayMs("Please retry in 43.835229498s.")).toBe(43835);
  });

  it("parses HTTP Retry-After headers", () => {
    expect(parseRetryDelayMs("LLM API error (429) retry-after: 30: body")).toBe(30000);
  });

  it("returns undefined when no hint exists", () => {
    expect(parseRetryDelayMs("something went wrong")).toBeUndefined();
  });
});

describe("classifyProviderError", () => {
  it("classifies a free-tier 429 as a retryable rate limit", () => {
    const info = classifyProviderError(GEMINI_429_RPM);
    expect(info.kind).toBe("rate_limit");
    expect(info.retryable).toBe(true);
    expect(info.httpStatus).toBe(429);
    expect(info.model).toBe("gemini-3.8-flash");
    expect(info.retryAfterMs).toBe(43835);
  });

  it("classifies Gemini UNAVAILABLE as a retryable overload", () => {
    const info = classifyProviderError(GEMINI_503);
    expect(info.kind).toBe("overloaded");
    expect(info.retryable).toBe(true);
  });

  it("classifies a retired model 404 as fatal, with the suggested replacement", () => {
    const info = classifyProviderError(GEMINI_404_RETIRED);
    expect(info.kind).toBe("model_not_found");
    expect(info.retryable).toBe(false);
    expect(info.model).toBe("gemini-2.5-flash-lite");
    expect(info.suggestedModel).toBe("gemini-3.5-flash-lite");
  });

  it("classifies rejected credentials as fatal auth errors", () => {
    for (const message of [
      "Gemini API error (403): API key not valid. Please pass a valid API key.",
      "LLM API error (401): invalid_api_key",
      '{"error":{"code":403,"status":"PERMISSION_DENIED"}}',
    ]) {
      const info = classifyProviderError(message);
      expect(info.kind).toBe("auth");
      expect(info.retryable).toBe(false);
    }
  });

  it("classifies a daily quota exhaustion as fatal, and per-minute as retryable", () => {
    const daily = classifyProviderError(
      '{"code":429,"status":"RESOURCE_EXHAUSTED","message":"Quota exceeded ... per day"}',
    );
    expect(daily.kind).toBe("quota_exhausted");
    expect(daily.retryable).toBe(false);

    const perMinute = classifyProviderError(
      '{"code":429,"status":"RESOURCE_EXHAUSTED","message":"limit: 15 per minute"}',
    );
    expect(perMinute.kind).toBe("rate_limit");
    expect(perMinute.retryable).toBe(true);
  });

  it("classifies transport failures as retryable network errors", () => {
    expect(classifyProviderError(new Error("fetch failed")).kind).toBe("network");
    expect(classifyProviderError(new Error("socket hang up")).retryable).toBe(true);
  });

  it("does not retry unclassified errors", () => {
    expect(classifyProviderError("weird provider noise").retryable).toBe(false);
  });

  it("distinguishes 'no API key configured' from a rejected key", () => {
    // The old lifecycle regex matched /API key/i here and claimed 403/401.
    const skipped = classifyProviderError("skipped — no API key configured (needs GROQ_API_KEY)");
    expect(skipped.kind).not.toBe("auth");
  });

  it("exposes hints that never contain credentials", () => {
    const hint = providerErrorHint(classifyProviderError(GEMINI_404_RETIRED), "gemini");
    expect(hint).toContain("gemini-3.5-flash-lite");
    expect(hint).not.toMatch(/AQ\.|AIza/);
  });
});

describe("retry helpers", () => {
  it("retries transient errors only", () => {
    expect(isRetryableHttpError(new Error(GEMINI_429_RPM))).toBe(true);
    expect(isRetryableHttpError(new Error(GEMINI_503))).toBe(true);
    expect(isRetryableHttpError(new Error(GEMINI_404_RETIRED))).toBe(false);
    expect(isRetryableHttpError(new Error("API key not valid"))).toBe(false);
  });

  it("surfaces the provider's requested back-off", () => {
    expect(retryAfterMsFor(new Error(GEMINI_429_RPM))).toBe(43835);
    expect(retryAfterMsFor(new Error("nope"))).toBeUndefined();
  });
});

describe("redactSecrets", () => {
  const key = "AQ.Ab8RN6J-example-auth-key-value-1234567890";

  it("removes exact secret values", () => {
    expect(redactSecrets(`request failed for ${key}`, [key])).not.toContain(key);
  });

  it("removes credential-shaped strings even when the exact value is unknown", () => {
    const redacted = redactSecrets(
      "key=AIzaSyD-EXAMPLE-LEGACY-KEY-000 & token=ghp_abcdefghijklmnopqrstuvwx",
    );
    expect(redacted).not.toContain("AIzaSyD-EXAMPLE");
    expect(redacted).not.toContain("ghp_abcdefghijklmnopqrstuvwx");
  });

  it("scrubs keys used as URL query parameters", () => {
    const redacted = redactSecrets(
      "https://generativelanguage.googleapis.com/v1beta/models/x:generateContent?key=AQ.secretvalue123",
    );
    expect(redacted).toContain("key=***");
    expect(redacted).not.toContain("AQ.secretvalue123");
  });

  it("collects only resolved secrets from a provider list", () => {
    const secrets = collectSecrets([
      { apiKey: "resolved-secret-123" },
      { apiKey: "${GEMINI_API_KEY}" },
      { apiKey: undefined },
    ]);
    expect(secrets).toEqual(["resolved-secret-123"]);
  });
});

describe("describeCredential", () => {
  it("identifies the new AI Studio auth key format", () => {
    expect(describeCredential("AQ.Ab8RN6Jexamplekeyvalue")).toContain("auth key (AQ.");
  });

  it("identifies legacy keys and warns about whitespace", () => {
    expect(describeCredential("AIzaSyExampleKeyValue")).toContain("legacy standard key");
    expect(describeCredential("AIzaSyExampleKeyValue\n")).toContain("whitespace");
  });

  it("never echoes the key material", () => {
    const description = describeCredential("AQ.SUPERSECRETVALUE1234");
    expect(description).not.toContain("SUPERSECRETVALUE");
  });

  it("flags unresolved references and empties", () => {
    expect(hasUsableSecret("${GEMINI_API_KEY}")).toBe(false);
    expect(hasUsableSecret("")).toBe(false);
    expect(hasUsableSecret("   ")).toBe(false);
    expect(hasUsableSecret("AQ.realkeyvalue")).toBe(true);
  });
});

describe("redactConfig (issueclaw config show)", () => {
  it("replaces resolved credentials with a placeholder", async () => {
    const { redactConfig } = await import("../../src/config.ts");
    const fakeConfig = {
      version: 1 as const,
      providers: [
        {
          type: "gemini" as const,
          model: "gemini-3.5-flash-lite",
          apiKey: "AQ.real-secret-value",
          default: true,
        },
        { type: "groq" as const, model: "llama-3.3-70b-versatile", apiKey: undefined },
      ],
      memory: {
        stateDir: "./state",
        memoryFile: "memory.md",
        personalityFile: "personality.md",
        userFile: "user.md",
        auditFile: "audit.log",
        maxSessionSize: 1,
        autoCompact: true,
      },
      github: {
        onIssueOpened: true,
        onIssueComment: true,
        onPullRequest: false,
        allowedAssociations: ["OWNER"],
        hatchLabel: "hatch",
        reactionWhileProcessing: true,
        maxCommentLength: 60000,
        concurrencyGroup: "x",
      },
      agent: {
        piCommand: "bunx pi",
        timeoutMs: 1000,
        skills: false,
        extensions: false,
        appendSystemPrompt: ".pi/APPEND_SYSTEM.md",
        agentsFile: "AGENTS.md",
      },
      runtime: { dryRun: false, logLevel: "info" as const, logJson: false, offline: false },
    };

    const output = JSON.stringify(redactConfig(fakeConfig));
    expect(output).not.toContain("AQ.real-secret-value");
    expect(output).toContain("***redacted***");
  });
});

describe("agent retry decision", () => {
  it("retries transient provider failures only, within the attempt budget", async () => {
    const { shouldRetryProviderFailure } = await import("../../src/agent/runner.ts");

    expect(shouldRetryProviderFailure(GEMINI_503, 1, 3)).toBe(true);
    expect(shouldRetryProviderFailure(GEMINI_429_RPM, 2, 3)).toBe(true);

    // Fatal: rejected key and retired model.
    expect(shouldRetryProviderFailure("Gemini API error (403): API key not valid", 1, 3)).toBe(
      false,
    );
    expect(shouldRetryProviderFailure(GEMINI_404_RETIRED, 1, 3)).toBe(false);

    // Attempt budget exhausted.
    expect(shouldRetryProviderFailure(GEMINI_503, 3, 3)).toBe(false);
  });
});
