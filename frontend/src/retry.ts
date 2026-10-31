/**
 * "Busy, retrying…": retry a request the server answered with 503 (busy), with backoff, a few times.
 *
 * Why: during a flash sale many buyers update the same product row at once. The server retries DynamoDB's
 * transaction conflicts itself (common/transact.py) and, if one product's row stays contended through all of them,
 * answers 503 + Retry-After instead of guessing "out of stock" (step 3.1). Nothing was held or ordered, so asking
 * again a moment later is safe: a hold attempt just tries again, and an order carries the SAME Idempotency-Key on
 * every try, so it can never be created twice. The customer sees "busy, retrying…", not an error.
 *
 * Only 503 is retried here. A 409 is a real answer (out of stock), and anything else is shown as an error.
 */
import { ApiError } from "./api";

export const BUSY_STATUS = 503;
export const BUSY_ATTEMPTS = 4; // the first try + 3 retries
const BASE_DELAY_MS = 500;
const MAX_DELAY_MS = 4000;

export interface RetryOptions {
  attempts?: number;
  /** Called before each retry: show "busy, retrying… (attempt n of m)". */
  onRetry?: (attempt: number, attempts: number) => void;
  sleep?: (ms: number) => Promise<void>; // injectable for tests
  random?: () => number; // injectable for tests
}

export function isBusy(err: unknown): err is ApiError {
  return err instanceof ApiError && err.status === BUSY_STATUS;
}

/** Wait before retry n (1-based): the server's Retry-After if it sent one, else exponential backoff with jitter. */
export function busyDelayMs(retry: number, retryAfterSeconds: number | undefined, random: () => number = Math.random): number {
  const backoff = Math.min(MAX_DELAY_MS, BASE_DELAY_MS * 2 ** (retry - 1));
  const floor = retryAfterSeconds ? retryAfterSeconds * 1000 : 0;
  return Math.max(floor, Math.round(backoff * (0.5 + random() / 2))); // jitter: 50-100% of the backoff
}

/** The message shown when every try was busy. */
export const STILL_BUSY_MESSAGE = "The store is very busy right now and nothing was charged or held. Please try again in a moment.";

export async function retryWhenBusy<T>(request: () => Promise<T>, options: RetryOptions = {}): Promise<T> {
  const attempts = options.attempts ?? BUSY_ATTEMPTS;
  const sleep = options.sleep ?? ((ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms)));
  for (let attempt = 1; ; attempt++) {
    try {
      return await request();
    } catch (err) {
      if (!isBusy(err)) throw err;
      if (attempt >= attempts) throw new ApiError(STILL_BUSY_MESSAGE, BUSY_STATUS);
      options.onRetry?.(attempt + 1, attempts);
      await sleep(busyDelayMs(attempt, err.retryAfterSeconds, options.random));
    }
  }
}
