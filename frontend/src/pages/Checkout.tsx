/**
 * Checkout (/checkout), two steps:
 *   1. Name + delivery + demo test scenario (and the duplicate test). The account (and so the wallet) is the
 *      signed-in Cognito user's: this page sits behind <RequireAuth> and has no email field.
 *   2. Payment: the DemoPay wallet card (balance, amount due, balance after) and "Pay ₹X"
 * Paying places the order (with an Idempotency-Key) and goes straight to the live tracker.
 * The wallet is actually debited later, by the saga's ProcessPayment step.
 */
import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { createOrder, type NewOrder } from "../api";
import { useCart } from "../cart";
import { DELIVER_TO } from "../catalog";
import { useSession } from "../auth";
import { SCENARIOS, formatPrice } from "../format";
import type { Simulate } from "../types";
import { useWallet } from "../wallet";
import { ErrorBanner, ProductImage } from "../components/ui";

type Step = "details" | "payment";

function StepHeader({ step }: { step: Step }) {
  const item = (n: number, label: string, active: boolean, done: boolean) => (
    <li className={`flex items-center gap-2 text-sm font-semibold ${active ? "text-ink" : "text-pending"}`}>
      <span
        className={`flex h-6 w-6 items-center justify-center rounded-full text-xs ${
          done ? "bg-ok text-white" : active ? "bg-ink text-white" : "border border-line bg-white text-pending"
        }`}
        aria-hidden="true"
      >
        {done ? "✓" : n}
      </span>
      {label}
      <span className="sr-only">{done ? " (done)" : active ? " (current step)" : ""}</span>
    </li>
  );
  return (
    <ol className="mb-8 flex items-center gap-4" aria-label="Checkout steps">
      {item(1, "Contact & delivery", step === "details", step === "payment")}
      <li className="h-px w-10 bg-line" aria-hidden="true" />
      {item(2, "Payment", step === "payment", false)}
    </ol>
  );
}

