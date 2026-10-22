/** Catalogue state: products loaded once from GET /products, plus shared helpers for listing pages. */
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { getProducts } from "./api";
import type { Product } from "./types";

export const CATEGORIES = [
  { slug: "keyboards", name: "Keyboards" },
  { slug: "mice", name: "Mice" },
  { slug: "audio", name: "Audio" },
  { slug: "monitors", name: "Monitors" },
  { slug: "accessories", name: "Accessories" },
] as const;

export const categoryBySlug = (slug?: string) => CATEGORIES.find((c) => c.slug === slug);
export const slugOf = (categoryName: string) => CATEGORIES.find((c) => c.name === categoryName)?.slug ?? "";

export const LOW_STOCK = 20;
export const DEAL_DISCOUNT = 25; // "Today's deals" = at least this % off MRP
export const DELIVER_TO = "Chennai 600127";

/** Whole-percent discount off MRP, e.g. 23. */
export const discountPercent = (p: Pick<Product, "price" | "mrp">) => (p.mrp > p.price ? Math.round((1 - p.price / p.mrp) * 100) : 0);

/** "Saturday, 24 October": free delivery is always two days out. */
export function deliveryDate(style: "long" | "short" = "long"): string {
  const date = new Date(Date.now() + 2 * 24 * 60 * 60 * 1000);
  const weekday = date.toLocaleDateString("en-GB", { weekday: style });
  const dayMonth = date.toLocaleDateString("en-GB", { day: "numeric", month: style });
  return `${weekday}, ${dayMonth}`;
}

interface CatalogState {
  products: Product[] | null;
  error: string | null;
  reload: () => void;
}

const CatalogContext = createContext<CatalogState | null>(null);

export function CatalogProvider({ children }: { children: ReactNode }) {
  const [products, setProducts] = useState<Product[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    setError(null);
    getProducts()
      .then(setProducts)
      .catch((err: Error) => setError(err.message));
  }, []);

  useEffect(reload, [reload]);

  return <CatalogContext.Provider value={{ products, error, reload }}>{children}</CatalogContext.Provider>;
}

export function useCatalog(): CatalogState {
  const value = useContext(CatalogContext);
  if (!value) throw new Error("useCatalog must be used inside <CatalogProvider>");
  return value;
}
