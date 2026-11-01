// Step 3.3 load test: POST /orders against the LIVE API at a controlled arrival rate (k6 "open model").
//
//   python scripts/loadtest_prep.py                      # products, buyers, wallets, tokens -> build/loadtest/run.json
//   k6 run --summary-export build/loadtest/k6-summary.json --out csv=build/loadtest/k6.csv loadtest/k6/orders.js
//   python scripts/loadtest_report.py                    # completion times, money, auditor, CloudWatch -> evidence
//
// Profile (ramping-arrival-rate, so a slow response never lowers the offered rate the way a closed VU loop would):
//   5 -> 50 orders/s over 5 min, hold 50/s for 3 min, then a 1-min spike offered at 100/s.
// The API stage is throttled at 50 req/s (burst 100) on purpose; above that API Gateway answers 429 before any
// Lambda runs. 429s are counted on their own (orders_throttled), never as errors: they are the designed limit.
// The script never polls order status (that would add load and skew the numbers); completion times come from
// DynamoDB statusHistory afterwards.
//
// Order mix: ~80% normal (1-3 lines, qty 1-2), ~10% partial fulfillment (one line found damaged after payment,
// simulate=item_unavailable), ~10% payment declined (simulate=payment_declined).

import http from "k6/http";
import { Counter, Trend } from "k6/metrics";
import exec from "k6/execution";

const run = JSON.parse(open("../../build/loadtest/run.json")); // gitignored: holds the buyers' access tokens
const PRODUCTS = Object.keys(run.products);
const BUYERS = run.buyers; // [{label, sub, token}]
const URL = `${run.api}/orders`;

const accepted = new Counter("orders_accepted"); // 200/202: the order exists and the saga will run
const throttled = new Counter("orders_throttled"); // 429 from the stage's rate limit (designed limit, not an error)
const failed = new Counter("orders_failed"); // anything else (4xx/5xx/network)
const acceptLatency = new Trend("accept_latency", true); // API latency of accepted requests only

export const options = {
  scenarios: {
    orders: {
      executor: "ramping-arrival-rate",
      startRate: 5,
      timeUnit: "1s",
      preAllocatedVUs: 150,
      maxVUs: 600,
      stages: [
        { target: 50, duration: "5m" }, // ramp
        { target: 50, duration: "3m" }, // hold at the stage limit
        { target: 100, duration: "10s" }, // spike: offer twice the limit...
        { target: 100, duration: "50s" }, // ...for a minute
      ],
    },
  },
  summaryTrendStats: ["avg", "med", "p(90)", "p(95)", "p(99)", "max"],
  discardResponseBodies: false,
};

function pick(list) {
  return list[Math.floor(Math.random() * list.length)];
}

function lines(count) {
  // distinct products, quantity 1-2
  const chosen = new Set();
  while (chosen.size < count) chosen.add(pick(PRODUCTS));
  return [...chosen].map((productId) => ({ productId, quantity: 1 + Math.floor(Math.random() * 2) }));
}

function order() {
  const roll = Math.random();
  if (roll < 0.8) return { kind: "normal", body: { items: lines(1 + Math.floor(Math.random() * 3)), simulate: "none" } };
  if (roll < 0.9) {
    const items = lines(2 + Math.floor(Math.random() * 2)); // 2-3 lines, one of them damaged
    return { kind: "partial", body: { items, simulate: "item_unavailable", simulateLine: 1 + Math.floor(Math.random() * items.length) } };
  }
  return { kind: "declined", body: { items: lines(1), simulate: "payment_declined" } };
}

export default function () {
  const buyer = BUYERS[exec.scenario.iterationInTest % BUYERS.length];
  const { kind, body } = order();
  body.customerName = `Load ${run.runId}`; // the report finds this run's orders by it
  const res = http.post(URL, JSON.stringify(body), {
    headers: { "Content-Type": "application/json", Authorization: buyer.token, "Idempotency-Key": crypto.randomUUID() },
    tags: { name: "POST /orders", kind },
    timeout: "30s",
  });
  if (res.status === 200 || res.status === 202) {
    accepted.add(1, { kind });
    acceptLatency.add(res.timings.duration, { kind });
  } else if (res.status === 429) {
    throttled.add(1);
  } else {
    failed.add(1, { status: String(res.status) });
  }
}
