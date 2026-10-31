/**
 * useCheckoutHold: sets the cart aside (POST /holds) while the checkout page is open.
 *   - The countdown runs against the SERVER's clock: offset = serverTime - Date.now() when the hold arrives,
 *     so a device whose clock is minutes off still shows the right mm:ss.
 *   - At 0 the hold is shown as expired (the server expires it at the same second) with "Hold again".
 *   - Leaving the page (navigating away, closing the tab) releases it, unless an order consumed it.
 * Creates and releases run one after another through a small queue, so React StrictMode's mount-unmount-mount
 * in development can't let an older create land after a newer one (a new hold replaces the user's previous one).
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { createHold, releaseHold, type HoldItems } from "./api";
import { getAccessToken } from "./auth";
import { retryWhenBusy } from "./retry";
import type { Hold } from "./types";

export type HoldState =
  | { phase: "holding" }
  | { phase: "busy"; attempt: number; attempts: number } // 503: the store is busy; retrying with backoff (retry.ts)
  | { phase: "active"; hold: Hold; offsetMs: number }
  | { phase: "expired"; hold: Hold }
  | { phase: "unavailable"; message: string }; // e.g. 409: a product is short; checkout still works without a hold

export function useCheckoutHold(items: HoldItems) {
  const [state, setState] = useState<HoldState>({ phase: "holding" });
  const [now, setNow] = useState(() => Date.now());
  const heldId = useRef<string | null>(null);
  const token = useRef<string | undefined>(undefined);
  const consumed = useRef(false);
  const queue = useRef<Promise<void>>(Promise.resolve());
  const itemsKey = JSON.stringify(items);

  const enqueue = (task: () => Promise<void>) => {
    queue.current = queue.current.then(task, task);
  };

  const release = useCallback(() => {
    if (heldId.current && !consumed.current) releaseHold(heldId.current, token.current);
    heldId.current = null;
  }, []);

  const hold = useCallback(() => {
    if (itemsKey === "[]") return; // empty cart (e.g. just cleared after paying): nothing to hold
    setState({ phase: "holding" });
    enqueue(async () => {
      try {
        token.current = await getAccessToken();
        const created = await retryWhenBusy(() => createHold(JSON.parse(itemsKey) as HoldItems), {
          onRetry: (attempt, attempts) => setState({ phase: "busy", attempt, attempts }),
        });
        heldId.current = created.holdId;
        consumed.current = false;
        setState({ phase: "active", hold: created, offsetMs: Date.parse(created.serverTime) - Date.now() });
      } catch (err) {
        setState({ phase: "unavailable", message: (err as Error).message });
      }
    });
  }, [itemsKey]);

  // Hold on entering checkout; release on leaving it (unmount) or closing the tab (pagehide).
  useEffect(() => {
    hold();
    const onHide = () => release();
    const onShow = (event: PageTransitionEvent) => event.persisted && hold(); // back from the bfcache: hold again
    window.addEventListener("pagehide", onHide);
    window.addEventListener("pageshow", onShow);
    return () => {
      window.removeEventListener("pagehide", onHide);
      window.removeEventListener("pageshow", onShow);
      enqueue(async () => release());
    };
  }, [hold, release]);

  // Tick once a second while the hold is active; flip to "expired" at 0.
  useEffect(() => {
    if (state.phase !== "active") return;
    const timer = window.setInterval(() => {
      const current = Date.now();
      setNow(current);
      if (Date.parse(state.hold.expiresAt) <= current + state.offsetMs) {
        heldId.current = null; // nothing left to release
        setState({ phase: "expired", hold: state.hold });
      }
    }, 1000);
    return () => window.clearInterval(timer);
  }, [state]);

  const secondsLeft =
    state.phase === "active" ? Math.max(0, Math.ceil((Date.parse(state.hold.expiresAt) - (now + state.offsetMs)) / 1000)) : 0;

  return {
    state,
    secondsLeft,
    /** Sent with the order. An expired hold is still sent: the saga records it and reserves afresh. */
    holdId: state.phase === "active" || state.phase === "expired" ? state.hold.holdId : undefined,
    holdAgain: hold,
    /** Call once an order has been placed with this hold, so leaving the page doesn't release it. */
    markConsumed: () => {
      consumed.current = true;
    },
  };
}

/** 600 -> "10:00", 59 -> "0:59". */
export function formatCountdown(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}
