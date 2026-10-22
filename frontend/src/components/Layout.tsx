/**
 * Page chrome. Sticky two-row header:
 *   row 1 (#222831): logo · deliver-to · search (category + query) · DemoPay wallet · Orders · Cart
 *   row 2 (#393E46): category links + Today's deals
 * Then the content area, a one-line footer and the quick-add cart drawer.
 */
import { useEffect, useState, type FormEvent } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { useCart } from "../cart";
import { CATEGORIES, DELIVER_TO } from "../catalog";
import { formatPrice } from "../format";
import { useWallet } from "../wallet";
import { CartDrawer } from "./CartDrawer";
import { PinIcon, SearchIcon } from "./shop";

const GITHUB_URL = "https://github.com/NITHIN777-DOTCOM/Event-driven-order-processing";

function SearchBar() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const location = useLocation();
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("");

  // Keep the box in sync with the URL when the user lands on a search results page.
  useEffect(() => {
    if (location.pathname === "/search") {
      setQuery(params.get("q") ?? "");
      setCategory(params.get("cat") ?? "");
    }
  }, [location.pathname, params]);

  function submit(event: FormEvent) {
    event.preventDefault();
    const next = new URLSearchParams();
    if (query.trim()) next.set("q", query.trim());
    if (category) next.set("cat", category);
    navigate(`/search?${next}`);
  }

  return (
    <form role="search" onSubmit={submit} className="flex h-10 w-full overflow-hidden rounded-control bg-white">
      <label htmlFor="search-category" className="sr-only">
        Search in category
      </label>
      <select
        id="search-category"
        value={category}
        onChange={(e) => setCategory(e.target.value)}
        className="max-w-[7.5rem] shrink-0 border-r border-line bg-tile px-2 text-[13px] text-muted-strong focus:outline-none sm:max-w-none"
      >
        <option value="">All</option>
        {CATEGORIES.map((c) => (
          <option key={c.slug} value={c.slug}>
            {c.name}
          </option>
        ))}
      </select>
      <label htmlFor="search-query" className="sr-only">
        Search products
      </label>
      <input
        id="search-query"
        type="search"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Search keyboards, mice, monitors…"
        className="min-w-0 flex-1 px-3 text-[15px] text-ink placeholder:text-pending focus:outline-none"
      />
      <button type="submit" className="flex w-12 shrink-0 items-center justify-center bg-amber text-ink hover:bg-amber-light" aria-label="Search">
        <SearchIcon />
      </button>
    </form>
  );
}

function HeaderLink({ to, top, main, className = "" }: { to: string; top: string; main: string; className?: string }) {
  return (
    <Link to={to} className={`flex flex-col rounded-control px-2 py-1 leading-tight text-white hover:bg-white/10 ${className}`}>
      <span className="text-[11px] text-white/60">{top}</span>
      <span className="whitespace-nowrap text-sm font-semibold">{main}</span>
    </Link>
  );
}

export function Layout() {
  const cart = useCart();
  const { wallet } = useWallet();

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-30">
        {/* Row 1 */}
        <div className="bg-ink">
          <div className="mx-auto flex max-w-content flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3 sm:px-8 lg:h-16 lg:flex-nowrap lg:py-0">
            <Link to="/" className="flex shrink-0 items-center gap-2.5 text-white" aria-label="Event-Driven Order Processing, home">
              <span className="h-5 w-5 rounded-[4px] bg-amber" aria-hidden="true" />
              <span className="hidden text-[15px] font-semibold leading-tight xl:inline">
                Event-Driven
                <br />
                Order Processing
              </span>
            </Link>
            <div className="hidden shrink-0 items-center gap-1.5 px-2 text-white lg:flex">
              <PinIcon />
              <span className="flex flex-col leading-tight">
                <span className="text-[11px] text-white/60">Deliver to</span>
                <span className="whitespace-nowrap text-sm font-semibold">{DELIVER_TO}</span>
              </span>
            </div>
            <div className="order-last w-full lg:order-none lg:flex-1">
              <SearchBar />
            </div>
            <nav className="ml-auto flex items-center gap-1" aria-label="Account">
              <HeaderLink to="/wallet" top="DemoPay" main={wallet ? formatPrice(wallet.balance) : "Wallet"} />
              <HeaderLink to="/orders" top="Returns &" main="Orders" className="hidden sm:flex" />
              <Link
                to="/cart"
                className="ml-1 inline-flex items-center gap-2 rounded-control border border-white/20 px-3 py-2 text-sm font-semibold text-white hover:border-white/50"
                aria-label={`Cart, ${cart.count} item${cart.count === 1 ? "" : "s"}`}
              >
                Cart
                <span className="min-w-[1.25rem] rounded-full bg-cream px-1.5 text-center text-xs font-semibold leading-5 text-ink">{cart.count}</span>
              </Link>
            </nav>
          </div>
        </div>
        {/* Row 2 */}
        <div className="bg-[#393E46]">
          <nav className="mx-auto flex h-10 max-w-content items-center gap-1 overflow-x-auto px-4 text-sm sm:px-8" aria-label="Categories">
            <CategoryLink to="/" end label="All" />
            {CATEGORIES.map((c) => (
              <CategoryLink key={c.slug} to={`/c/${c.slug}`} label={c.name} />
            ))}
            <CategoryLink to="/deals" label="Today's deals" accent />
            <CategoryLink to="/orders" label="Orders" className="sm:hidden" />
          </nav>
        </div>
      </header>

      <main className="mx-auto w-full max-w-content flex-1 px-4 py-8 sm:px-8 sm:py-10">
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

function CategoryLink({ to, label, end, accent, className = "" }: { to: string; label: string; end?: boolean; accent?: boolean; className?: string }) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        `shrink-0 whitespace-nowrap rounded-control px-2.5 py-1 font-medium transition-colors ${
          isActive ? "bg-white/15 text-white" : accent ? "text-amber-light hover:text-white" : "text-white/80 hover:text-white"
        } ${className}`
      }
    >
      {label}
    </NavLink>
  );
}
