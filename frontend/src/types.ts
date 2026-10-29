/** Shapes returned by the order-saga HTTP API (see src/lambdas/* in the repo root). */

export type Simulate =
  | "none"
  | "payment_declined"
  | "payment_flaky"
  | "out_of_stock"
  | "poison"
  | "payment_timeout"
  | "payment_late"
  | "webhook_duplicate"
  | "webhook_bad_signature";

export interface Product {
  productId: string;
  name: string;
  category: string;
  price: number;
  mrp: number;
  rating: number;
  ratingCount: number;
  stock: number;
  highlights: string[];
  description: string;
  imageKey: string | null;
}

export type WalletTxnType = "DEBIT" | "CREDIT" | "ADJUST";

export interface WalletTxn {
  txnId: string;
  type: WalletTxnType;
  amount: number;
  balanceAfter: number;
  orderId: string | null;
  ts: string;
  note: string;
}

export interface Wallet {
  walletId: string;
  balance: number;
  currency: string;
  transactions: WalletTxn[];
}

export interface OrderItem {
  productId: string;
  name: string;
  quantity: number;
  unitPrice: number;
}

export interface HistoryEntry {
  status: string;
  timestamp: string;
  detail: string;
}

export type FeedLevel = "info" | "retry" | "error";

export interface FeedRow {
  time: string;
  service: string;
  message: string;
  level: FeedLevel;
  note?: string;
}

export interface ConsoleLinks {
  execution: string | null;
  dynamodbItem: string;
  logs: string;
}

export interface Order {
  orderId: string;
  customerName: string;
  customerEmail: string;
  items: OrderItem[];
  totalAmount: number;
  currency: string;
  status: string;
  statusHistory: HistoryEntry[];
  simulate: Simulate;
  createdAt: string;
  updatedAt: string;
  executionArn?: string;
  paymentId?: string;
  paymentAttempts?: number;
  failureReason?: string;
  deadLettered?: boolean;
  released?: boolean;
  paidAmount?: number;
  refunded?: boolean;
  feed: FeedRow[];
  consoleLinks: ConsoleLinks;
}

export interface OrderSummary {
  orderId: string;
  createdAt: string;
  status: string;
  simulate: Simulate;
  totalAmount: number;
  currency: string;
  customerName: string;
  deadLettered: boolean | null;
}

export interface CreateOrderResponse {
  orderId: string;
  status: string;
  idempotencyKey: string;
  duplicate: boolean;
}
