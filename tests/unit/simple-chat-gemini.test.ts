/**
 * Chat mode sent the Gemini key as a `?key=` query parameter, which the
 * current AI Studio `AQ.` "auth" keys do not accept (and which leaks the
 * secret into URLs/logs). It also read only `parts[0].text`, which returns an
 * empty string for reasoning models that emit thought parts first.
 */
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  extractGeminiText,
  geminiGenerateContentUrl,
  runSimpleChat,
} from "../../src/agent/simple-chat.ts";
import type { IssueClawConfig, ProviderConfig } from "../../src/config.ts";
import { MemoryStore } from "../../src/memory/store.ts";

const mockFetch = vi.fn();
globalThis.fetch = mockFetch as unknown as typeof globalThis.fetch;

let stateDir: string;
let memory: MemoryStore;

function makeTestConfig(providers: ProviderConfig[]): IssueClawConfig {
  return {
    version: 1,
    providers,
    memory: {
      stateDir,
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
    runtime: { dryRun: false, logLevel: "error", logJson: false, offline: false },
  };
}

function makeEvent() {
  return {
    type: "issues.opened" as const,
    rawName: "issues",
    issueNumber: 1,
    title: "Hello",
    issueBody: "What is 2+2?",
    body: "What is 2+2?",
    author: "testuser",
    authorAssociation: "OWNER",
    isBot: false,
    labels: [] as string[],
    raw: {},
  };
}

beforeEach(() => {
  stateDir = mkdtempSync(join(tmpdir(), "issueclaw-test-"));
  memory = new MemoryStore(makeTestConfig([]).memory);
  mockFetch.mockReset();
});

afterEach(() => {
  rmSync(stateDir, { recursive: true, force: true });
});

describe("geminiGenerateContentUrl", () => {
  it("never embeds the API key in the URL", () => {
    const url = geminiGenerateContentUrl("gemini-3.5-flash-lite");
    expect(url).toBe(
      "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent",
    );
    expect(url).not.toContain("key=");
  });
});

describe("extractGeminiText", () => {
  it("joins multiple answer parts", () => {
    expect(
      extractGeminiText({
        candidates: [{ content: { parts: [{ text: "Hello " }, { text: "world" }] } }],
      }),
    ).toBe("Hello world");
  });

  it("skips internal thought parts", () => {
    expect(
      extractGeminiText({
        candidates: [
          {
            content: {
              parts: [{ text: "let me think…", thought: true }, { text: "The answer is 4." }],
            },
          },
        ],
      }),
    ).toBe("The answer is 4.");
  });

  it("returns an empty string when only thoughts were produced", () => {
    expect(
      extractGeminiText({
        candidates: [{ content: { parts: [{ text: "thinking", thought: true }] } }],
      }),
    ).toBe("");
  });
});

describe("runSimpleChat with Gemini", () => {
  it("authenticates with the x-goog-api-key header and keeps the key out of the URL", async () => {
    const apiKey = "AQ.example-auth-key-value";
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        candidates: [{ content: { parts: [{ text: "2 + 2 = 4" }] } }],
        usageMetadata: { totalTokenCount: 30 },
      }),
      text: async () => "",
    });

    const config = makeTestConfig([
      { type: "gemini", model: "gemini-3.5-flash-lite", apiKey, default: true },
    ]);

    const result = await runSimpleChat({ config, memory, event: makeEvent() });

    expect(result.success).toBe(true);
    expect(result.response).toBe("2 + 2 = 4");

    const [url, init] = mockFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/v1beta/models/gemini-3.5-flash-lite:generateContent");
    expect(url).not.toContain(apiKey);
    expect(url).not.toContain("?key=");
    expect((init.headers as Record<string, string>)["x-goog-api-key"]).toBe(apiKey);

    const body = JSON.parse(String(init.body));
    expect(body.systemInstruction.parts[0].text.length).toBeGreaterThan(0);
    // Reasoning models burn the output budget on thinking, so the default must
    // be generous enough to leave room for an answer.
    expect(body.generationConfig.maxOutputTokens).toBeGreaterThanOrEqual(8192);
  });

  it("reports a retired model as a model problem, not an auth problem", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 404,
      headers: new Headers(),
      text: async () =>
        '{"error":{"code":404,"status":"NOT_FOUND","message":"This model models/gemini-2.5-flash-lite is no longer available to new users. Please update your code to use models/gemini-3.5-flash-lite."}}',
    });

    const config = makeTestConfig([
      { type: "gemini", model: "gemini-2.5-flash-lite", apiKey: "AQ.example-key", default: true },
    ]);

    const result = await runSimpleChat({ config, memory, event: makeEvent() });

    expect(result.success).toBe(false);
    expect(result.error).toContain("404");
    expect(result.error).not.toMatch(/unauthorized|forbidden/i);
    // 404 must not be retried — it is deterministic.
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it("retries a 429 using the provider's requested delay", async () => {
    vi.useFakeTimers();
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 429,
      headers: new Headers({ "retry-after": "0" }),
      text: async () =>
        '{"error":{"code":429,"status":"RESOURCE_EXHAUSTED","message":"Please retry in 0.05s."}}',
    });
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        candidates: [{ content: { parts: [{ text: "recovered" }] } }],
        usageMetadata: { totalTokenCount: 5 },
      }),
      text: async () => "",
    });

    const config = makeTestConfig([
      { type: "gemini", model: "gemini-3.5-flash-lite", apiKey: "AQ.example-key", default: true },
    ]);

    const pending = runSimpleChat({ config, memory, event: makeEvent() });
    // Default backoff is 5s (+jitter), so advance past the retry window.
    await vi.advanceTimersByTimeAsync(70_000);
    const result = await pending;

    expect(result.success).toBe(true);
    expect(result.response).toBe("recovered");
    expect(mockFetch).toHaveBeenCalledTimes(2);
    vi.useRealTimers();
  });

  it("never prints the API key in the aggregated failure report", async () => {
    const apiKey = "AQ.do-not-leak-me-0123456789";
    mockFetch.mockResolvedValue({
      ok: false,
      status: 403,
      headers: new Headers(),
      text: async () => `{"error":{"code":403,"message":"API key not valid: ${apiKey}"}}`,
    });

    const config = makeTestConfig([
      { type: "gemini", model: "gemini-3.5-flash-lite", apiKey, default: true },
      { type: "groq", model: "llama-3.3-70b-versatile", apiKey: "${GROQ_API_KEY}" },
    ]);

    const result = await runSimpleChat({ config, memory, event: makeEvent() });

    expect(result.success).toBe(false);
    expect(result.error).not.toContain(apiKey);
    expect(result.error).toContain("***");
  });
});
