import type { Simulate } from "./types";

const inr = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2, minimumFractionDigits: 0 });

/** 4999 -> "₹4,999"; 1234.5 -> "₹1,234.5" */
export const formatPrice = (amount: number) => inr.format(amount);

/** ISO timestamp -> local "16:37:31". */
export const formatTime = (iso: string) =>
  new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" });

/** ISO timestamp -> local "22 Oct, 16:37". */
export const formatDateTime = (iso: string) =>
  new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

/** Milliseconds -> "8.2s" / "3m 05s". */
export function formatDuration(ms: number): string {
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  const seconds = Math.round(ms / 1000);
  return `${Math.floor(seconds / 60)}m ${String(seconds % 60).padStart(2, "0")}s`;
}

/** 3 -> "3rd" */
export function ordinal(n: number): string {
  const suffix = n % 100 >= 11 && n % 100 <= 13 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[n % 10] ?? "th";
  return `${n}${suffix}`;
}

/** The checkout's "Test scenario" options, shared with the Orders table. */
export const SCENARIOS: { value: Simulate; label: string; description: string }[] = [
  { value: "none", label: "Normal", description: "Stock is reserved, DemoPay confirms the payment through a signed webhook a few seconds later, and a confirmation email is sent." },
  { value: "payment_declined", label: "Payment declined", description: "The card is declined before any money moves, so the saga releases the reserved stock and fails the order." },
  { value: "payment_flaky", label: "Payment glitch (retries)", description: "The payment request fails twice with a transient error; Step Functions retries with backoff and the wallet is debited once." },
  { value: "payment_timeout", label: "Payment timeout", description: "DemoPay never answers. After 120 s the saga gives up, releases the stock and fails the order; nothing is charged." },
  { value: "payment_late", label: "Late payment (auto-refund)", description: "DemoPay charges after the 120 s timeout (~150 s). The order has already failed, so the late payment is refunded automatically." },
  { value: "webhook_duplicate", label: "Duplicate webhook", description: "DemoPay sends the success callback twice; the second is ignored, so the wallet is debited once." },
  { value: "webhook_bad_signature", label: "Forged webhook first", description: "A callback with a wrong HMAC signature arrives first and is rejected (401); the genuine one then completes the order." },
  { value: "item_unavailable", label: "Item damaged (partial refund)", description: "After payment, the last item is found damaged in the warehouse: only that item is refunded and written off, the rest is delivered, and the order is partially fulfilled." },
  { value: "out_of_stock", label: "Out of stock", description: "Reservation fails before anything is held, so the order fails with nothing to release." },
  { value: "poison", label: "Poison message (to DLQ)", description: "The queue consumer rejects the message; after 3 attempts SQS moves it to the dead-letter queue (~3 min)." },
];

export const scenarioLabel = (simulate: Simulate) => SCENARIOS.find((s) => s.value === simulate)?.label ?? simulate;

/** Read/write localStorage without ever throwing (private mode, blocked storage, etc.). */
export const storage = {
  get(key: string): string | null {
    try {
      return window.localStorage.getItem(key);
    } catch {
      return null;
    }
  },
  set(key: string, value: string): void {
    try {
      window.localStorage.setItem(key, value);
    } catch {
      /* storage unavailable: the app still works, it just won't remember */
    }
  },
};
