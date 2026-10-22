/** Shop (/): headline + product grid with live stock from GET /products. */
import { useCallback, useEffect, useState } from "react";
import { getProducts } from "../api";
import { useCart } from "../cart";
import { formatPrice } from "../format";
import type { Product } from "../types";
import { ErrorBanner, ProductImage, Skeleton } from "../components/ui";

const LOW_STOCK = 20;

function StockLine({ stock }: { stock: number }) {
  if (stock <= 0) return <p className="text-sm font-medium text-bad">Out of stock</p>;
  if (stock < LOW_STOCK) return <p className="text-sm font-medium text-amber">Only {stock} left</p>;
  return <p className="text-sm text-muted">{stock} in stock</p>;
}

function ProductCard({ product }: { product: Product }) {
  const cart = useCart();
  const inCart = cart.lines.find((line) => line.productId === product.productId)?.quantity ?? 0;
  const canAdd = product.stock > inCart;

  return (
    <article className="card flex flex-col overflow-hidden">
      <ProductImage imageKey={product.imageKey} name={product.name} className="aspect-[4/3] w-full border-b border-line" />
      <div className="flex flex-1 flex-col gap-1 p-5">
        <h2 className="text-[15px] font-semibold">{product.name}</h2>
        <StockLine stock={product.stock} />
        <div className="mt-auto flex items-center justify-between pt-4">
          <span className="text-lg font-semibold">{formatPrice(product.price)}</span>
          <button
            type="button"
            className="btn-primary px-4 py-2"
            onClick={() => cart.add(product)}
            disabled={!canAdd}
            aria-label={`Add ${product.name} to cart`}
          >
            {inCart > 0 ? `Add · ${inCart}` : "Add"}
          </button>
        </div>
      </div>
    </article>
  );
}

export function Shop() {
  const [products, setProducts] = useState<Product[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(null);
    getProducts()
      .then(setProducts)
      .catch((err: Error) => setError(err.message));
  }, []);

  useEffect(load, [load]);

  return (
    <>
      <section className="mb-10 max-w-[880px] sm:mb-14">
        <h1 className="text-[32px] font-semibold leading-tight tracking-tight sm:text-[44px]">
          Desk essentials, processed in real time.
        </h1>
        <p className="mt-4 text-[15px] text-muted">
          Every order runs through an event-driven saga on AWS. Place one and watch each step happen live.
        </p>
      </section>

      {error && <ErrorBanner message={`Couldn't load products. ${error}`} onRetry={load} />}

      <section aria-label="Products" className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
        {products
          ? products.map((product) => <ProductCard key={product.productId} product={product} />)
          : !error &&
            Array.from({ length: 3 }, (_, index) => (
              <div key={index} className="card overflow-hidden">
                <Skeleton className="aspect-[4/3] rounded-none" />
                <div className="space-y-3 p-5">
                  <Skeleton className="h-4 w-2/3" />
                  <Skeleton className="h-3 w-1/3" />
                  <Skeleton className="h-9 w-full" />
                </div>
              </div>
            ))}
      </section>
    </>
  );
}
