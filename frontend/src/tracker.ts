/**
 * Derive the order tracker's progress steps from statusHistory.
 *
 *   Placed -> Queued -> Stock reserved -> Paid -> Confirmed
 *
 * While the saga waits for DemoPay's webhook (PAYMENT_PENDING), the "Paid" step reads
 * "Awaiting payment confirmation".
 *
 * On failure the failing step turns red. When compensation ran (INVENTORY_RELEASED), a
 * "Stock released" step replaces "Confirmed", because the order will never be confirmed.
 * A PARTIALLY_FULFILLED order (some lines refunded after payment) ends on "Partly delivered".
 * A CANCELLED order (step 2.4) ends on "Stock released", and its "Paid" step says whether it was refunded.
 */
import { ordinal } from "./format";
import type { HistoryEntry, Order } from "./types";

export type StepKey = "placed" | "queued" | "reserved" | "paid" | "confirmed" | "released";
export type StepState = "done" | "failed" | "active" | "pending" | "compensated";

export interface Step {
  key: StepKey;
  label: string;
  state: StepState;
  time?: string;
  note?: string;
}

export const TERMINAL_STATUSES = ["COMPLETED", "PARTIALLY_FULFILLED", "FAILED", "CANCELLED"];

export const isTerminal = (order: Order) => TERMINAL_STATUSES.includes(order.status) || Boolean(order.deadLettered);

const find = (history: HistoryEntry[], status: string) => history.find((entry) => entry.status === status);
const last = (history: HistoryEntry[], status: string) => [...history].reverse().find((entry) => entry.status === status);

export function deriveSteps(order: Order): Step[] {
  const h = order.statusHistory;
  const failedAt = find(h, "FAILED")?.timestamp;
  const released = find(h, "INVENTORY_RELEASED");
  const partial = find(h, "PARTIALLY_FULFILLED");
  const cancelled = order.items.filter((item) => item.fulfillment === "WRITTEN_OFF").length;

  const steps: Step[] = [
    { key: "placed", label: "Placed", state: "done", time: find(h, "PENDING")?.timestamp ?? order.createdAt },
    stage("queued", "Queued", find(h, "PROCESSING"), find(h, "DEAD_LETTERED")),
    stage("reserved", "Stock reserved", find(h, "RESERVED"), find(h, "OUT_OF_STOCK")),
    paidStep(order, h, failedAt),
    released
      ? { key: "released", label: "Stock released", state: "compensated", time: released.timestamp }
      : partial
        ? { key: "confirmed", label: "Partly delivered", state: "compensated", time: partial.timestamp, note: `${cancelled} of ${order.items.length} refunded` }
        : stage("confirmed", "Confirmed", find(h, "COMPLETED"), undefined),
  ];

  // A failure that didn't map to a specific step (e.g. an unexpected error) marks the first unfinished step.
  if (failedAt && !steps.some((step) => step.state === "failed")) {
    const first = steps.find((step) => step.state === "pending");
    if (first) Object.assign(first, { state: "failed", time: failedAt });
  }
  // While processing, the first unfinished step is the active one.
  if (!isTerminal(order)) {
    const next = steps.find((step) => step.state === "pending");
    if (next) next.state = "active";
  }
  return steps;
}

function stage(key: StepKey, label: string, done?: HistoryEntry, failed?: HistoryEntry): Step {
  if (done) return { key, label, state: "done", time: done.timestamp };
  if (failed) return { key, label, state: "failed", time: failed.timestamp };
  return { key, label, state: "pending" };
}

function paidStep(order: Order, h: HistoryEntry[], failedAt?: string): Step {
  const attempts = order.paymentAttempts ?? 1;
  const note = attempts > 1 ? `${ordinal(attempts)} attempt` : undefined;
  const captured = find(h, "PAYMENT_CAPTURED");
  if (order.status === "CANCELLED") {
    const refund = order.refundedAmount ?? 0;
    return { key: "paid", label: "Paid", state: "compensated", time: captured?.timestamp, note: refund > 0 ? "refunded" : "nothing charged" };
  }
  if (captured) return { key: "paid", label: "Paid", state: "done", time: captured.timestamp, note };

  const declined = find(h, "PAYMENT_DECLINED");
  if (declined) return { key: "paid", label: "Paid", state: "failed", time: declined.timestamp, note: "declined" };

  // Retries ran out: the order failed after at least one PAYMENT_RETRY and was never captured.
  const lastRetry = last(h, "PAYMENT_RETRY");
  const pending = last(h, "PAYMENT_PENDING");
  // The saga gave up waiting for the provider's webhook (no callback within 120 s).
  if (pending && failedAt && /timeout/i.test(order.failureReason ?? ""))
    return { key: "paid", label: "Paid", state: "failed", time: failedAt, note: "no confirmation in 120 s" };
  if (lastRetry && failedAt && !pending) return { key: "paid", label: "Paid", state: "failed", time: failedAt, note: "retries exhausted" };
  if (pending && !failedAt) return { key: "paid", label: "Awaiting payment confirmation", state: "pending", time: pending.timestamp, note: "waiting for DemoPay" };
  if (lastRetry) return { key: "paid", label: "Paid", state: "pending", note: `retrying · ${ordinal(attempts)} attempt failed` };
  return { key: "paid", label: "Paid", state: "pending" };
}

/** The headline for the tracker. */
export function trackerTitle(order: Order): string {
  if (order.deadLettered) return "Stuck in the dead-letter queue";
  if (order.status === "COMPLETED") return "Order completed";
  if (order.status === "PARTIALLY_FULFILLED") return "Order partially fulfilled";
  if (order.status === "FAILED") return "Order failed";
  if (order.status === "CANCELLED") return "Order cancelled";
  if (order.status === "CANCEL_REQUESTED") return "Cancelling…";
  return "Processing…";
}

/** Time of the last event, used for "finished in Xs". */
export function finishedAt(order: Order): string | undefined {
  return isTerminal(order) ? order.statusHistory[order.statusHistory.length - 1]?.timestamp : undefined;
}
