import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/500.css";
import "@fontsource/ibm-plex-sans/600.css";
import "@fontsource/ibm-plex-mono/400.css";
import "./index.css";

import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Link, Route, Routes } from "react-router-dom";
import { loadConfig } from "./api";
import { CartProvider } from "./cart";
import { CatalogProvider } from "./catalog";
import { ToastProvider } from "./toast";
import { WalletProvider } from "./wallet";
import { Layout } from "./components/Layout";
import { ErrorBanner } from "./components/ui";
import { CartPage } from "./pages/CartPage";
import { Checkout } from "./pages/Checkout";
import { Listing } from "./pages/Listing";
import { Orders } from "./pages/Orders";
import { ProductPage } from "./pages/ProductPage";
import { Tracker } from "./pages/Tracker";
import { WalletPage } from "./pages/WalletPage";

function NotFound() {
  return (
    <div className="py-10">
      <h1 className="text-[32px] font-semibold">Page not found</h1>
      <Link to="/" className="btn-primary mt-6">
        Back to the shop
      </Link>
    </div>
  );
}

/** Loads /config.json (the API URL) before rendering any page. */
function App() {
  const [state, setState] = useState<"loading" | "ready" | string>("loading");

  useEffect(() => {
    loadConfig()
      .then(() => setState("ready"))
      .catch((err: Error) => setState(err.message));
  }, []);

  if (state === "loading") return null;
  if (state !== "ready") {
    return (
      <div className="mx-auto max-w-content p-8">
        <ErrorBanner message={`The app couldn't start: ${state}`} />
      </div>
    );
  }

  return (
    <CatalogProvider>
      <WalletProvider>
        <CartProvider>
          <BrowserRouter>
            <ToastProvider>
              <Routes>
                <Route element={<Layout />}>
                  <Route index element={<Listing />} />
                  <Route path="c/:category" element={<Listing />} />
                  <Route path="deals" element={<Listing />} />
                  <Route path="search" element={<Listing />} />
                  <Route path="p/:productId" element={<ProductPage />} />
                  <Route path="cart" element={<CartPage />} />
                  <Route path="checkout" element={<Checkout />} />
                  <Route path="wallet" element={<WalletPage />} />
                  <Route path="orders" element={<Orders />} />
                  <Route path="orders/:id" element={<Tracker />} />
                  <Route path="*" element={<NotFound />} />
                </Route>
              </Routes>
            </ToastProvider>
          </BrowserRouter>
        </CartProvider>
      </WalletProvider>
    </CatalogProvider>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
