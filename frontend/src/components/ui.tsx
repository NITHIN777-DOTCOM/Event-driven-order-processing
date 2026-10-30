/** Small shared UI pieces: status pill, product image, error banner, skeleton. */
import { useState } from "react";

export type PillTone = "ok" | "bad" | "pending" | "retry";

const PILL: Record<PillTone, string> = {
  ok: "bg-ok-bg text-ok",
  bad: "bg-bad-bg text-bad",
  retry: "bg-retry-bg text-retry",
  pending: "bg-tile text-muted-strong",
};
const DOT: Record<PillTone, string> = { ok: "bg-ok", bad: "bg-bad", retry: "bg-amber", pending: "bg-pending" };

export function StatusPill({ tone, label }: { tone: PillTone; label: string }) {
  return (
    <span className={`inline-flex items-center gap-2 whitespace-nowrap rounded-full px-3 py-1 text-sm font-semibold ${PILL[tone]}`}>
      <span className={`h-2 w-2 rounded-full ${DOT[tone]}`} aria-hidden="true" />
      {label}
    </span>
  );
}

/** Map an order's status to a pill. Dead-lettered orders stay PENDING in the database. */
export function orderPill(status: string, deadLettered?: boolean | null): { tone: PillTone; label: string } {
  if (deadLettered) return { tone: "bad", label: "In DLQ" };
  if (status === "COMPLETED") return { tone: "ok", label: "Completed" };
  if (status === "PARTIALLY_FULFILLED") return { tone: "retry", label: "Partially fulfilled" };
  if (status === "FAILED") return { tone: "bad", label: "Failed" };
  if (status === "PENDING") return { tone: "pending", label: "Pending" };
  return { tone: "pending", label: "Processing" };
}

/** A product photo, or a neutral tile with the product name if the image is missing or fails to load. */
export function ProductImage({ imageKey, name, className = "" }: { imageKey: string | null; name: string; className?: string }) {
  const [failed, setFailed] = useState(false);
  if (!imageKey || failed) {
    return (
      <div className={`flex items-center justify-center bg-tile p-2 text-center text-xs text-muted ${className}`}>{name}</div>
    );
  }
  return (
    <img
      src={`/${imageKey}`}
      alt={name}
      loading="lazy"
      decoding="async"
      onError={() => setFailed(true)}
      className={`bg-tile object-cover ${className}`}
    />
  );
}

export function ErrorBanner({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-card border border-bad/30 bg-bad-bg px-4 py-3 text-sm text-bad">
      <span>{message}</span>
      {onRetry && (
        <button type="button" className="font-semibold underline underline-offset-2" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}

export const Skeleton = ({ className = "" }: { className?: string }) => <div className={`skeleton ${className}`} aria-hidden="true" />;
