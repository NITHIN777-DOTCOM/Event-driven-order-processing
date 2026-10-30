/**
 * Thin client for the order-saga HTTP API. The base URL comes from /config.json at runtime, so one
 * build works against any deployment (Terraform writes config.json next to the app in S3).
 * Every request carries the signed-in user's Cognito ID token (when there is one) as "Authorization".
 */
import { getAccessToken, type AuthConfig } from "./auth";
import type { CancelResponse, CreateOrderResponse, Hold, Order, OrderSummary, Product, Simulate, Wallet } from "./types";

export interface AppConfig {
  apiUrl: string;
  region: string;
  auth: AuthConfig;
}

let apiUrl = "";

export async function loadConfig(): Promise<AppConfig> {
  const res = await fetch("/config.json", { cache: "no-store" });
  if (!res.ok) throw new Error(`Could not load /config.json (HTTP ${res.status})`);
  const config = (await res.json()) as AppConfig;
  apiUrl = config.apiUrl.replace(/\/$/, "");
  return config;
}

/** An API error with the server's own message ({"error": "..."}) when it sent one. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<{ status: number; body: T }> {
  let res: Response;
  const token = await getAccessToken();
  try {
    res = await fetch(`${apiUrl}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(token ? { Authorization: token } : {}), ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError("Can't reach the API. Check your connection and try again.", 0);
  }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new ApiError((body as { error?: string }).error ?? `Request failed (HTTP ${res.status})`, res.status);
  }
  return { status: res.status, body: body as T };
}

export async function getProducts(): Promise<Product[]> {
  return (await request<{ products: Product[] }>("/products")).body.products;
}

export async function getOrder(orderId: string): Promise<Order> {
  return (await request<Order>(`/orders/${encodeURIComponent(orderId)}`)).body;
}

/**
 * POST /orders/{id}/cancel. Idempotent: asking twice gives the same answer. A 409 means the cancel window has
 * closed (the order is already being fulfilled, or finished); its `error` code is mapped to a message by the caller.
 */
export async function cancelOrder(orderId: string, reason?: string): Promise<CancelResponse> {
  const { body } = await request<CancelResponse>(`/orders/${encodeURIComponent(orderId)}/cancel`, {
    method: "POST",
    body: JSON.stringify(reason ? { reason } : {}),
  });
  return body;
}

export async function listOrders(limit = 20): Promise<OrderSummary[]> {
  return (await request<{ orders: OrderSummary[] }>(`/orders?limit=${limit}`)).body.orders;
}

/** No email or user id: the API takes the customer's identity from the ID token only. */
export interface NewOrder {
  customerName: string;
  items: { productId: string; quantity: number }[];
  simulate: Simulate;
  holdId?: string; // the checkout hold to consume (the saga reserves afresh if it has ended)
}

/** POST /orders. Re-using an idempotencyKey returns the original order (HTTP 200, duplicate: true). */
export async function createOrder(order: NewOrder, idempotencyKey: string): Promise<CreateOrderResponse> {
  const { body } = await request<CreateOrderResponse>("/orders", {
    method: "POST",
    body: JSON.stringify(order),
    headers: { "Idempotency-Key": idempotencyKey },
  });
  return body;
}

export type HoldItems = { productId: string; quantity: number }[];

/** POST /holds: set the cart aside for 10 minutes. Replaces the user's previous hold. 409 = a product is short. */
export async function createHold(items: HoldItems): Promise<Hold> {
  return (await request<Hold>("/holds", { method: "POST", body: JSON.stringify({ items }) })).body;
}

/**
 * DELETE /holds/{holdId}: give the units back. `keepalive` lets the request finish while the page is closing,
 * which is why the token is passed in (there is no time to await a token refresh in "pagehide").
 */
export function releaseHold(holdId: string, token: string | undefined): void {
  void fetch(`${apiUrl}/holds/${encodeURIComponent(holdId)}`, {
    method: "DELETE",
    keepalive: true,
    headers: token ? { Authorization: token } : {},
  }).catch(() => undefined); // best effort: the hold expires on its own anyway
}

/** DemoPay: the signed-in user's balance + 20 most recent transactions (₹10,00,000 on first use). */
export async function getWallet(): Promise<Wallet> {
  return (await request<Wallet>("/wallet")).body;
}

/** Demo helper: set the signed-in user's balance (omit `balance` to reset to ₹10,00,000). */
export async function setWalletBalance(balance?: number): Promise<Wallet> {
  const { body } = await request<Wallet>("/wallet/reset", {
    method: "POST",
    body: JSON.stringify(balance === undefined ? {} : { balance }),
  });
  return body;
}
