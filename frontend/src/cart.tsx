/** Cart state (React context), persisted to localStorage so a refresh keeps the cart. */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { storage } from "./format";
import type { Product } from "./types";

export interface CartLine {
  productId: string;
  name: string;
  price: number;
  imageKey: string | null;
  stock: number;
  quantity: number;
}

interface CartState {
  lines: CartLine[];
  count: number;
  total: number;
  isOpen: boolean;
  open: () => void;
  close: () => void;
  /** Add `quantity` (default 1), capped at the product's stock. */
  add: (product: Product, quantity?: number) => void;
  setQuantity: (productId: string, quantity: number) => void;
  remove: (productId: string) => void;
  clear: () => void;
}

const CartContext = createContext<CartState | null>(null);
const STORAGE_KEY = "order-saga.cart";

function loadLines(): CartLine[] {
  try {
    const parsed = JSON.parse(storage.get(STORAGE_KEY) ?? "[]");
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function CartProvider({ children }: { children: ReactNode }) {
  const [lines, setLines] = useState<CartLine[]>(loadLines);
  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => storage.set(STORAGE_KEY, JSON.stringify(lines)), [lines]);

  const add = useCallback((product: Product, quantity = 1) => {
    setLines((current) => {
      const existing = current.find((line) => line.productId === product.productId);
      if (existing) {
        return current.map((line) =>
          line.productId === product.productId
            ? { ...line, stock: product.stock, quantity: Math.min(line.quantity + quantity, product.stock) }
            : line,
        );
      }
      const { productId, name, price, imageKey, stock } = product;
      return [...current, { productId, name, price, imageKey, stock, quantity: Math.min(quantity, stock) }];
    });
  }, []);

  const setQuantity = useCallback((productId: string, quantity: number) => {
    setLines((current) =>
      current
        .map((line) => (line.productId === productId ? { ...line, quantity: Math.min(quantity, line.stock) } : line))
        .filter((line) => line.quantity > 0),
    );
  }, []);

  const value = useMemo<CartState>(
    () => ({
      lines,
      count: lines.reduce((sum, line) => sum + line.quantity, 0),
      total: lines.reduce((sum, line) => sum + line.quantity * line.price, 0),
      isOpen,
      open: () => setIsOpen(true),
      close: () => setIsOpen(false),
      add,
      setQuantity,
      remove: (productId) => setLines((current) => current.filter((line) => line.productId !== productId)),
      clear: () => setLines([]),
    }),
    [lines, isOpen, add, setQuantity],
  );

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>;
}

export function useCart(): CartState {
  const cart = useContext(CartContext);
  if (!cart) throw new Error("useCart must be used inside <CartProvider>");
  return cart;
}
