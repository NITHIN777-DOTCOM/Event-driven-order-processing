/** Cart page (/cart): line items with quantity and remove, plus a subtotal box with "Proceed to checkout". */
import { Link, useNavigate } from "react-router-dom";
import { useCart } from "../cart";
import { formatPrice } from "../format";
import { StockNote } from "../components/shop";
import { ProductImage } from "../components/ui";

export function CartPage() {
  const cart = useCart();
  const navigate = useNavigate();

  if (cart.lines.length === 0) {
    return (
      <div className="card mx-auto max-w-lg px-6 py-12 text-center">
        <h1 className="text-[32px] font-semibold">Your cart is empty</h1>
        <p className="mt-2 text-muted">Browse the catalogue and add something you like.</p>
        <Link to="/" className="btn-primary mt-6">
          Continue shopping
        </Link>
      </div>
    );
  }

  return (
    <div className="grid gap-8 lg:grid-cols-[1fr_320px]">
      <section className="card p-6" aria-labelledby="cart-title">
        <div className="flex items-end justify-between border-b border-line pb-4">
          <h1 id="cart-title" className="text-[32px] font-semibold leading-tight">
            Shopping cart
          </h1>
          <span className="text-sm text-muted">Price</span>
        </div>
        <ul className="divide-y divide-line">
          {cart.lines.map((line) => (
            <li key={line.productId} className="flex gap-4 py-5">
              <Link to={`/p/${line.productId}`} className="shrink-0">
                <ProductImage imageKey={line.imageKey} name={line.name} className="h-24 w-32 rounded-control border border-line" />
              </Link>
              <div className="min-w-0 flex-1">
                <div className="flex items-start justify-between gap-4">
                  <Link to={`/p/${line.productId}`} className="font-medium leading-snug hover:underline">
                    {line.name}
                  </Link>
                  <span className="whitespace-nowrap text-lg font-semibold">{formatPrice(line.price * line.quantity)}</span>
                </div>
                <div className="mt-1">
                  <StockNote stock={line.stock} inStockLabel="In stock" />
                </div>
                <div className="mt-3 flex flex-wrap items-center gap-4 text-sm">
                  <label className="flex items-center gap-2 text-muted-strong">
                    Qty
                    <select
                      className="input w-20 py-1.5 text-sm"
                      value={line.quantity}
                      onChange={(e) => cart.setQuantity(line.productId, Number(e.target.value))}
                    >
                      {Array.from({ length: Math.max(1, Math.min(10, line.stock)) }, (_, i) => (
                        <option key={i + 1} value={i + 1}>
                          {i + 1}
                        </option>
                      ))}
                    </select>
                  </label>
                  <span className="h-4 w-px bg-line" aria-hidden="true" />
                  <button type="button" className="text-muted hover:text-bad" onClick={() => cart.remove(line.productId)}>
                    Remove
                  </button>
                  <span className="text-muted">{formatPrice(line.price)} each</span>
                </div>
              </div>
            </li>
          ))}
        </ul>
        <p className="border-t border-line pt-4 text-right text-lg">
          Subtotal ({cart.count} item{cart.count === 1 ? "" : "s"}): <span className="font-semibold">{formatPrice(cart.total)}</span>
        </p>
      </section>

      <aside className="card h-fit p-6">
        <p className="text-sm font-medium text-ok">Your order qualifies for FREE delivery.</p>
        <p className="mt-3 text-lg">
          Subtotal ({cart.count} item{cart.count === 1 ? "" : "s"}): <span className="font-semibold">{formatPrice(cart.total)}</span>
        </p>
        <button type="button" className="btn-primary mt-5 w-full" onClick={() => navigate("/checkout")}>
          Proceed to checkout
        </button>
        <p className="mt-3 text-center text-xs text-muted">You'll pay with your DemoPay wallet.</p>
      </aside>
    </div>
  );
}
