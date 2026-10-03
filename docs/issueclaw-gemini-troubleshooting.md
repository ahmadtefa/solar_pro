# IssueClaw + Gemini: troubleshooting and root-cause notes

This document records the diagnosis of the failing `IssueClaw Agent` runs and the
guarantees the code now provides. It is written so that the next failure can be
identified in seconds instead of re-deriving the whole chain.

## Symptom history

| Run | Reported by IssueClaw | Real provider error |
| --- | --- | --- |
| chat mode | `Authentication error (403/401)` | `gemini`: **"Gemini returned empty response"** |
| agent mode | `Rate limit or quota exceeded (429)` | `gemini/gemini-3.8-flash`: 503 `UNAVAILABLE` ×2, then 429 `RESOURCE_EXHAUSTED` (`limit: 5`, "retry in 43.8s") |
| agent mode | `Authentication error (403/401)` | `gemini/gemini-2.5-flash-lite`: **404 `NOT_FOUND` — model retired**, "use `models/gemini-3.5-flash-lite`" |

The API key was valid in all three runs. Two of the three reports were
mis-diagnoses produced by IssueClaw itself.

## Root causes

### 1. The 403/401 report was a false positive (IssueClaw bug)

`buildErrorMessage()` (in `src/lifecycle/main.ts`) classified the failure by
regex-matching the **aggregated** multi-provider summary:

```ts
const isAuthError = /403|401|Forbidden|Unauthorized|API key|apiKey/i.test(errMsg);
```

The summary always contains a line per unconfigured fallback provider:

```
2. `groq/llama-3.3-70b-versatile` (✗ no key): skipped — no API key set (needs GROQ_API_KEY)
```

The substring `API key` therefore matched **every** run and the comment always
claimed "Authentication error (403/401)", masking the real 404 and "empty
response" errors.

**Fix:** the summary is now parsed into per-provider rows; only providers that
were actually attempted are classified, via `classifyProviderError()`
(`src/utils/errors.ts`), which distinguishes `auth`, `missing_credential`,
`model_not_found`, `rate_limit`, `quota_exhausted`, `overloaded`,
`request_too_large`, `blocked`, and `network`.

### 2. The default Gemini model had been retired

`gemini-2.5-flash-lite` now answers:

```
404 NOT_FOUND — This model models/gemini-2.5-flash-lite is no longer available
to new users. Please update your code to use models/gemini-3.5-flash-lite
```

**Fix:** `issueclaw.config.json` defaults to `gemini-3.5-flash-lite`, with
`gemini-flash-lite-latest` and `gemini-3.8-flash` as model-level fallbacks.
`GEMINI_RETIRED_MODELS` (`src/providers/gemini.ts`) lets validation fail fast with
the replacement id instead of burning a run on a guaranteed 404.

### 3. Chat mode used the obsolete query-parameter authentication

`callGemini()` built:

```
.../v1beta/models/{model}:generateContent?key=<API_KEY>
```

AI Studio now issues **auth-style keys with the `AQ.` prefix**. These are only
accepted through the `x-goog-api-key` header; the legacy `?key=` placement is why
new keys fail — and the key is additionally exposed to proxy logs, traces and
`process.args` (CWE-598).

**Fix:** chat mode sends `x-goog-api-key` (agent mode already did, because pi's
native `google` provider uses `@google/genai`, which uses the header). The
credential never appears in a URL or in a command line.

### 4. Chat mode could not read reasoning-model responses

It read only `parts[0].text` and used `maxOutputTokens: 8192`. Gemini 3.x models
emit thought parts and count thinking against the output budget, so this
produced the unhelpful "Gemini returned empty response".

**Fix:** all non-thought parts are concatenated, the output budget defaults to
32768, and an empty result now explains itself
(`MAX_TOKENS` → "exhausted the output budget on internal reasoning",
`blockReason` → safety block, etc.).

### 5. Transient 429/503s were never retried in CI

pi's auto-retry only exists in interactive/RPC modes — in
`--print --mode json` a single transient error aborts the run (the session log
shows two 503s and a 429 with zero retries). IssueClaw's `retry()` helper existed
but was never applied to the agent invocation, and its retry predicate did not
recognise `UNAVAILABLE`/`RESOURCE_EXHAUSTED` wording or the
`Please retry in 43.8s` hint.

**Fix:** agent mode retries transient failures (`ISSUECLAW_MAX_TRANSIENT_ATTEMPTS`,
default 3) with exponential backoff that honours the provider's requested delay,
resuming the pi session so completed tool calls are not repeated. Retries stay
inside the configured `agent.timeoutMs` budget. Chat mode retries four times with
the same back-off rules. 401/403/404/413 are never retried.

### 6. Credential handling hardened

* `issueclaw config show` printed the **resolved** API key (it substituted
  `${GEMINI_API_KEY}` before printing). It now prints `***redacted***`; `doctor`
  prints only the credential *shape* (`AQ.` long form, length, whitespace warning).
* All error paths that can reach a log line or a public issue comment are passed
  through `redactSecrets()`.
* `PI_CODING_AGENT_DIR` is set to a clean directory in CI: pi resolves
  `~/.pi/agent/auth.json` **before** the environment, so a stale stored credential
  silently shadows the `GEMINI_API_KEY` secret on runners with a persisted home.
* The workflow no longer pipes `secrets.GITHUB_TOKEN` into a shell command;
  `gh auth status` reads `GH_TOKEN` from the environment.

## Operating notes

* Gemini free tier is **5–15 requests/minute per model** and Flash models can be
  capped at ~20 requests/day. Flash-Lite ids have the highest ceiling, which is
  why `gemini-3.5-flash-lite` is the default.
* Gemini reports both per-minute throttling and daily exhaustion as 429
  `RESOURCE_EXHAUSTED`. The classifier treats a response carrying a retry hint as
  transient, and "per day"/`RPD` wording as fatal.
* `bun run preflight` (also a workflow step) probes
  `GET /v1beta/models/{id}` with the `x-goog-api-key` header before the agent
  starts, so a bad key or a retired model is reported as itself. It is advisory
  (exit 0) unless `ISSUECLAW_PREFLIGHT_STRICT=true`.

## Verification

```bash
bun run typecheck   # tsc --noEmit
bun run lint        # biome check src tests
bun run test        # vitest run — 53 tests
```

Regression tests live in `tests/unit/`: the retry classifier, the retired-model
map, the Gemini request shape (header auth, no key in the URL), and the
lifecycle error classifier (a retired-model 404 must never be reported as a
403/401).

## Applying the workflow change

`patches/issueclaw-agent-workflow.patch` contains the workflow update (secret
echo removal, credential preflight step, `PI_CODING_AGENT_DIR`, retry tuning).
It is shipped as a patch **only because the GitHub App used by this session is
not allowed to create or update files under `.github/workflows/`** — both
`git push` and the Contents API answer:

```
refusing to allow a GitHub App to create or update workflow
`.github/workflows/issueclaw-agent.yml` without `workflows` permission
```

Apply it with a credential that has the `workflow` scope:

```bash
git apply patches/issueclaw-agent-workflow.patch
git commit -am "ci(issueclaw): secret hygiene, credential preflight, retry tuning"
git push
```

The workflow change is an operational hardening step — the Gemini fix itself is
complete without it, because `issueclaw.config.json` and `src/` are what the
workflow executes.
