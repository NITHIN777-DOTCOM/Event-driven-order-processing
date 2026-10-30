/**
 * Order tracker (/orders/:id): the main feature.
 * Polls GET /orders/{id} every 1.5 s until the order reaches a terminal state, and shows the
 * progress steps, a live feed of what each AWS service did, the items and AWS Console links.
 */
import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError, cancelOrder, getOrder } from "../api";
import { formatDateTime, formatDuration, formatPrice, formatTime, scenarioLabel } from "../format";
import { deriveSteps, finishedAt, isTerminal, trackerTitle, type Step } from "../tracker";
import type { FeedRow, Order, OrderItem } from "../types";
import { useWallet } from "../wallet";
import {
  CardIcon,
  EnvelopeCheckIcon,
  PackageIcon,
  PackageReturnIcon,
  QueueIcon,
  ReceiptIcon,
} from "../components/StageIcons";
import { ErrorBanner, Skeleton, StatusPill, orderPill } from "../components/ui";

const POLL_MS = 1500;
const POISON_HINT_AFTER_MS = 20_000;

const STEP_ICON = {
  placed: ReceiptIcon,
  queued: QueueIcon,
  reserved: PackageIcon,
  paid: CardIcon,
  confirmed: EnvelopeCheckIcon,
  released: PackageReturnIcon,
};

/** Poll the order until it's terminal. A failed poll keeps the last good data and shows a banner. */
function useOrderPolling(orderId: string) {
  const [order, setOrder] = useState<Order | null>(null);
  const [error, setError] = useState<{ message: string; fatal: boolean } | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;
    const tick = async () => {
      try {
        const next = await getOrder(orderId);
        if (cancelled) return;
        setOrder(next);
        setError(null);
        if (isTerminal(next)) return; // stop polling
      } catch (err) {
        if (cancelled) return;
        const fatal = err instanceof ApiError && (err.status === 404 || err.status === 400);
        setError({ message: (err as Error).message, fatal });
        if (fatal) return;
      }
      timer = window.setTimeout(tick, POLL_MS);
    };
    tick();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [orderId]);

  return { order, error };
}

/** Re-render once a second while the order is running, for "running for Xs" and the poison hint. */
function useNow(active: boolean): number {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!active) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [active]);
  return now;
}

function StepTile({ step }: { step: Step }) {
  const Icon = STEP_ICON[step.key];
  const tile =
    step.state === "failed"
      ? "border-bad/40 bg-bad-bg"
      : step.state === "compensated"
        ? "border-line bg-retry-bg"
        : "border-line bg-white";
  const bar =
    step.state === "done"
      ? "bg-ok"
      : step.state === "failed"
        ? "bg-bad"
        : step.state === "compensated"
          ? "bg-amber"
          : step.state === "active"
            ? "bg-amber/60"
            : "bg-line";
  const dim = step.state === "pending" || step.state === "active";

  return (
    <li className="min-w-0">
      <div
        className={`flex h-12 w-12 items-center justify-center rounded-card border sm:h-16 sm:w-16 ${tile} ${dim ? "[&_svg]:opacity-40" : ""}`}
      >
        <Icon />
      </div>
      <div className={`mt-3 h-1 rounded-full ${bar}`} aria-hidden="true" />
      <p className={`mt-3 text-[13px] font-semibold sm:text-sm ${step.state === "failed" ? "text-bad" : dim ? "text-pending" : ""}`}>
        {step.label}
        <span className="sr-only"> ({step.state})</span>
      </p>
      <p className="text-xs text-muted sm:text-[13px]">
        {step.time ? formatTime(step.time) : step.state === "active" ? "in progress" : "—"}
        {step.note && <span className={step.state === "failed" ? "text-bad" : ""}> · {step.note}</span>}
      </p>
    </li>
  );
}

const ROW_STYLE: Record<FeedRow["level"], string> = {
  info: "",
  retry: "bg-retry-bg",
  error: "bg-bad-bg",
};

/** Bold the status words, as in "Order marked COMPLETED". */
function Message({ text }: { text: string }) {
  return (
    <>
      {text.split(/\b(PARTIALLY_FULFILLED|COMPLETED|FAILED|CANCELLED)\b/).map((part, index) =>
        index % 2 === 1 ? <strong key={index} className="font-semibold">{part}</strong> : part,
      )}
    </>
  );
}

