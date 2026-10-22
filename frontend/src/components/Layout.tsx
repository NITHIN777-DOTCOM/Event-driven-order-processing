/** Page chrome: dark header (logo, nav, cart), content area, one-line footer, cart drawer. */
import { NavLink, Outlet } from "react-router-dom";
import { useCart } from "../cart";
import { CartDrawer } from "./CartDrawer";

const GITHUB_URL = "https://github.com/NITHIN777-DOTCOM/Event-driven-order-processing";

function NavItem({ to, children }: { to: string; children: string }) {
  return (
    <NavLink
      to={to}
      end={to === "/"}
      className={({ isActive }) =>
        `rounded-control px-2 py-1 text-sm font-medium transition-colors ${isActive ? "text-white" : "text-white/65 hover:text-white"}`
      }
    >
      {children}
    </NavLink>
  );
}

export function Layout() {
  const cart = useCart();
  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-30 h-16 bg-ink">
        <div className="mx-auto flex h-full max-w-content items-center gap-4 px-4 sm:px-8">
          <NavLink to="/" className="flex min-w-0 items-center gap-3 text-white" aria-label="Event-Driven Order Processing, home">
            <span className="h-5 w-5 shrink-0 rounded-[4px] bg-amber" aria-hidden="true" />
            {/* On phones only the logo mark shows, which leaves room for the nav and cart. */}
            <span className="hidden truncate text-[15px] font-semibold sm:inline">Event-Driven Order Processing</span>
          </NavLink>
          <nav className="ml-auto flex items-center gap-1 sm:gap-3" aria-label="Main">
            <NavItem to="/">Shop</NavItem>
            <NavItem to="/orders">Orders</NavItem>
            <button
              type="button"
              onClick={cart.open}
              className="ml-1 inline-flex items-center gap-2 rounded-control border border-white/20 px-3 py-1.5 text-sm font-medium text-white hover:border-white/50"
              aria-label={`Open cart, ${cart.count} item${cart.count === 1 ? "" : "s"}`}
            >
              Cart
              <span className="min-w-[1.25rem] rounded-full bg-cream px-1.5 text-center text-xs font-semibold leading-5 text-ink">
                {cart.count}
              </span>
            </button>
          </nav>
        </div>
      </header>

      <main className="mx-auto w-full max-w-content flex-1 px-4 py-10 sm:px-8 sm:py-14">
        <Outlet />
      </main>

      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-content flex-wrap items-center justify-between gap-2 px-4 py-6 text-sm text-muted sm:px-8">
          <span>API Gateway · SQS · Step Functions · Lambda · DynamoDB · SNS</span>
          <a href={GITHUB_URL} target="_blank" rel="noreferrer" className="font-medium text-muted-strong hover:text-ink">
            GitHub
          </a>
        </div>
      </footer>

      <CartDrawer />
    </div>
  );
}
