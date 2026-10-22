/**
 * Product listing for / (all), /c/:category, /deals and /search?q=&cat=.
 * Filters (price range, 4 stars & up, in stock only) and sort live in the URL, so every view can be linked.
 */
import { useMemo, useState } from "react";
import { Link, useLocation, useParams, useSearchParams } from "react-router-dom";
import { CATEGORIES, DEAL_DISCOUNT, categoryBySlug, discountPercent, slugOf, useCatalog } from "../catalog";
import type { Product } from "../types";
import { ProductCard, Stars } from "../components/shop";
import { ErrorBanner, Skeleton } from "../components/ui";

const PRICE_RANGES = [
  { id: "0-2000", label: "Under ₹2,000", min: 0, max: 2000 },
  { id: "2000-5000", label: "₹2,000 – ₹5,000", min: 2000, max: 5000 },
  { id: "5000-20000", label: "₹5,000 – ₹20,000", min: 5000, max: 20000 },
  { id: "20000-", label: "Over ₹20,000", min: 20000, max: Infinity },
];

const SORTS: { id: string; label: string; compare?: (a: Product, b: Product) => number }[] = [
  { id: "featured", label: "Featured" },
  { id: "price-asc", label: "Price: low to high", compare: (a, b) => a.price - b.price },
  { id: "price-desc", label: "Price: high to low", compare: (a, b) => b.price - a.price },
  { id: "rating", label: "Avg. customer rating", compare: (a, b) => b.rating - a.rating || b.ratingCount - a.ratingCount },
];

/** "Featured": in stock first, then most-reviewed. */
const featured = (a: Product, b: Product) => Number(b.stock > 0) - Number(a.stock > 0) || b.ratingCount - a.ratingCount;

