/** Orders (/orders): the 20 most recent orders (GET /orders, a GSI Query), refreshed every 5 s. */
import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { listOrders } from "../api";
import { formatDateTime, formatPrice, scenarioLabel } from "../format";
import type { OrderSummary } from "../types";
import { ErrorBanner, Skeleton, StatusPill, orderPill } from "../components/ui";

const REFRESH_MS = 5000;

export function Orders() {
  const [orders, setOrders] = useState<OrderSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  const load = useCallback(() => {
    listOrders(20)
      .then((result) => {
        setOrders(result);
        setError(null);
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  useEffect(() => {
    load();
    const id = window.setInterval(load, REFRESH_MS);
    return () => window.clearInterval(id);
  }, [load]);

  return (
    <>
      <div className="mb-8 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[32px] font-semibold leading-tight">Orders</h1>
          <p className="mt-2 text-muted">The 20 most recent orders. Refreshes every 5 seconds.</p>
        </div>
      </div>

      {error && (
        <div className="mb-6">
          <ErrorBanner message={`Couldn't load orders. ${error}`} onRetry={load} />
        </div>
      )}

      <div className="card overflow-hidden">
        <table className="w-full text-left text-[15px]">
          <thead className="border-b border-line text-[13px] text-muted">
            <tr>
              <th scope="col" className="px-4 py-3 font-medium sm:px-6">Order</th>
              <th scope="col" className="hidden px-4 py-3 font-medium sm:table-cell">Time</th>
              <th scope="col" className="hidden px-4 py-3 font-medium md:table-cell">Scenario</th>
              <th scope="col" className="px-4 py-3 text-right font-medium">Total</th>
              <th scope="col" className="px-4 py-3 font-medium sm:px-6">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {orders === null
              ? Array.from({ length: 5 }, (_, i) => (
                  <tr key={i}>
                    <td colSpan={5} className="px-6 py-4">
                      <Skeleton className="h-5 w-full" />
                    </td>
                  </tr>
                ))
              : orders.map((order) => {
                  const pill = orderPill(order.status, order.deadLettered);
                  return (
                    <tr
                      key={order.orderId}
                      className="cursor-pointer hover:bg-page"
                      onClick={() => navigate(`/orders/${order.orderId}`)}
                    >
                      <td className="px-4 py-3.5 sm:px-6">
                        <Link to={`/orders/${order.orderId}`} className="font-mono text-sm" onClick={(e) => e.stopPropagation()}>
                          {order.orderId}
                        </Link>
                      </td>
                      <td className="hidden whitespace-nowrap px-4 py-3.5 text-muted sm:table-cell">{formatDateTime(order.createdAt)}</td>
                      <td className="hidden px-4 py-3.5 text-muted-strong md:table-cell">{scenarioLabel(order.simulate)}</td>
                      <td className="whitespace-nowrap px-4 py-3.5 text-right">{formatPrice(order.totalAmount)}</td>
                      <td className="px-4 py-3.5 sm:px-6">
                        <StatusPill tone={pill.tone} label={pill.label} />
                      </td>
                    </tr>
                  );
                })}
            {orders?.length === 0 && (
              <tr>
                <td colSpan={5} className="px-6 py-10 text-center text-muted">
                  No orders yet. <Link to="/" className="font-medium text-ink underline underline-offset-2">Place one</Link>.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}
