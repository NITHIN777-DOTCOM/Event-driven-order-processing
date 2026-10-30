/**
 * DemoPay wallet (/wallet): balance, transaction history, reset to ₹10,00,000, and a "set balance"
 * demo control. For example, set it to ₹1,000 and buy something pricier to see a REAL decline.
 * Always the signed-in user's own wallet (the page is behind <RequireAuth>).
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { setWalletBalance } from "../api";
import { useSession } from "../auth";
import { formatDateTime, formatPrice } from "../format";
import type { WalletTxnType } from "../types";
import { useWallet } from "../wallet";
import { ErrorBanner, Skeleton, StatusPill, type PillTone } from "../components/ui";

const TYPE: Record<WalletTxnType, { label: string; tone: PillTone }> = {
  DEBIT: { label: "Debit", tone: "bad" },
  CREDIT: { label: "Refund", tone: "ok" },
  ADJUST: { label: "Adjustment", tone: "pending" },
};

export function WalletPage() {
  const { wallet, refresh, setWallet } = useWallet();
  const { email } = useSession();
  const [custom, setCustom] = useState("1000");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function change(balance?: number) {
    setBusy(true);
    setError(null);
    try {
      setWallet(await setWalletBalance(balance));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="mb-8 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[32px] font-semibold leading-tight">DemoPay wallet</h1>
          <p className="mt-1 text-muted">{email} · demo money, not real</p>
        </div>
      </div>
      {error && (
        <div className="mb-6">
          <ErrorBanner message={error} />
        </div>
      )}

      <div className="grid gap-8 lg:grid-cols-[300px_1fr]">
        <div className="space-y-6">
          <section className="card p-6" aria-labelledby="balance-title">
            <h2 id="balance-title" className="text-sm font-medium text-muted-strong">
              Available balance
            </h2>
            {wallet ? <p className="mt-1 text-[36px] font-semibold leading-tight">{formatPrice(wallet.balance)}</p> : <Skeleton className="mt-2 h-10 w-48" />}
            <button type="button" className="btn-secondary mt-5 w-full" onClick={() => change()} disabled={busy}>
              Reset demo balance to ₹10,00,000
            </button>
          </section>

          <section className="card p-6" aria-labelledby="set-title">
            <div className="flex items-center gap-2">
              <h2 id="set-title" className="section-title">
                Set a custom balance
              </h2>
              <span className="rounded-full bg-cream px-2 py-0.5 text-xs font-semibold">Demo</span>
            </div>
            <p className="mt-1 text-sm text-muted">Set ₹1,000, then buy something pricier: the payment is declined for real and the stock is released.</p>
            <form
              className="mt-4 flex gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                change(Number(custom));
              }}
            >
              <label htmlFor="custom-balance" className="sr-only">
                Balance in rupees
              </label>
              <input
                id="custom-balance"
                type="number"
                min={0}
                max={10000000}
                step={1}
                className="input"
                value={custom}
                onChange={(e) => setCustom(e.target.value)}
              />
              <button type="submit" className="btn-primary shrink-0" disabled={busy || custom === "" || Number(custom) < 0}>
                Set
              </button>
            </form>
          </section>
        </div>

        <section className="card overflow-hidden" aria-labelledby="txn-title">
          <h2 id="txn-title" className="section-title border-b border-line px-6 py-4">
            Transactions
          </h2>
          {!wallet ? (
            <div className="space-y-3 p-6">
              <Skeleton className="h-5 w-full" />
              <Skeleton className="h-5 w-full" />
            </div>
          ) : wallet.transactions.length === 0 ? (
            <p className="px-6 py-10 text-center text-muted">
              No transactions yet. <Link to="/" className="font-medium text-ink underline underline-offset-2">Start shopping</Link>.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-line text-[13px] text-muted">
                  <tr>
                    <th scope="col" className="px-5 py-3 font-medium">Date</th>
                    <th scope="col" className="px-3 py-3 font-medium">Order</th>
                    <th scope="col" className="px-3 py-3 font-medium">Type</th>
                    <th scope="col" className="px-3 py-3 text-right font-medium">Amount</th>
                    <th scope="col" className="px-5 py-3 text-right font-medium">Balance after</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {wallet.transactions.map((t) => {
                    const credit = t.type === "CREDIT" || (t.type === "ADJUST" && t.amount >= 0);
                    return (
                      <tr key={t.txnId}>
                        <td className="whitespace-nowrap px-5 py-3 text-muted">{formatDateTime(t.ts)}</td>
                        <td className="px-3 py-3">
                          {t.orderId ? (
                            <Link to={`/orders/${t.orderId}`} className="whitespace-nowrap font-mono text-[13px] underline decoration-line underline-offset-4 hover:decoration-ink">
                              {t.orderId}
                            </Link>
                          ) : (
                            <span className="text-muted">{t.note}</span>
                          )}
                          {/* A refund says what it was for, e.g. "Refund for ORD-… line L2 (1 x Desk Mat)" (step 2.3). */}
                          {t.orderId && t.type === "CREDIT" && t.note && (
                            <span className="mt-0.5 block text-xs text-muted">{t.note}</span>
                          )}
                        </td>
                        <td className="px-3 py-3">
                          <StatusPill tone={TYPE[t.type].tone} label={TYPE[t.type].label} />
                        </td>
                        <td className={`whitespace-nowrap px-3 py-3 text-right font-medium ${credit ? "text-ok" : "text-bad"}`}>
                          {credit ? "+" : "−"}
                          {formatPrice(Math.abs(t.amount))}
                        </td>
                        <td className="whitespace-nowrap px-5 py-3 text-right">{formatPrice(t.balanceAfter)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </>
  );
}
