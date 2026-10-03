/**
 * Requirement under test: a task that says "Do NOT modify any files" must not
 * be able to change application code — regardless of what the model decides.
 */
import { describe, expect, it } from "vitest";
import {
  detectReadOnlyRequest,
  parsePorcelainPaths,
  planCommitScope,
} from "../../src/utils/policy.ts";

describe("detectReadOnlyRequest", () => {
  it("detects the read-only wording used by the component-save investigation", () => {
    expect(detectReadOnlyRequest("Do NOT modify any files.\nDo NOT commit or push anything.")).toBe(
      true,
    );
  });

  it("detects common read-only phrasings", () => {
    const positives = [
      "do not change any code",
      "Don't edit any source files, just report.",
      "Please investigate without modifying any files.",
      "Read-only investigation of the save flow.",
      "Investigate only; produce a report.",
      "We need an analysis with no file changes.",
      "Do NOT modify any application code under lib/.",
      "Do not edit any source files.",
    ];
    for (const text of positives) {
      expect(detectReadOnlyRequest(text), text).toBe(true);
    }
  });

  it("does not fire on a task that forbids one specific change", () => {
    const negatives = [
      "Do not modify the database schema, but fix the component form.",
      "Fix the save bug; don't touch the migrations directory only.",
      "Implement the feature and update the docs.",
      "",
    ];
    for (const text of negatives) {
      expect(detectReadOnlyRequest(text), text).toBe(false);
    }
  });
});

describe("parsePorcelainPaths", () => {
  it("parses modified, untracked and renamed entries", () => {
    const status = [
      " M lib/features/designs/data/models/component.dart",
      "?? state/sessions/new.jsonl",
      "R  old/name.dart -> lib/features/new_name.dart",
      ' M "path with spaces/file.dart"',
    ].join("\n");

    expect(parsePorcelainPaths(status)).toEqual([
      "lib/features/designs/data/models/component.dart",
      "state/sessions/new.jsonl",
      "lib/features/new_name.dart",
      "path with spaces/file.dart",
    ]);
  });

  it("returns nothing for a clean tree", () => {
    expect(parsePorcelainPaths("")).toEqual([]);
    expect(parsePorcelainPaths("\n")).toEqual([]);
  });
});

describe("planCommitScope", () => {
  const dirtyTree = [
    " M lib/features/designs/presentation/screens/component_form_screen.dart",
    " M lib/core/database/database_helper.dart",
    " M state/memory.md",
    " M state/issues/2.json",
  ].join("\n");

  it("stages everything for a normal run", () => {
    const scope = planCommitScope(dirtyTree, false);
    expect(scope.paths).toEqual(["-A"]);
    expect(scope.restricted).toBe(false);
    expect(scope.skipped).toEqual([]);
  });

  it("stages only state/ for a read-only run and reports what is skipped", () => {
    const scope = planCommitScope(dirtyTree, true);
    expect(scope.paths).toEqual(["state/"]);
    expect(scope.restricted).toBe(true);
    expect(scope.skipped).toEqual([
      "lib/features/designs/presentation/screens/component_form_screen.dart",
      "lib/core/database/database_helper.dart",
    ]);
    // Application code is never staged.
    expect(scope.paths.join(" ")).not.toContain("lib/");
  });

  it("does not flag anything when a read-only run touched only state", () => {
    const scope = planCommitScope(" M state/memory.md", true);
    expect(scope.skipped).toEqual([]);
  });
});