/** What a 409 from the cancel API means, in the customer's words. */
const CANCEL_REFUSED: Record<string, string> = {
  TOO_LATE_TO_CANCEL: "Too late to cancel: the warehouse has already started packing this order.",
  NOT_CANCELLABLE: "This order was placed before cancelling was available, so it can't be cancelled.",
  NOT_CANCELLABLE_YET: "The order is still being set up. Try again in a second.",
  CANCEL_DISABLED: "Cancelling orders is switched off right now.",
};

/**
 * The Cancel button, with a confirm step. Shown only while the API reports the order inside the cancel window
 * (canCancel); the API still decides for real, so a refusal (409) is shown as a friendly message.
 */
function CancelOrder({ order }: { order: Order }) {
  const [stage, setStage] = useState<"idle" | "confirm" | "sending" | "sent">("idle");
  const [refusal, setRefusal] = useState<string | null>(null);

  if (refusal) {
    return (
      <p className="card p-4 text-[15px] text-bad" role="alert" data-testid="cancel-refused">
        {refusal}
      </p>
    );
  }
  if (stage === "sent" || order.cancelRequestedAt) {
    return order.status === "CANCELLED" ? null : (
      <p className="card p-4 text-[15px] text-muted-strong" role="status" data-testid="cancel-requested">
        Cancellation requested. Refunding and returning the stock…
      </p>
    );
  }
  if (!order.canCancel) return null;

  const send = async () => {
    setStage("sending");
    try {
      await cancelOrder(order.orderId);
      setStage("sent"); // the poll picks up CANCEL_REQUESTED, then CANCELLED
    } catch (err) {
      const code = err instanceof ApiError ? err.message : "";
      setRefusal(CANCEL_REFUSED[code] ?? `Couldn't cancel the order: ${(err as Error).message}`);
    }
  };

  if (stage === "idle") {
    return (
      <button type="button" className="btn-secondary w-full" onClick={() => setStage("confirm")} data-testid="cancel-order">
        Cancel order
      </button>
    );
  }
  return (
    <div className="card p-4" role="group" aria-label="Confirm cancellation">
      <p className="text-[15px] font-semibold">Cancel this order?</p>
      <p className="mt-1 text-sm text-muted">
        {order.paidAmount !== undefined
          ? `The ${formatPrice(order.paidAmount)} you paid goes back to your DemoPay wallet.`
          : "Nothing will be charged; a payment still in flight is refunded automatically."}
      </p>
      <div className="mt-3 flex gap-3">
        <button type="button" className="btn-primary" disabled={stage === "sending"} onClick={send} data-testid="confirm-cancel">
          {stage === "sending" ? "Cancelling…" : "Yes, cancel"}
        </button>
        <button type="button" className="btn-secondary" disabled={stage === "sending"} onClick={() => setStage("idle")}>
          Keep order
        </button>
      </div>
    </div>
  );
}

/** "Cancelled — refunded ₹X" or "Cancelled — nothing charged". */
function cancelledSummary(order: Order): string {
  const refund = order.refundedAmount ?? 0;
  return refund > 0 ? `Cancelled — refunded ${formatPrice(refund)}` : "Cancelled — nothing charged";
}

function FeedList({ rows }: { rows: FeedRow[] }) {
  return (
    <ol className="card divide-y divide-line overflow-hidden" aria-live="polite" aria-label="Live feed, newest first">
      {rows.map((row) => (
        <li
          key={`${row.time}|${row.service}|${row.message}`}
          className={`feed-row-enter grid grid-cols-[auto_1fr] gap-x-4 gap-y-0.5 px-5 py-3.5 sm:grid-cols-[84px_160px_1fr] sm:items-baseline sm:gap-x-6 sm:px-6 sm:py-4 ${ROW_STYLE[row.level]}`}
        >
          <span className="font-mono text-[13px] text-muted">{formatTime(row.time)}</span>
          <span className="text-[13px] font-semibold text-muted-strong">{row.service}</span>
          <span className={`col-span-2 text-[15px] sm:col-span-1 ${row.level === "error" ? "text-bad" : ""}`}>
            <Message text={row.message} />
            {row.note && <span className="ml-1 text-sm text-retry">({row.note})</span>}
          </span>
        </li>
      ))}
    </ol>
  );
}

function TrackerSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading order">
      <Skeleton className="h-4 w-48" />
      <Skeleton className="mt-3 h-9 w-72" />
      <Skeleton className="mt-3 h-4 w-60" />
      <div className="mt-10 grid grid-cols-5 gap-3 sm:gap-4">
        {Array.from({ length: 5 }, (_, i) => (
          <Skeleton key={i} className="h-28" />
        ))}
      </div>
      <Skeleton className="mt-12 h-64" />
    </div>
  );
}

export function Tracker() {
  const { id = "" } = useParams();
  const { order, error } = useOrderPolling(id);
  const running = order ? !isTerminal(order) : true;
  const now = useNow(running);

  const steps = useMemo(() => (order ? deriveSteps(order) : []), [order]);

  // When the saga finishes, the wallet balance in the header may have changed (debit or refund).
  const { refresh: refreshWallet } = useWallet();
  useEffect(() => {
    if (!running) refreshWallet();
  }, [running, refreshWallet]);

  // Newest first. A poison order still PENDING after 20 s gets an explanatory info row.
  const feed = useMemo(() => {
    if (!order) return [];
    const rows = [...order.feed];
    const waited = now - new Date(order.createdAt).getTime();
    const pickedUp = order.statusHistory.some((entry) => entry.status !== "PENDING");
    if (order.simulate === "poison" && !pickedUp && waited > POISON_HINT_AFTER_MS) {
      rows.push({
        time: new Date(new Date(order.createdAt).getTime() + POISON_HINT_AFTER_MS).toISOString(),
        service: "SQS → Step Functions",
        message: "SQS is retrying this message; after 3 attempts it moves to the dead-letter queue (~3 min)",
        level: "info",
      });
    }
    // Newest first; rows with the same timestamp keep reverse API order (e.g. the SNS email after the DynamoDB write).
    return rows
      .map((row, index) => ({ row, index }))
      .sort((a, b) => b.row.time.localeCompare(a.row.time) || b.index - a.index)
      .map(({ row }) => row);
  }, [order, now]);

  if (error?.fatal) {
    return (
      <div className="space-y-4">
        <ErrorBanner message={error.message} />
        <Link to="/orders" className="btn-secondary">
          See recent orders
        </Link>
      </div>
    );
  }
  if (!order) return error ? <ErrorBanner message={error.message} /> : <TrackerSkeleton />;

  const pill = isTerminal(order)
    ? orderPill(order.status, order.deadLettered)
    : { tone: "pending" as const, label: "Processing" };
  const end = finishedAt(order);
  const elapsed = (end ? new Date(end).getTime() : now) - new Date(order.createdAt).getTime();
  const links = order.consoleLinks;

  return (
    <div>
      {error && (
        <div className="mb-6">
          <ErrorBanner message={`Live updates paused: ${error.message} Retrying…`} />
        </div>
      )}

      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="font-mono text-sm text-muted">{order.orderId}</p>
          <h1 className="mt-1 text-[32px] font-semibold leading-tight">{trackerTitle(order)}</h1>
          <p className="mt-2 text-[15px] text-muted">
            {formatPrice(order.totalAmount)} · placed {formatTime(order.createdAt)} ·{" "}
            {!end
              ? `running for ${formatDuration(Math.max(0, elapsed))}`
              : order.deadLettered
                ? `dead-lettered after ${formatDuration(elapsed)}`
                : `finished in ${formatDuration(elapsed)}`}
            {order.simulate !== "none" && <> · scenario: {scenarioLabel(order.simulate)}</>}
          </p>
          {order.failureReason && <p className="mt-2 text-[15px] text-bad">{order.failureReason}</p>}
          {order.status === "CANCELLED" && (
            <p className="mt-2 text-[15px] font-semibold text-muted-strong" data-testid="cancelled-summary">
              {cancelledSummary(order)}
            </p>
          )}
        </div>
        <StatusPill tone={pill.tone} label={pill.label} />
      </div>

      {/* Progress */}
      <ol className="mt-10 grid grid-cols-5 gap-3 sm:gap-4" aria-label="Order progress">
        {steps.map((step) => (
          <StepTile key={step.key} step={step} />
        ))}
      </ol>

      <div className="mt-12 grid gap-8 lg:grid-cols-[1fr_360px]">
        {/* Live feed */}
        <section aria-labelledby="feed-title">
          <div className="mb-4 flex items-center justify-between">
            <h2 id="feed-title" className="section-title">
              Live feed
            </h2>
            {running && (
              <span className="inline-flex items-center gap-2 text-sm text-muted" role="status">
                <span className="h-2 w-2 rounded-full bg-ok motion-safe:animate-pulse" aria-hidden="true" />
                Live · polling every 1.5s
              </span>
            )}
          </div>
          <FeedList rows={feed} />
        </section>

        {/* Sidebar */}
        <aside className="space-y-6">
          <CancelOrder order={order} />
          <section className="card p-6" aria-labelledby="items-title">
            <h2 id="items-title" className="section-title mb-4">
              Items
            </h2>
            <ul className="space-y-2">
              {order.items.map((item) => (
                <li key={item.lineId ?? item.productId} className="text-[15px]">
                  <div className="flex justify-between gap-4">
                    <span>
                      {item.name} × {item.quantity}
                    </span>
                    <span className={`whitespace-nowrap ${item.fulfillment === "WRITTEN_OFF" ? "text-muted line-through" : ""}`}>
                      {formatPrice(item.lineAmount ?? item.unitPrice * item.quantity)}
                    </span>
                  </div>
                  <LineStatus item={item} />
                </li>
              ))}
            </ul>
            <div className="mt-4 flex justify-between border-t border-line pt-4 font-semibold">
              <span>Total</span>
              <span>{formatPrice(order.totalAmount)}</span>
            </div>
            {order.refundedAmount !== undefined && order.refundedAmount > 0 && order.status === "PARTIALLY_FULFILLED" && (
              <div className="mt-2 flex justify-between text-[15px] text-ok" data-testid="partial-refund">
                <span>Refunded to wallet</span>
                <span>−{formatPrice(order.refundedAmount)}</span>
              </div>
            )}
            {order.paidAmount !== undefined && (
              <p className="mt-4 text-sm text-muted-strong">
                Paid {formatPrice(order.paidAmount)} with DemoPay
                {order.refunded && <span className="block text-ok">Refunded {formatPrice(order.paidAmount)} to the wallet</span>}
              </p>
            )}
            {isTerminal(order) && !order.deadLettered && (
              <p className="mt-4 text-sm text-muted">
                {{ COMPLETED: "Confirmation", PARTIALLY_FULFILLED: "Partial delivery", FAILED: "Failure", CANCELLED: "Cancellation" }[order.status] ?? "Status"}{" "}
                email sent via SNS
                <br />
                <span className="text-muted-strong">for {order.customerEmail}</span>
              </p>
            )}
            <p className="mt-4 text-xs text-muted">Placed {formatDateTime(order.createdAt)} by {order.customerName}</p>
          </section>

          <section className="card p-6" aria-labelledby="console-title">
            <h2 id="console-title" className="section-title">
              View in AWS Console
            </h2>
            <p className="mb-4 text-sm text-muted">Opens in a new tab</p>
            <ul className="space-y-3 text-[15px]">
              <ConsoleLink href={links.execution} label="Step Functions execution" missing="Not started (message never reached the workflow)" />
              <ConsoleLink href={links.dynamodbItem} label="DynamoDB record" />
              <ConsoleLink href={links.logs} label="CloudWatch logs" />
            </ul>
          </section>
        </aside>
      </div>
    </div>
  );
}

/** Under each item, once fulfillment ran: Delivered, or Cancelled with the refund (step 2.3). */
function LineStatus({ item }: { item: OrderItem }) {
  if (item.fulfillment === "FULFILLED") return <p className="text-sm text-ok">Delivered</p>;
  if (item.fulfillment === "WRITTEN_OFF" || item.refundedAmount !== undefined) {
    return (
      <p className="text-sm text-bad" title={item.writeOffReason}>
        Cancelled — refunded {formatPrice(item.refundedAmount ?? item.lineAmount)}
      </p>
    );
  }
  return null;
}

function ConsoleLink({ href, label, missing }: { href: string | null; label: string; missing?: string }) {
  if (!href) {
    return (
      <li className="text-muted">
        {label}
        {missing && <span className="block text-xs">{missing}</span>}
      </li>
    );
  }
  return (
    <li>
      <a href={href} target="_blank" rel="noreferrer" className="font-medium text-ink underline decoration-line underline-offset-4 hover:decoration-ink">
        {label} ↗
      </a>
    </li>
  );
}
