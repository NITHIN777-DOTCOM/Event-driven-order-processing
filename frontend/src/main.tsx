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
import { Layout } from "./components/Layout";
import { ErrorBanner } from "./components/ui";
import { Checkout } from "./pages/Checkout";
import { Orders } from "./pages/Orders";
import { Shop } from "./pages/Shop";
import { Tracker } from "./pages/Tracker";

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
    <CartProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Shop />} />
            <Route path="checkout" element={<Checkout />} />
            <Route path="orders" element={<Orders />} />
            <Route path="orders/:id" element={<Tracker />} />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </CartProvider>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
