/** Minimal toast notifications (e.g. "Added to cart"). Announced to screen readers via role="status". */
import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";

interface Toast {
  id: number;
  message: string;
  link?: { to: string; label: string };
}

const ToastContext = createContext<((message: string, link?: Toast["link"]) => void) | null>(null);
const TOAST_MS = 3500;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);

  const show = useCallback((message: string, link?: Toast["link"]) => {
    const id = nextId.current++;
    setToasts((current) => [...current.slice(-2), { id, message, link }]);
    window.setTimeout(() => setToasts((current) => current.filter((t) => t.id !== id)), TOAST_MS);
  }, []);

  return (
    <ToastContext.Provider value={show}>
      {children}
      <div className="pointer-events-none fixed inset-x-0 bottom-6 z-50 flex flex-col items-center gap-2 px-4" role="status" aria-live="polite">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className="feed-row-enter pointer-events-auto flex items-center gap-4 rounded-control bg-ink px-4 py-3 text-sm text-white"
          >
            <span>{toast.message}</span>
            {toast.link && (
              <Link to={toast.link.to} className="font-semibold text-amber-light underline-offset-2 hover:underline">
                {toast.link.label}
              </Link>
            )}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const show = useContext(ToastContext);
  if (!show) throw new Error("useToast must be used inside <ToastProvider>");
  return show;
}
