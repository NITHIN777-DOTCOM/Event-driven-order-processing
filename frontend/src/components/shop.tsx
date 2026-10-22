/** Storefront building blocks: rating stars, price line, stock note, delivery line, product card, icons. */
import { Link } from "react-router-dom";
import { useCart } from "../cart";
import { LOW_STOCK, deliveryDate, discountPercent } from "../catalog";
import { formatPrice } from "../format";
import { useToast } from "../toast";
import type { Product } from "../types";
import { ProductImage } from "./ui";

const STAR = "M10 1.5l2.6 5.4 5.9.8-4.3 4.1 1 5.9L10 14.9l-5.2 2.8 1-5.9L1.5 7.7l5.9-.8z";

/** Five stars filled to the rating (e.g. 4.3 -> 86%), drawn as two clipped layers. */
export function Stars({ rating, count, size = 14 }: { rating: number; count?: number; size?: number }) {
  const row = (fill: string) => (
    <span className="flex">
      {Array.from({ length: 5 }, (_, i) => (
        <svg key={i} viewBox="0 0 20 20" width={size} height={size} aria-hidden="true">
          <path d={STAR} fill={fill} />
        </svg>
      ))}
    </span>
  );
  return (
    <span className="inline-flex flex-wrap items-center gap-x-1.5 text-sm">
      <span className="relative inline-block" aria-label={`${rating.toFixed(1)} out of 5 stars`} role="img">
        {row("#E4DFD3")}
        <span className="absolute inset-0 overflow-hidden" style={{ width: `${(rating / 5) * 100}%` }}>
          {row("#C58940")}
        </span>
      </span>
      <span className="font-medium text-muted-strong">{rating.toFixed(1)}</span>
      {count !== undefined && <span className="text-muted">({count.toLocaleString("en-IN")})</span>}
    </span>
  );
}

/** "₹3,499  M.R.P. ₹4,999  –30%" */
export function PriceLine({ product, large = false }: { product: Product; large?: boolean }) {
  const off = discountPercent(product);
  return (
    <div className="flex flex-wrap items-baseline gap-x-2">
      <span className={`font-semibold ${large ? "text-[28px]" : "text-xl"}`}>{formatPrice(product.price)}</span>
      {off > 0 && (
        <>
          <span className="text-sm text-muted">
            M.R.P. <span className="line-through">{formatPrice(product.mrp)}</span>
          </span>
          <span className="text-sm font-semibold text-amber">–{off}%</span>
        </>
      )}
    </div>
  );
}

export function StockNote({ stock, inStockLabel }: { stock: number; inStockLabel?: string }) {
  if (stock <= 0) return <p className="text-sm font-medium text-bad">Currently unavailable</p>;
  if (stock < LOW_STOCK) return <p className="text-sm font-medium text-amber">Only {stock} left in stock</p>;
  return inStockLabel ? <p className="text-sm font-medium text-ok">{inStockLabel}</p> : null;
}

export function DeliveryLine() {
  return (
    <p className="text-sm text-muted-strong">
      <span className="font-semibold text-ink">FREE delivery</span> by <span className="whitespace-nowrap">{deliveryDate("short")}</span>
    </p>
  );
}

export function ProductCard({ product }: { product: Product }) {
  const cart = useCart();
  const toast = useToast();
  const inCart = cart.lines.find((line) => line.productId === product.productId)?.quantity ?? 0;
  const canAdd = product.stock > inCart;
  const href = `/p/${product.productId}`;

  return (
    <article className="card flex flex-col overflow-hidden">
      <Link to={href} tabIndex={-1} aria-hidden="true">
        <ProductImage imageKey={product.imageKey} name={product.name} className="aspect-[4/3] w-full border-b border-line" />
      </Link>
      <div className="flex flex-1 flex-col gap-1.5 p-3 sm:p-4">
        <h2 className="line-clamp-2 min-h-[2.75rem] text-[15px] font-medium leading-snug">
          <Link to={href} className="hover:underline hover:underline-offset-2">
            {product.name}
          </Link>
        </h2>
        <Stars rating={product.rating} count={product.ratingCount} />
        <PriceLine product={product} />
        {product.stock > 0 && <DeliveryLine />}
        <StockNote stock={product.stock} />
        <button
          type="button"
          className="btn-primary mt-auto w-full py-2"
          disabled={!canAdd}
          onClick={() => {
            cart.add(product);
            toast(`Added ${product.name} to cart`, { to: "/cart", label: "View cart" });
          }}
          aria-label={`Add ${product.name} to cart`}
        >
          {product.stock <= 0 ? "Unavailable" : "Add to cart"}
        </button>
      </div>
    </article>
  );
}

export const SearchIcon = () => (
  <svg viewBox="0 0 24 24" width={20} height={20} fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" aria-hidden="true">
    <circle cx="11" cy="11" r="7" />
    <path d="m20 20-4-4" />
  </svg>
);

export const PinIcon = () => (
  <svg viewBox="0 0 24 24" width={18} height={18} fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinejoin="round" aria-hidden="true">
    <path d="M12 21s-7-6.2-7-11.5a7 7 0 1 1 14 0C19 14.8 12 21 12 21z" />
    <circle cx="12" cy="9.5" r="2.5" />
  </svg>
);
