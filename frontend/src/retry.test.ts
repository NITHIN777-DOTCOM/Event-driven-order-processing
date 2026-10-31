/**
 * Unit tests for the "busy, retrying…" behaviour (retry.ts): a 503 from POST /holds or POST /orders is retried with
 * backoff a few times; any other error is not.
 */
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "./api";
import { BUSY_ATTEMPTS, STILL_BUSY_MESSAGE, busyDelayMs, retryWhenBusy } from "./retry";

const busy = (retryAfter?: number) => new ApiError("Product RACE-1 is busy", 503, retryAfter);
const noSleep = () => Promise.resolve();

describe("retryWhenBusy", () => {
  it("retries a 503 and returns the answer that follows", async () => {
    const request = vi.fn().mockRejectedValueOnce(busy(1)).mockRejectedValueOnce(busy()).mockResolvedValue({ holdId: "HOLD-1" });
    const onRetry = vi.fn();
    await expect(retryWhenBusy(request, { onRetry, sleep: noSleep })).resolves.toEqual({ holdId: "HOLD-1" });
    expect(request).toHaveBeenCalledTimes(3);
    expect(onRetry.mock.calls).toEqual([
      [2, BUSY_ATTEMPTS],
      [3, BUSY_ATTEMPTS],
    ]);
  });

  it("gives up after a few tries with a friendly message, still a 503", async () => {
    const request = vi.fn().mockRejectedValue(busy());
    const error = (await retryWhenBusy(request, { sleep: noSleep }).catch((err: unknown) => err)) as ApiError;
    expect(request).toHaveBeenCalledTimes(BUSY_ATTEMPTS);
    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(503);
    expect(error.message).toBe(STILL_BUSY_MESSAGE);
  });

  it("never retries a real answer such as 409 out of stock", async () => {
    const request = vi.fn().mockRejectedValue(new ApiError("Not enough stock", 409));
    await expect(retryWhenBusy(request, { sleep: noSleep })).rejects.toMatchObject({ status: 409 });
    expect(request).toHaveBeenCalledTimes(1);
  });

  it("waits between tries (backoff), honouring Retry-After", async () => {
    const waits: number[] = [];
    const request = vi.fn().mockRejectedValueOnce(busy(2)).mockRejectedValueOnce(busy()).mockResolvedValue("ok");
    await retryWhenBusy(request, { sleep: async (ms) => void waits.push(ms), random: () => 1 });
    expect(waits).toEqual([2000, 1000]); // Retry-After: 2 s, then the 2nd backoff step (500 ms x 2)
  });
});

describe("busyDelayMs", () => {
  it("grows exponentially with jitter and is capped", () => {
    expect(busyDelayMs(1, undefined, () => 1)).toBe(500);
    expect(busyDelayMs(3, undefined, () => 1)).toBe(2000);
    expect(busyDelayMs(10, undefined, () => 1)).toBe(4000);
    expect(busyDelayMs(1, undefined, () => 0)).toBe(250); // jitter floor: half the backoff
  });
});
