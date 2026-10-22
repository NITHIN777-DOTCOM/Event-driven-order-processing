/** Right-side cart drawer: items, quantity stepper, remove, total, Checkout. Esc or the backdrop closes it. */
import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useCart } from "../cart";
import { formatPrice } from "../format";
import { ProductImage } from "./ui";

export function CartDrawer() {
  const cart = useCart();
  const navigate = useNavigate();
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!cart.isOpen) return;
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && cart.close();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [cart.isOpen, cart.close]);

  if (!cart.isOpen) return null;

  return (
    <div className="fixed inset-0 z-40">
      <div className="absolute inset-0 bg-ink/40" onClick={cart.close} aria-hidden="true" />
      <aside
        role="dialog"
        aria-modal="true"
        aria-labelledby="cart-title"
        className="absolute right-0 top-0 flex h-full w-full max-w-[400px] flex-col border-l border-line bg-white"
      >
        <div className="flex items-center justify-between border-b border-line px-6 py-5">
          <h2 id="cart-title" className="text-lg font-semibold">
            Cart
          </h2>
          <button ref={closeRef} type="button" onClick={cart.close} className="rounded-control px-2 py-1 text-sm text-muted hover:text-ink">
            Close
          </button>
        </div>

        {cart.lines.length === 0 ? (
          <p className="px-6 py-10 text-muted">Your cart is empty.</p>
        ) : (
          <ul className="flex-1 divide-y divide-line overflow-y-auto px-6">
            {cart.lines.map((line) => (
              <li key={line.productId} className="flex gap-4 py-5">
                <ProductImage imageKey={line.imageKey} name={line.name} className="h-14 w-[75px] shrink-0 rounded-control" />
                <div className="min-w-0 flex-1">
                  <div className="flex items-start justify-between gap-3">
                    <p className="font-medium leading-snug">{line.name}</p>
                    <p className="whitespace-nowrap font-medium">{formatPrice(line.price * line.quantity)}</p>
                  </div>
                  <div className="mt-2 flex items-center justify-between">
                    <div className="inline-flex items-center rounded-control border border-line" role="group" aria-label={`Quantity of ${line.name}`}>
                      <button
                        type="button"
                        className="h-8 w-8 text-muted-strong hover:text-ink"
                        onClick={() => cart.setQuantity(line.productId, line.quantity - 1)}
                        aria-label="Decrease quantity"
                      >
                        −
                      </button>
                      <span className="w-8 text-center text-sm font-medium" aria-live="polite">
                        {line.quantity}
                      </span>
                      <button
                        type="button"
                        className="h-8 w-8 text-muted-strong hover:text-ink disabled:opacity-40"
                        onClick={() => cart.setQuantity(line.productId, line.quantity + 1)}
                        disabled={line.quantity >= line.stock}
                        aria-label="Increase quantity"
                      >
                        +
                      </button>
                    </div>
                    <button type="button" className="text-sm text-muted hover:text-bad" onClick={() => cart.remove(line.productId)}>
                      Remove
                    </button>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}

        <div className="mt-auto border-t border-line px-6 py-5">
          <div className="mb-4 flex items-center justify-between">
            <span className="text-muted-strong">Total</span>
            <span className="text-lg font-semibold">{formatPrice(cart.total)}</span>
          </div>
          <button
            type="button"
            className="btn-primary w-full"
            disabled={cart.lines.length === 0}
            onClick={() => {
              cart.close();
              navigate("/checkout");
            }}
          >
            Checkout
          </button>
        </div>
      </aside>
    </div>
  );
}
