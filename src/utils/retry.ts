/**
 * Retry utility with exponential backoff and jitter.
 * Supports async functions and configurable retry conditions.
 */

import { classifyProviderError, parseRetryDelayMs } from "./errors.ts";
import { log } from "./log.ts";

export interface RetryOptions<_T> {
  /** Maximum number of attempts (including the first try). Default: 3. */
  maxAttempts?: number;
  /** Initial delay in ms. Default: 1000. */
  initialDelayMs?: number;
  /** Maximum delay in ms. Default: 30000. */
  maxDelayMs?: number;
  /** Backoff multiplier. Default: 2. */
  multiplier?: number;
  /** Whether to add jitter (random 0-50% of delay). Default: true. */
  jitter?: boolean;
  /** Predicate to decide whether an error is retryable. Default: all errors. */
  retryIf?: (error: unknown) => boolean;
  /** Called before each retry with the attempt number and error. */
  onRetry?: (attempt: number, error: unknown, delayMs: number) => void;
  /** Timeout for each attempt in ms. */
  timeoutMs?: number;
  /**
   * Extra delay requested by the provider for this error (ms).
   * When it returns a number, the retry waits at least that long — Gemini
   * answers 429 with `Please retry in 43.8s` and ignoring that hint guarantees
   * another 429. Falls back to `parseRetryDelayMs(error.message)`.
   */
  retryAfterMs?: (error: unknown) => number | undefined;
  /** Operation name for logging. */
  name?: string;
}

const DEFAULT_OPTIONS: Required<
  Omit<RetryOptions<unknown>, "retryIf" | "onRetry" | "timeoutMs" | "name" | "retryAfterMs">
> = {
  maxAttempts: 3,
  initialDelayMs: 1000,
  maxDelayMs: 30000,
  multiplier: 2,
  jitter: true,
};

async function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function retry<T>(fn: () => Promise<T>, options: RetryOptions<T> = {}): Promise<T> {
  const opts = { ...DEFAULT_OPTIONS, ...options };
  const name = opts.name ?? "operation";

  let lastError: unknown;
  let delay = opts.initialDelayMs;

  for (let attempt = 1; attempt <= opts.maxAttempts; attempt++) {
    try {
      log.debug(`retry: ${name} attempt ${attempt}/${opts.maxAttempts}`);
      const result = opts.timeoutMs ? await withTimeout(fn(), opts.timeoutMs) : await fn();
      if (attempt > 1) {
        log.info(`retry: ${name} succeeded on attempt ${attempt}`);
      }
      return result;
    } catch (error) {
      lastError = error;
      const isRetryable = opts.retryIf ? opts.retryIf(error) : true;
      if (!isRetryable || attempt === opts.maxAttempts) {
        throw error;
      }
      const jitter = opts.jitter ? Math.random() * 0.5 * delay : 0;
      // Honour an explicit provider back-off hint (429 / Retry-After) when the
      // computed exponential delay is shorter than what the provider asked for.
      const requested = opts.retryAfterMs?.(error) ?? parseRetryDelayMs(errorMessage(error)) ?? 0;
      const actualDelay = Math.min(Math.max(delay + jitter, requested), opts.maxDelayMs);
      log.warn(
        `retry: ${name} failed on attempt ${attempt}, retrying in ${Math.round(actualDelay)}ms`,
        { error: errorMessage(error), attempt, nextDelay: Math.round(actualDelay) },
      );
      opts.onRetry?.(attempt, error, Math.round(actualDelay));
      await sleep(actualDelay);
      delay = Math.min(delay * opts.multiplier, opts.maxDelayMs);
    }
  }
  throw lastError;
}

export function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  if (typeof error === "string") return error;
  return String(error);
}

export function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      reject(new Error(`Operation timed out after ${ms}ms`));
    }, ms);
    promise.then(
      (val) => {
        clearTimeout(timer);
        resolve(val);
      },
      (err) => {
        clearTimeout(timer);
        reject(err);
      },
    );
  });
}

/**
 * Returns a retryable error predicate for network/HTTP errors.
 *
 * Delegates to the shared provider-error classifier so that Google's wording
 * (`UNAVAILABLE`, `RESOURCE_EXHAUSTED`, `Please retry in 43.8s`) is handled the
 * same way as OpenAI-style status codes. Authentication failures (401/403) and
 * retired-model errors (404) are explicitly NOT retryable — retrying those just
 * burns quota.
 */
export function isRetryableHttpError(error: unknown): boolean {
  return classifyProviderError(error).retryable;
}

/**
 * Back-off hint (ms) requested by the provider for the given error, if any.
 * Exposed so callers can wire it into `retry({ retryAfterMs })`.
 */
export function retryAfterMsFor(error: unknown): number | undefined {
  return classifyProviderError(error).retryAfterMs;
}
