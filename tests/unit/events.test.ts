/**
 * Regression tests for event parsing.
 *
 * A comment-triggered run must still see the issue description: the read-only
 * policy check and the task prompt both depend on it (issue #2 carries its
 * "do NOT modify any files" instruction in the issue body, while the run is
 * triggered by a comment).
 */
import { describe, expect, it } from "vitest";
import { parseEvent } from "../../src/github/events.ts";

const issuePayload = {
  action: "created",
  issue: {
    number: 2,
    title: "Investigate component save bug",
    body: "Do NOT modify any files.\nTrace the save flow and report the failure point.",
    user: { login: "ahmadtefa" },
    author_association: "OWNER",
    labels: [{ name: "agent" }],
  },
  comment: {
    id: 1234,
    body: "Please investigate.",
    user: { login: "ahmadtefa" },
    author_association: "OWNER",
  },
};

describe("parseEvent", () => {
  it("keeps the issue body when the run was triggered by a comment", () => {
    const event = parseEvent("/dev/null", "issue_comment", JSON.stringify(issuePayload));

    expect(event.type).toBe("issue_comment.created");
    expect(event.issueNumber).toBe(2);
    expect(event.title).toBe("Investigate component save bug");
    // The comment is the instruction...
    expect(event.body).toBe("Please investigate.");
    // ...but the issue description is still available verbatim.
    expect(event.issueBody).toContain("Do NOT modify any files.");
  });

  it("exposes the issue body as `body` for issues.opened", () => {
    const event = parseEvent(
      "/dev/null",
      "issues",
      JSON.stringify({
        action: "opened",
        issue: { ...issuePayload.issue, number: 7 },
      }),
    );

    expect(event.type).toBe("issues.opened");
    expect(event.issueNumber).toBe(7);
    expect(event.body).toBe(event.issueBody);
    expect(event.body).toContain("Do NOT modify any files.");
  });

  it("treats a missing issue body as empty", () => {
    const event = parseEvent(
      "/dev/null",
      "issue_comment",
      JSON.stringify({
        action: "created",
        issue: { number: 3, title: "t", body: null, user: { login: "u" } },
        comment: { id: 1, body: "go", user: { login: "u" } },
      }),
    );

    expect(event.issueBody).toBe("");
  });
});
