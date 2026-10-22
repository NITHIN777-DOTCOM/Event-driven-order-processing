/** Product page (/p/:productId): photo, title, rating, price block, highlights, buy box, description. */
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useCart } from "../cart";
import { DELIVER_TO, deliveryDate, discountPercent, slugOf, useCatalog } from "../catalog";
import { formatPrice } from "../format";
import { PinIcon, PriceLine, Stars, StockNote } from "../components/shop";
import { ErrorBanner, ProductImage, Skeleton } from "../components/ui";

const MAX_QTY = 10;

export function ProductPage() {
  const { productId } = useParams();
  const { products, error } = useCatalog();
  const cart = useCart();
  const navigate = useNavigate();
  const [quantity, setQuantity] = useState(1);

  if (error) return <ErrorBanner message={`Couldn't load the product. ${error}`} />;
  if (!products) {
    return (
      <div className="grid gap-8 lg:grid-cols-[1.1fr_1fr_300px]" aria-busy="true">
        <Skeleton className="aspect-[4/3]" />
        <div className="space-y-3">
          <Skeleton className="h-8 w-4/5" />
          <Skeleton className="h-4 w-1/3" />
          <Skeleton className="h-24 w-full" />
        </div>
        <Skeleton className="h-72" />
      </div>
    );
  }

  const product = products.find((p) => p.productId === productId);
  if (!product) {
    return (
      <div className="card px-6 py-12 text-center">
        <p className="font-semibold">This product doesn't exist.</p>
        <Link to="/" className="btn-primary mt-5">
          Back to the shop
        </Link>
      </div>
    );
  }

  const inCart = cart.lines.find((line) => line.productId === product.productId)?.quantity ?? 0;
  const available = Math.max(0, product.stock - inCart);
  const maxQty = Math.min(MAX_QTY, available);
  const off = discountPercent(product);

  return (
    <>
      <nav aria-label="Breadcrumb" className="mb-6 text-sm text-muted">
        <Link to="/" className="hover:text-ink">
          Shop
        </Link>
        <span className="mx-2">›</span>
        <Link to={`/c/${slugOf(product.category)}`} className="hover:text-ink">
          {product.category}
        </Link>
        <span className="mx-2">›</span>
        <span className="text-muted-strong">{product.name}</span>
      </nav>

      <div className="grid gap-8 lg:grid-cols-[1.1fr_1fr_300px]">
        <div className="card self-start overflow-hidden">
          <ProductImage imageKey={product.imageKey} name={product.name} className="aspect-[4/3] w-full" />
        </div>

        <div>
          <h1 className="text-[28px] font-semibold leading-tight">{product.name}</h1>
          <div className="mt-2">
            <Stars rating={product.rating} count={product.ratingCount} size={16} />
          </div>
          <div className="my-5 border-t border-line pt-5">
            {off > 0 && <p className="mb-1 text-sm font-semibold text-amber">Save {off}% today</p>}
            <PriceLine product={product} large />
            <p className="mt-1 text-sm text-muted">Inclusive of all taxes</p>
          </div>
          <h2 className="section-title mb-2">About this item</h2>
          <ul className="list-disc space-y-1.5 pl-5 text-[15px] text-muted-strong marker:text-pending">
            {product.highlights.map((h) => (
              <li key={h}>{h}</li>
            ))}
          </ul>
        </div>

        <aside className="card h-fit p-5" aria-label="Buy box">
          <p className="text-[24px] font-semibold">{formatPrice(product.price)}</p>
          {product.stock > 0 && (
            <p className="mt-2 text-sm text-muted-strong">
              <span className="font-semibold text-ink">FREE delivery</span> {deliveryDate()}
            </p>
          )}
          <p className="mt-2 flex items-center gap-1.5 text-sm text-muted">
            <PinIcon /> Deliver to {DELIVER_TO}
          </p>
          <div className="mt-3">
            <StockNote stock={product.stock} inStockLabel="In stock" />
          </div>

          {product.stock > 0 && (
            <>
              <label className="mt-4 flex items-center gap-2 text-sm text-muted-strong">
                Quantity
                <select
                  className="input w-20 py-1.5 text-sm"
                  value={Math.min(quantity, Math.max(1, maxQty))}
                  onChange={(e) => setQuantity(Number(e.target.value))}
                  disabled={maxQty === 0}
                >
                  {Array.from({ length: Math.max(1, maxQty) }, (_, i) => (
                    <option key={i + 1} value={i + 1}>
                      {i + 1}
                    </option>
                  ))}
                </select>
              </label>
              {inCart > 0 && <p className="mt-2 text-xs text-muted">{inCart} already in your cart</p>}
              <div className="mt-4 space-y-2.5">
                <button
                  type="button"
                  className="btn-primary w-full"
                  disabled={maxQty === 0}
                  onClick={() => {
                    cart.add(product, quantity);
                    cart.open(); // quick-add drawer
                  }}
                >
                  Add to Cart
                </button>
                <button
                  type="button"
                  className="btn w-full bg-ink text-white hover:bg-[#393E46]"
                  disabled={maxQty === 0 && inCart === 0}
                  onClick={() => {
                    if (maxQty > 0) cart.add(product, quantity);
                    navigate("/checkout");
                  }}
                >
                  Buy Now
                </button>
              </div>
            </>
          )}
          <p className="mt-4 border-t border-line pt-3 text-xs text-muted">Paid with DemoPay · Ships from Order Saga</p>
        </aside>
      </div>

      <section className="mt-12 max-w-3xl border-t border-line pt-8" aria-labelledby="description-title">
        <h2 id="description-title" className="section-title mb-2">
          Product description
        </h2>
        <p className="text-[15px] text-muted-strong">{product.description}</p>
      </section>
    </>
  );
}
