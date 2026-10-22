/** Checkout (/checkout): contact details, demo test scenario, duplicate test, order summary. */
import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { createOrder, type NewOrder } from "../api";
import { useCart } from "../cart";
import { SCENARIOS, formatPrice, storage } from "../format";
import type { Simulate } from "../types";
import { ErrorBanner, ProductImage } from "../components/ui";

const CONTACT_KEY = "order-saga.contact";
const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

function loadContact(): { name: string; email: string } {
  try {
    const saved = JSON.parse(storage.get(CONTACT_KEY) ?? "{}");
    return { name: String(saved.name ?? ""), email: String(saved.email ?? "") };
  } catch {
    return { name: "", email: "" };
  }
}

export function Checkout() {
  const cart = useCart();
  const navigate = useNavigate();
  const [contact, setContact] = useState(loadContact);
  const [simulate, setSimulate] = useState<Simulate>("none");
  const [busy, setBusy] = useState<"order" | "duplicate" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [duplicateResult, setDuplicateResult] = useState<{ requests: number; orderIds: string[] } | null>(null);

  const scenario = SCENARIOS.find((s) => s.value === simulate)!;
  const contactValid = contact.name.trim().length > 0 && EMAIL_PATTERN.test(contact.email.trim());

  const buildOrder = (): NewOrder => {
    storage.set(CONTACT_KEY, JSON.stringify(contact));
    return {
      customerName: contact.name.trim(),
      customerEmail: contact.email.trim(),
      items: cart.lines.map((line) => ({ productId: line.productId, quantity: line.quantity })),
      simulate,
    };
  };

  async function placeOrder(event: FormEvent) {
    event.preventDefault();
    if (!contactValid || busy) return;
    setBusy("order");
    setError(null);
    try {
      const result = await createOrder(buildOrder(), crypto.randomUUID());
      cart.clear();
      navigate(`/orders/${result.orderId}`);
    } catch (err) {
      setError((err as Error).message);
      setBusy(null);
    }
  }

  /** Sends the SAME request 3 times with ONE Idempotency-Key: the API must create exactly one order. */
  async function duplicateTest() {
    if (!contactValid || busy) return;
    setBusy("duplicate");
    setError(null);
    setDuplicateResult(null);
    try {
      const order = buildOrder();
      const key = crypto.randomUUID();
      const results = [];
      for (let i = 0; i < 3; i++) results.push(await createOrder(order, key));
      setDuplicateResult({ requests: results.length, orderIds: [...new Set(results.map((r) => r.orderId))] });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(null);
    }
  }

  if (cart.lines.length === 0 && !duplicateResult) {
    return (
      <div className="card mx-auto max-w-lg p-8 text-center">
        <h1 className="text-[32px] font-semibold">Checkout</h1>
        <p className="mt-3 text-muted">Your cart is empty.</p>
        <Link to="/" className="btn-primary mt-6">
          Browse products
        </Link>
      </div>
    );
  }

  return (
    <form onSubmit={placeOrder} noValidate>
      <h1 className="mb-8 text-[32px] font-semibold leading-tight">Checkout</h1>
      {error && (
        <div className="mb-6">
          <ErrorBanner message={error} />
        </div>
      )}

      <div className="grid gap-8 lg:grid-cols-[1fr_360px]">
        <div className="space-y-6">
          <section className="card p-6" aria-labelledby="contact-title">
            <h2 id="contact-title" className="section-title mb-4">
              Contact
            </h2>
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label htmlFor="name" className="label">
                  Name
                </label>
                <input
                  id="name"
                  className="input"
                  autoComplete="name"
                  value={contact.name}
                  onChange={(e) => setContact({ ...contact, name: e.target.value })}
                  required
                  maxLength={100}
                />
              </div>
              <div>
                <label htmlFor="email" className="label">
                  Email
                </label>
                <input
                  id="email"
                  type="email"
                  className="input"
                  autoComplete="email"
                  value={contact.email}
                  onChange={(e) => setContact({ ...contact, email: e.target.value })}
                  required
                  aria-invalid={contact.email.length > 0 && !EMAIL_PATTERN.test(contact.email.trim())}
                />
              </div>
            </div>
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
              <button
                type="button"
                className="btn-secondary"
                onClick={duplicateTest}
                disabled={!contactValid || busy !== null || cart.lines.length === 0}
              >
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
        </div>

        <aside className="card h-fit p-6" aria-labelledby="summary-title">
          <h2 id="summary-title" className="section-title mb-4">
            Summary
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
          <div className="mt-5 flex items-center justify-between border-t border-line pt-5">
            <span className="text-muted-strong">Total</span>
            <span className="text-lg font-semibold">{formatPrice(cart.total)}</span>
          </div>
          <button type="submit" className="btn-primary mt-5 w-full" disabled={!contactValid || busy !== null || cart.lines.length === 0}>
            {busy === "order" ? "Placing order…" : "Place order"}
          </button>
          {!contactValid && <p className="mt-3 text-center text-xs text-muted">Enter your name and a valid email to continue.</p>}
        </aside>
      </div>
    </form>
  );
}
