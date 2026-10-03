/**
 * The agent-mode failure was `404 NOT_FOUND` for `gemini-2.5-flash-lite`
 * ("no longer available to new users"). The provider must catch that class of
 * misconfiguration before a run instead of surfacing it as an auth error.
 */
import { describe, expect, it } from "vitest";
import {
  GEMINI_DEFAULT_MODELS,
  GEMINI_RETIRED_MODELS,
  checkGeminiModel,
  geminiModelWarnings,
  geminiProvider,
} from "../../src/providers/gemini.ts";

describe("checkGeminiModel", () => {
  it("accepts the current free-tier Flash-Lite models", () => {
    expect(checkGeminiModel("gemini-3.5-flash-lite").ok).toBe(true);
    expect(checkGeminiModel("gemini-flash-lite-latest").ok).toBe(true);
  });

  it("rejects the retired model that caused the 404, and names its replacement", () => {
    const status = checkGeminiModel("gemini-2.5-flash-lite");
    expect(status.ok).toBe(false);
    expect(status.retired).toBe(true);
    expect(status.replacement).toBe("gemini-3.5-flash-lite");
    expect(status.error).toContain("404");
  });

  it("strips a models/ prefix", () => {
    expect(checkGeminiModel("models/gemini-2.5-flash").retired).toBe(true);
  });

  it("flags paid-only models without failing them", () => {
    const status = checkGeminiModel("gemini-3-pro-preview");
    expect(status.ok).toBe(true);
    expect(status.paidOnly).toBe(true);
    expect(status.warning).toContain("paid");
  });

  it("allows unknown ids (Google ships new models faster than we update) but warns", () => {
    const status = checkGeminiModel("gemini-9-experimental");
    expect(status.ok).toBe(true);
    expect(status.warning).toContain("not in IssueClaw's known-good list");
  });

  it("maps every retired id to a model that is itself available", () => {
    expect(Object.keys(GEMINI_RETIRED_MODELS).length).toBeGreaterThan(0);
    for (const [retired, replacement] of Object.entries(GEMINI_RETIRED_MODELS)) {
      expect(retired).not.toBe(replacement);
      // The replacement must not be another retired id.
      const status = checkGeminiModel(replacement);
      expect(status.ok).toBe(true);
      expect(status.retired).toBeUndefined();
    }
  });

  it("keeps the recommended defaults current", () => {
    for (const model of GEMINI_DEFAULT_MODELS) {
      expect(checkGeminiModel(model).retired).toBeUndefined();
    }
  });

  it("surfaces warnings for doctor/preflight", () => {
    expect(geminiModelWarnings("gemini-2.5-flash-lite")[0]).toContain("gemini-3.5-flash-lite");
    expect(geminiModelWarnings("gemini-flash-lite-latest")).toEqual([]);
  });
});

describe("geminiProvider.buildArgs", () => {
  it("passes the key through the environment, never as a CLI argument", () => {
    const built = geminiProvider.buildArgs({
      type: "gemini",
      model: "gemini-3.5-flash-lite",
      apiKey: "AQ.example-key-value",
    });

    expect(built.args).toEqual(["--provider", "google", "--model", "gemini-3.5-flash-lite"]);
    expect(built.env.GEMINI_API_KEY).toBe("AQ.example-key-value");
    // The key must never appear in the process command line (visible in ps).
    expect(built.args.join(" ")).not.toContain("AQ.example-key-value");
  });

  it("unsets GOOGLE_API_KEY so it cannot shadow the configured secret", () => {
    const built = geminiProvider.buildArgs({
      type: "gemini",
      model: "gemini-3.5-flash-lite",
      apiKey: "AQ.example-key-value",
    });
    expect(built.env).toHaveProperty("GOOGLE_API_KEY", undefined);
  });

  it("forwards the thinking level", () => {
    const built = geminiProvider.buildArgs({
      type: "gemini",
      model: "gemini-3.8-flash",
      apiKey: "AQ.example-key-value",
      thinking: "high",
    });
    expect(built.args).toContain("--thinking");
  });
});

describe("geminiProvider.validate", () => {
  it("requires a key", () => {
    expect(geminiProvider.validate({ type: "gemini", model: "gemini-3.5-flash-lite" })).toContain(
      "GEMINI_API_KEY",
    );
  });

  it("fails fast on a retired model with an actionable message", () => {
    const error = geminiProvider.validate({
      type: "gemini",
      model: "gemini-2.5-flash-lite",
      apiKey: "AQ.example-key-value",
    });
    expect(error).toContain("retired");
    expect(error).toContain("gemini-3.5-flash-lite");
  });

  it("accepts a current model", () => {
    expect(
      geminiProvider.validate({
        type: "gemini",
        model: "gemini-3.5-flash-lite",
        apiKey: "AQ.example-key-value",
      }),
    ).toBeNull();
  });
});