export function Listing() {
  const { category: categorySlug } = useParams();
  const { pathname } = useLocation();
  const [params, setParams] = useSearchParams();
  const { products, error, reload } = useCatalog();
  const [filtersOpen, setFiltersOpen] = useState(false);

  const isSearch = pathname === "/search";
  const isDeals = pathname === "/deals";
  const query = (params.get("q") ?? "").trim();
  const category = categoryBySlug(categorySlug ?? (isSearch ? params.get("cat") ?? undefined : undefined));
  const price = PRICE_RANGES.find((r) => r.id === params.get("price"));
  const fourStars = params.get("rating") === "4";
  const inStockOnly = params.get("instock") === "1";
  const sort = SORTS.find((s) => s.id === params.get("sort")) ?? SORTS[0];

  const results = useMemo(() => {
    if (!products) return null;
    const words = query.toLowerCase().split(/\s+/).filter(Boolean);
    return products
      .filter((p) => !category || p.category === category.name)
      .filter((p) => !isDeals || discountPercent(p) >= DEAL_DISCOUNT)
      .filter((p) => words.every((w) => `${p.name} ${p.category}`.toLowerCase().includes(w)))
      .filter((p) => !price || (p.price >= price.min && p.price < price.max))
      .filter((p) => !fourStars || p.rating >= 4)
      .filter((p) => !inStockOnly || p.stock > 0)
      .sort(sort.compare ?? (isDeals ? (a, b) => discountPercent(b) - discountPercent(a) : featured));
  }, [products, category, isDeals, query, price, fourStars, inStockOnly, sort]);

  const setParam = (key: string, value: string | null) => {
    const next = new URLSearchParams(params);
    if (value === null) next.delete(key);
    else next.set(key, value);
    setParams(next, { replace: true });
  };
  const anyFilter = Boolean(price || fourStars || inStockOnly);

  const heading = isSearch
    ? query
      ? `Results for “${query}”${category ? ` in ${category.name}` : ""}`
      : category
        ? category.name
        : "All products"
    : isDeals
      ? "Today's deals"
      : category?.name ?? "Desk essentials, processed in real time.";
  const subheading = isDeals
    ? `Products at least ${DEAL_DISCOUNT}% off M.R.P.`
    : !isSearch && !category
      ? "Every order runs through an event-driven saga on AWS. Place one and watch each step happen live."
      : null;

  return (
    <>
      <div className="mb-6">
        <h1 className={`font-semibold leading-tight tracking-tight ${!isSearch && !category && !isDeals ? "text-[32px] sm:text-[44px]" : "text-[32px]"}`}>
          {heading}
        </h1>
        {subheading && <p className="mt-2 text-[15px] text-muted">{subheading}</p>}
      </div>

      {error && (
        <div className="mb-6">
          <ErrorBanner message={`Couldn't load products. ${error}`} onRetry={reload} />
        </div>
      )}

      <div className="grid gap-8 lg:grid-cols-[208px_1fr]">
        {/* Filters */}
        <aside aria-label="Filters">
          <button
            type="button"
            className="btn-secondary w-full lg:hidden"
            aria-expanded={filtersOpen}
            onClick={() => setFiltersOpen((open) => !open)}
          >
            {filtersOpen ? "Hide filters" : `Filters${anyFilter ? " (on)" : ""}`}
          </button>
          <div className={`${filtersOpen ? "mt-4 block" : "hidden"} space-y-7 lg:mt-0 lg:block`}>
            <FilterGroup title="Category">
              <ul className="space-y-1.5 text-sm">
                <li>
                  <Link to="/" className={!category && !isDeals ? "font-semibold" : "text-muted-strong hover:text-ink"}>
                    All categories
                  </Link>
                </li>
                {CATEGORIES.map((c) => (
                  <li key={c.slug}>
                    <Link to={`/c/${c.slug}`} className={category?.slug === c.slug ? "font-semibold" : "text-muted-strong hover:text-ink"}>
                      {c.name}
                    </Link>
                  </li>
                ))}
              </ul>
            </FilterGroup>
            <FilterGroup title="Price">
              <ul className="space-y-1.5 text-sm">
                {PRICE_RANGES.map((r) => (
                  <li key={r.id}>
                    <label className="flex cursor-pointer items-center gap-2">
                      <input
                        type="radio"
                        name="price"
                        className="accent-amber"
                        checked={price?.id === r.id}
                        onChange={() => setParam("price", r.id)}
                      />
                      {r.label}
                    </label>
                  </li>
                ))}
              </ul>
              {price && (
                <button type="button" className="mt-2 text-sm text-muted underline underline-offset-2" onClick={() => setParam("price", null)}>
                  Any price
                </button>
              )}
            </FilterGroup>
            <FilterGroup title="Customer rating">
              <label className="flex cursor-pointer items-center gap-2 text-sm">
                <input type="checkbox" className="accent-amber" checked={fourStars} onChange={(e) => setParam("rating", e.target.checked ? "4" : null)} />
                <Stars rating={4} /> <span>&amp; up</span>
              </label>
            </FilterGroup>
            <FilterGroup title="Availability">
              <label className="flex cursor-pointer items-center gap-2 text-sm">
                <input type="checkbox" className="accent-amber" checked={inStockOnly} onChange={(e) => setParam("instock", e.target.checked ? "1" : null)} />
                In stock only
              </label>
            </FilterGroup>
          </div>
        </aside>

        {/* Results */}
        <section aria-label="Results" className="min-w-0">
          <div className="mb-5 flex flex-wrap items-center justify-between gap-3 border-b border-line pb-4">
            <p className="text-sm text-muted-strong" aria-live="polite">
              {results ? (results.length ? `1–${results.length} of ${results.length} results` : "0 results") : "Loading…"}
              {category && !isSearch && <span className="text-muted"> in {category.name}</span>}
            </p>
            <label className="flex items-center gap-2 text-sm text-muted-strong">
              Sort by
              <select className="input w-auto py-1.5 text-sm" value={sort.id} onChange={(e) => setParam("sort", e.target.value === "featured" ? null : e.target.value)}>
                {SORTS.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.label}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {results === null && !error && (
            <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-4">
              {Array.from({ length: 8 }, (_, i) => (
                <div key={i} className="card overflow-hidden">
                  <Skeleton className="aspect-[4/3] rounded-none" />
                  <div className="space-y-2.5 p-4">
                    <Skeleton className="h-4 w-5/6" />
                    <Skeleton className="h-3 w-1/2" />
                    <Skeleton className="h-5 w-2/3" />
                    <Skeleton className="h-9 w-full" />
                  </div>
                </div>
              ))}
            </div>
          )}

          {results?.length === 0 && (
            <div className="card px-6 py-12 text-center">
              <p className="font-semibold">No products match.</p>
              <p className="mt-1 text-sm text-muted">Try a different search, or clear the filters.</p>
              <Link to={category ? `/c/${slugOf(category.name)}` : "/"} className="btn-secondary mt-5">
                Clear filters
              </Link>
            </div>
          )}

          {results && results.length > 0 && (
            <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-4">
              {results.map((product) => (
                <ProductCard key={product.productId} product={product} />
              ))}
            </div>
          )}
        </section>
      </div>
    </>
  );
}

function FilterGroup({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h2 className="mb-2.5 text-sm font-semibold">{title}</h2>
      {children}
    </div>
  );
}
