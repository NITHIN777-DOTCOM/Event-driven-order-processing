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
  | "webhook_bad_signature"
  | "item_unavailable";

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

/** Per-line fulfillment (step 2.3): absent while the line is still reserved. */
export type LineFulfillment = "FULFILLED" | "WRITTEN_OFF";

export interface OrderItem {
  productId: string;
  name: string;
  quantity: number;
  unitPrice: number;
  lineId: string; // L1, L2, ...
  lineAmount: number; // quantity x unitPrice, fixed by the server when the order was created
  fulfillment?: LineFulfillment;
  refundedAmount?: number; // set once the line was refunded (it couldn't be fulfilled)
  writeOffReason?: string;
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
  refundedAmount?: number; // the sum of the line refunds (step 2.3)
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
  items: OrderItem[];
  refundedAmount: number | null;
}

export interface CreateOrderResponse {
  orderId: string;
  status: string;
  idempotencyKey: string;
  duplicate: boolean;
}

/** A checkout hold (POST /holds): units set aside for this user until expiresAt (server time). */
export type HoldStatus = "ACTIVE" | "CONSUMED" | "RELEASED" | "EXPIRED";

export interface Hold {
  holdId: string;
  status: HoldStatus;
  items: { productId: string; quantity: number }[];
  expiresAt: string;
  durationSeconds: number;
  secondsLeft: number;
  serverTime: string; // the server's clock when it answered: the countdown is computed against this, not Date.now()
}
