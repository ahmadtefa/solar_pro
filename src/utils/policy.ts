/**
 * Run-scoped policies derived from the task text.
 *
 * IssueClaw can edit files and commit them, which is the point of agent mode.
 * However, users frequently ask for an investigation only ("Do NOT modify any
 * files"). When that instruction is present we must guarantee it — relying on
 * the model to obey is not a guarantee.
 *
 * The detector is deliberately narrow. It only fires on explicit, unambiguous
 * read-only instructions, so a task that merely forbids one specific change
 * ("do not modify the database schema, but fix the form") is unaffected.
 */

/** Patterns that unambiguously request a read-only run. */
const READ_ONLY_PATTERNS: RegExp[] = [
  // "Do NOT modify any files." / "do not change any code" / "don't edit any source"
  /\bdo(?:es)?\s+not\s+(?:modify|change|edit|touch|apply)\s+any\s+(?:[a-z]+\s+)?(?:files?|code|source|sources)\b/i,
  /\bdo(?:es)?n'?t\s+(?:modify|change|edit|touch|apply)\s+any\s+(?:[a-z]+\s+)?(?:files?|code|source|sources)\b/i,
  // "without modifying any files" / "no file changes"
  /\bwithout\s+(?:modifying|changing|editing)\s+(?:any\s+)?(?:[a-z]+\s+)?(?:files?|code|source|sources)\b/i,
  /\bno\s+(?:file|code|source)\s+changes\b/i,
  // "read-only investigation"
  /\bread[-\s]?only\b/i,
  // "investigate only" / "report only"
  /\b(?:investigate|report|review|analyse|analyze)\s+only\b/i,
];

/**
 * True when the task explicitly asks for a read-only/investigation run.
 *
 * @param text issue title + body, or comment body
 */
export function detectReadOnlyRequest(text: string): boolean {
  if (!text) return false;
  return READ_ONLY_PATTERNS.some((re) => re.test(text));
}

/** Paths that are always safe to commit: IssueClaw's own bookkeeping. */
export const STATE_PREFIX = "state/";

/**
 * Parse `git status --porcelain` output into a list of repository-relative
 * paths (renames are reported by their new path).
 */
export function parsePorcelainPaths(porcelain: string): string[] {
  const paths: string[] = [];
  for (const rawLine of porcelain.split("\n")) {
    const line = rawLine.trimEnd();
    if (!line) continue;
    // Format: XY <path> (or `XY <old> -> <new>` for renames/copies).
    const rest = line.slice(2).trim();
    if (!rest) continue;
    const arrow = rest.indexOf(" -> ");
    const path = arrow >= 0 ? rest.slice(arrow + 4) : rest;
    paths.push(path.replace(/^"(.*)"$/, "$1"));
  }
  return paths;
}

export interface CommitScope {
  /** Paths to stage. */
  paths: string[];
  /** True when changes outside `state/` must not be committed. */
  restricted: boolean;
  /** Changed paths that will be left uncommitted because of the restriction. */
  skipped: string[];
}

/**
 * Decide what may be staged for this run.
 *
 * - Default: stage everything (`git add -A`) — normal agent behaviour.
 * - Read-only request: stage only `state/` so application code cannot be
 *   modified by the run, no matter what the model decided to do.
 */
export function planCommitScope(statusOutput: string, readOnly: boolean): CommitScope {
  if (!readOnly) {
    return { paths: ["-A"], restricted: false, skipped: [] };
  }
  const changed = parsePorcelainPaths(statusOutput);
  const skipped = changed.filter((p) => !p.startsWith(STATE_PREFIX));
  return { paths: [STATE_PREFIX], restricted: true, skipped };
}