export function Checkout() {
  const cart = useCart();
  const navigate = useNavigate();
  const session = useSession();
  const { contact, saveContact, wallet, refresh } = useWallet();
  const [form, setForm] = useState({ name: contact.name || session.name, address: contact.address || DELIVER_TO });
  const [step, setStep] = useState<Step>("details");
  const [simulate, setSimulate] = useState<Simulate>("none");
  const [busy, setBusy] = useState<"order" | "duplicate" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [duplicateResult, setDuplicateResult] = useState<{ requests: number; orderIds: string[] } | null>(null);

  const scenario = SCENARIOS.find((s) => s.value === simulate)!;
  const detailsValid = form.name.trim().length > 0 && form.address.trim().length > 0;
  const balance = wallet ? wallet.balance : null;
  const after = balance === null ? null : balance - cart.total;

  const buildOrder = (): NewOrder => ({
    customerName: form.name.trim(), // the delivery name only; the account comes from the ID token
    items: cart.lines.map((line) => ({ productId: line.productId, quantity: line.quantity })),
    simulate,
  });

  function continueToPayment(event: FormEvent) {
    event.preventDefault();
    if (!detailsValid) return;
    saveContact({ name: form.name.trim(), address: form.address.trim() });
    setError(null);
    setStep("payment");
  }

  async function pay() {
    if (busy) return;
    setBusy("order");
    setError(null);
    try {
      const result = await createOrder(buildOrder(), crypto.randomUUID());
      cart.clear();
      window.setTimeout(refresh, 4000); // the saga debits within a few seconds
      navigate(`/orders/${result.orderId}`);
    } catch (err) {
      setError((err as Error).message);
      setBusy(null);
    }
  }

  /** Sends the SAME request 3 times with ONE Idempotency-Key: the API must create exactly one order. */
  async function duplicateTest() {
    if (!detailsValid || busy) return;
    saveContact({ name: form.name.trim(), address: form.address.trim() });
    setBusy("duplicate");
    setError(null);
    setDuplicateResult(null);
    try {
      const order = buildOrder();
      const key = crypto.randomUUID();
      const results = [];
      for (let i = 0; i < 3; i++) results.push(await createOrder(order, key));
      setDuplicateResult({ requests: results.length, orderIds: [...new Set(results.map((r) => r.orderId))] });
      window.setTimeout(refresh, 4000);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(null);
    }
  }

  if (cart.lines.length === 0 && !duplicateResult) {
    return (
      <div className="card mx-auto max-w-lg px-6 py-12 text-center">
        <h1 className="text-[32px] font-semibold">Checkout</h1>
        <p className="mt-3 text-muted">Your cart is empty.</p>
        <Link to="/" className="btn-primary mt-6">
          Browse products
        </Link>
      </div>
    );
  }

  return (
    <div>
      <h1 className="mb-4 text-[32px] font-semibold leading-tight">Checkout</h1>
      <StepHeader step={step} />
      {error && (
        <div className="mb-6">
          <ErrorBanner message={error} />
        </div>
      )}

      <div className="grid gap-8 lg:grid-cols-[1fr_360px]">
        {step === "details" ? (
          <form id="details-form" onSubmit={continueToPayment} noValidate className="space-y-6">
            <section className="card p-6" aria-labelledby="contact-title">
              <h2 id="contact-title" className="section-title mb-4">
                Contact
              </h2>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field id="name" label="Name" value={form.name} onChange={(v) => setForm({ ...form, name: v })} autoComplete="name" />
                <div>
                  <span className="label">Signed in as</span>
                  <p className="flex h-10 items-center text-[15px] text-muted-strong" data-testid="account-email">
                    {session.email}
                  </p>
                </div>
              </div>
            </section>

            <section className="card p-6" aria-labelledby="delivery-title">
              <h2 id="delivery-title" className="section-title mb-4">
                Delivery
              </h2>
              <Field id="address" label="Address" value={form.address} onChange={(v) => setForm({ ...form, address: v })} autoComplete="street-address" />
              <p className="mt-2 text-sm text-muted">FREE delivery in 2 days.</p>
            </section>

            <section className="card p-6" aria-labelledby="scenario-title">
              <div className="mb-4 flex items-center gap-2">
                <h2 id="scenario-title" className="section-title">
                  Test scenario
                </h2>
                <span className="rounded-full bg-cream px-2 py-0.5 text-xs font-semibold text-ink">Demo</span>
              </div>
              <label htmlFor="scenario" className="sr-only">
                Test scenario
              </label>
              <select id="scenario" className="input" value={simulate} onChange={(e) => setSimulate(e.target.value as Simulate)}>
                {SCENARIOS.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </select>
              <p className="mt-3 text-sm text-muted">{scenario.description}</p>

              <div className="mt-5 border-t border-line pt-5">
                <button type="button" className="btn-secondary" onClick={duplicateTest} disabled={!detailsValid || busy !== null || cart.lines.length === 0}>
                  {busy === "duplicate" ? "Sending…" : "Send same order 3× (duplicate test)"}
                </button>
                {duplicateResult && (
                  <p className="mt-3 text-sm text-muted-strong" role="status">
                    {duplicateResult.requests} requests → {duplicateResult.orderIds.length} order
                    {duplicateResult.orderIds.length === 1 ? "" : "s"} (
                    {duplicateResult.orderIds.map((id) => (
                      <Link key={id} to={`/orders/${id}`} className="font-mono text-ink underline underline-offset-2">
                        {id}
                      </Link>
                    ))}
                    )
                  </p>
                )}
              </div>
            </section>
          </form>
        ) : (
          <section className="card p-6" aria-labelledby="payment-title">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 id="payment-title" className="section-title">
                  DemoPay wallet
                </h2>
                <p className="text-sm text-muted">{session.email}</p>
              </div>
              <button type="button" className="text-sm font-medium text-muted-strong underline underline-offset-2" onClick={() => setStep("details")}>
                Change details
              </button>
            </div>

            <dl className="mt-6 divide-y divide-line rounded-card border border-line">
              <Row label="Wallet balance" value={balance === null ? "Loading…" : formatPrice(balance)} />
              <Row label="Amount due" value={formatPrice(cart.total)} strong />
              <Row
                label="Balance after payment"
                value={after === null ? "—" : after < 0 ? `Short by ${formatPrice(-after)}` : formatPrice(after)}
                tone={after !== null && after < 0 ? "bad" : undefined}
              />
            </dl>
            {after !== null && after < 0 && (
              <p className="mt-3 rounded-control bg-bad-bg px-3 py-2 text-sm text-bad" role="alert">
                Not enough balance. You can still pay: the saga will decline the payment for real, release the stock and fail the order.
              </p>
            )}
            {simulate !== "none" && (
              <p className="mt-3 text-sm text-muted">
                Test scenario: <span className="font-medium text-muted-strong">{scenario.label}</span>
              </p>
            )}

            <button type="button" className="btn-primary mt-6 w-full py-3.5 text-base" onClick={pay} disabled={busy !== null}>
              {busy === "order" ? "Placing order…" : `Pay ${formatPrice(cart.total)}`}
            </button>
            <p className="mt-3 text-center text-xs text-muted">
              Demo wallet: not real money. Every account starts with ₹10,00,000. <Link to="/wallet" className="underline underline-offset-2">Manage wallet</Link>
            </p>
          </section>
        )}

        <aside className="card h-fit p-6" aria-labelledby="summary-title">
          <h2 id="summary-title" className="section-title mb-4">
            Order summary
          </h2>
          <ul className="space-y-4">
            {cart.lines.map((line) => (
              <li key={line.productId} className="flex items-center gap-3">
                <ProductImage imageKey={line.imageKey} name={line.name} className="h-12 w-16 shrink-0 rounded-control" />
                <span className="min-w-0 flex-1 text-sm">
                  {line.name} <span className="text-muted">× {line.quantity}</span>
                </span>
                <span className="text-sm font-medium">{formatPrice(line.price * line.quantity)}</span>
              </li>
            ))}
          </ul>
          <div className="mt-5 space-y-1.5 border-t border-line pt-5 text-sm">
            <div className="flex justify-between text-muted-strong">
              <span>Delivery</span>
              <span className="font-medium text-ok">FREE</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-strong">Order total</span>
              <span className="text-lg font-semibold">{formatPrice(cart.total)}</span>
            </div>
          </div>
          {step === "details" && (
            <>
              <button type="submit" form="details-form" className="btn-primary mt-5 w-full" disabled={!detailsValid || cart.lines.length === 0}>
                Continue to payment
              </button>
              {!detailsValid && <p className="mt-3 text-center text-xs text-muted">Enter your name and an address.</p>}
            </>
          )}
        </aside>
      </div>
    </div>
  );
}

function Field(props: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
  autoComplete?: string;
  invalid?: boolean;
}) {
  return (
    <div>
      <label htmlFor={props.id} className="label">
        {props.label}
      </label>
      <input
        id={props.id}
        type={props.type ?? "text"}
        className="input"
        value={props.value}
        onChange={(e) => props.onChange(e.target.value)}
        autoComplete={props.autoComplete}
        aria-invalid={props.invalid}
        required
      />
    </div>
  );
}

function Row({ label, value, strong, tone }: { label: string; value: string; strong?: boolean; tone?: "bad" }) {
  return (
    <div className="flex items-center justify-between px-4 py-3.5">
      <dt className="text-muted-strong">{label}</dt>
      <dd className={`${strong ? "text-lg font-semibold" : "font-medium"} ${tone === "bad" ? "text-bad" : ""}`}>{value}</dd>
    </div>
  );
}
