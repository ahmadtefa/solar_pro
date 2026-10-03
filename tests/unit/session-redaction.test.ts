import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { MemoryStore } from "../../src/memory/store.ts";
import { collectSecrets, redactSecrets } from "../../src/utils/errors.ts";

describe("IssueClaw session & state secret redaction", () => {
  let tempDir: string;

  beforeEach(() => {
    tempDir = mkdtempSync(join(tmpdir(), "issueclaw-redaction-test-"));
  });

  afterEach(() => {
    rmSync(tempDir, { recursive: true, force: true });
  });

  it("collects resolved secrets from both provider configs and environment variables", () => {
    const secrets = collectSecrets(
      [{ apiKey: "test-provider-secret-value-12345" }, { apiKey: "${UNRESOLVED_KEY}" }],
      {
        GEMINI_API_KEY: "test-env-gemini-secret-98765",
        GITHUB_TOKEN: "test-env-github-token-54321",
        NORMAL_VAR: "visible-non-secret-value",
      },
    );

    expect(secrets).toContain("test-provider-secret-value-12345");
    expect(secrets).toContain("test-env-gemini-secret-98765");
    expect(secrets).toContain("test-env-github-token-54321");
    expect(secrets).not.toContain("visible-non-secret-value");
    expect(secrets).not.toContain("${UNRESOLVED_KEY}");
  });

  it("redacts GEMINI_API_KEY assignments, x-goog-api-key headers, and AQ./AIza shapes", () => {
    const fakeGeminiSecret = "my-custom-gemini-secret-value-xyz123";
    const sample = [
      `env output: GEMINI_API_KEY=${fakeGeminiSecret}`,
      'header: "x-goog-api-key": "AQ.test_fake_studio_token.part2_999"',
      "url: https://generativelanguage.googleapis.com/v1beta/models?key=testQuerySecret999",
    ].join("\n");

    const scrubbed = redactSecrets(sample, [fakeGeminiSecret]);
    expect(scrubbed).not.toContain(fakeGeminiSecret);
    expect(scrubbed).not.toContain("AQ.test_fake_studio_token.part2_999");
    expect(scrubbed).not.toContain("testQuerySecret999");
    expect(scrubbed).toContain("***");
  });

  it("scrubs state/sessions/*.jsonl in-place before mapping save and state persistence", () => {
    const fakeSecret = "super-sensitive-gemini-secret-000111222";
    const store = new MemoryStore(
      {
        stateDir: tempDir,
        memoryFile: "memory.md",
        personalityFile: "personality.md",
        userFile: "user.md",
        auditFile: "audit.log",
        maxSessionSize: 1000000,
        autoCompact: true,
      },
      [fakeSecret],
    );
    store.init();

    const sessionPath = store.getSessionPath("2026-10-03T12-00-00_test.jsonl");
    const rawJsonl = [
      JSON.stringify({
        type: "session",
        version: 3,
        id: "test-session",
      }),
      JSON.stringify({
        type: "message",
        message: {
          role: "toolResult",
          toolName: "bash",
          content: [{ type: "text", text: `GEMINI_API_KEY=${fakeSecret}\nother=ok` }],
        },
      }),
      JSON.stringify({
        type: "message",
        message: {
          role: "assistant",
          stopReason: "error",
          errorMessage: `API key rejected: ${fakeSecret} (AQ.fake_studio_token_abcdef12345)`,
        },
      }),
    ].join("\n");

    writeFileSync(sessionPath, `${rawJsonl}\n`, "utf-8");

    // Saving mapping automatically scrubs the referenced session file on disk
    store.saveMapping({
      issueNumber: 2,
      sessionPath,
      createdAt: "2026-10-03T12:00:00.000Z",
      updatedAt: "2026-10-03T12:00:01.000Z",
      turnCount: 1,
    });

    const persistedSession = readFileSync(sessionPath, "utf-8");
    expect(persistedSession).not.toContain(fakeSecret);
    expect(persistedSession).not.toContain("AQ.fake_studio_token_abcdef12345");
    expect(persistedSession).toContain("other=ok");

    // Memory and audit writes also scrub secrets before persisting
    store.appendMemory(`Checked provider with key ${fakeSecret}`);
    store.appendAudit("agent_error", { detail: `Key ${fakeSecret} failed` });

    expect(store.readMemory()).not.toContain(fakeSecret);
    expect(store.readAudit()).not.toContain(fakeSecret);
  });

  it("redactAllStateFiles scrubs all session files and state markdown files", () => {
    const fakeSecret = "another-gemini-secret-value-888777666";
    const store = new MemoryStore(
      {
        stateDir: tempDir,
        memoryFile: "memory.md",
        personalityFile: "personality.md",
        userFile: "user.md",
        auditFile: "audit.log",
        maxSessionSize: 1000000,
        autoCompact: true,
      },
      [],
    );
    store.init();

    const s1 = store.getSessionPath("s1.jsonl");
    const s2 = store.getSessionPath("s2.jsonl");
    writeFileSync(s1, `{"err":"${fakeSecret}"}\n`, "utf-8");
    writeFileSync(s2, '{"ok":true}\n', "utf-8");
    writeFileSync(store.memoryFilePath, `Note: ${fakeSecret}\n`, "utf-8");

    const modifiedCount = store.redactAllStateFiles([fakeSecret]);
    expect(modifiedCount).toBe(2);
    expect(readFileSync(s1, "utf-8")).not.toContain(fakeSecret);
    expect(readFileSync(store.memoryFilePath, "utf-8")).not.toContain(fakeSecret);
  });
});
