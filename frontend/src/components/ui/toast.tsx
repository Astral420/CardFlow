import {
  createContext,
  useCallback,
  useContext,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { AnimatePresence, motion } from "framer-motion";
import { CheckCircle2, AlertCircle, Info, Loader2, X } from "lucide-react";
import { cn } from "@/lib/utils";

export type ToastVariant = "success" | "error" | "info" | "loading";

export interface Toast {
  id: string | number;
  title: string;
  description?: string;
  variant: ToastVariant;
  persistent?: boolean;
}

export interface ToastContextValue {
  toast: (t: Omit<Toast, "id"> & { id?: string | number }) => string | number;
  update: (id: string | number, t: Partial<Omit<Toast, "id">>) => void;
  dismiss: (id: string | number) => void;
}

const ToastContext = createContext<ToastContextValue | undefined>(undefined);

const ICONS: Record<ToastVariant, typeof CheckCircle2> = {
  success: CheckCircle2,
  error: AlertCircle,
  info: Info,
  loading: Loader2,
};

const COLORS: Record<ToastVariant, string> = {
  success: "text-accent-mint-foreground",
  error: "text-accent-rose-foreground",
  info: "text-accent-blue-foreground",
  loading: "text-accent-blue-foreground",
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const timers = useRef<Map<string | number, ReturnType<typeof setTimeout>>>(new Map());

  const clearExistingTimer = useCallback((id: string | number) => {
    const existing = timers.current.get(id);
    if (existing) {
      clearTimeout(existing);
      timers.current.delete(id);
    }
  }, []);

  const dismiss = useCallback(
    (id: string | number) => {
      clearExistingTimer(id);
      setToasts((prev) => prev.filter((t) => t.id !== id));
    },
    [clearExistingTimer]
  );

  const scheduleAutoDismiss = useCallback(
    (id: string | number, variant: ToastVariant, delay?: number) => {
      clearExistingTimer(id);
      const timeoutMs = delay ?? (variant === "error" ? 6000 : 4000);
      const timer = setTimeout(() => {
        dismiss(id);
      }, timeoutMs);
      timers.current.set(id, timer);
    },
    [clearExistingTimer, dismiss]
  );

  const toast = useCallback(
    (t: Omit<Toast, "id"> & { id?: string | number }) => {
      const id = t.id ?? Date.now() + Math.random();
      const newToast: Toast = { ...t, id };

      setToasts((prev) => {
        const index = prev.findIndex((item) => item.id === id);
        if (index >= 0) {
          const updated = [...prev];
          updated[index] = newToast;
          return updated;
        }
        return [...prev, newToast];
      });

      if (!t.persistent) {
        scheduleAutoDismiss(id, t.variant);
      } else {
        clearExistingTimer(id);
      }

      return id;
    },
    [clearExistingTimer, scheduleAutoDismiss]
  );

  const update = useCallback(
    (id: string | number, t: Partial<Omit<Toast, "id">>) => {
      let updatedToast: Toast | undefined;

      setToasts((prev) =>
        prev.map((item) => {
          if (item.id === id) {
            updatedToast = { ...item, ...t };
            return updatedToast;
          }
          return item;
        })
      );

      const targetVariant = t.variant ?? updatedToast?.variant ?? "info";
      const isPersistent = t.persistent !== undefined ? t.persistent : updatedToast?.persistent;

      if (!isPersistent && targetVariant !== "loading") {
        scheduleAutoDismiss(id, targetVariant);
      } else if (isPersistent) {
        clearExistingTimer(id);
      }
    },
    [clearExistingTimer, scheduleAutoDismiss]
  );

  return (
    <ToastContext.Provider value={{ toast, update, dismiss }}>
      {children}
      <div
        className="pointer-events-none fixed bottom-6 right-6 z-50 flex w-80 flex-col gap-2"
        aria-live="polite"
        aria-atomic="false"
      >
        <AnimatePresence>
          {toasts.map((t) => {
            const Icon = ICONS[t.variant];
            const isError = t.variant === "error";
            const isLoading = t.variant === "loading";

            return (
              <motion.div
                key={t.id}
                role={isError ? "alert" : "status"}
                initial={{ opacity: 0, y: 10, scale: 0.97 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: 4, scale: 0.97 }}
                transition={{ duration: 0.18 }}
                className="pointer-events-auto flex items-start gap-3 rounded-xl border border-border bg-surface p-4 shadow-float"
              >
                <Icon
                  aria-hidden="true"
                  className={cn(
                    "mt-0.5 h-4 w-4 shrink-0",
                    COLORS[t.variant],
                    isLoading && "animate-spin"
                  )}
                />
                <div className="flex-1 min-w-0">
                  <p className="text-body font-medium text-primary break-words">{t.title}</p>
                  {t.description && (
                    <p className="mt-0.5 text-caption text-muted-foreground break-words">
                      {t.description}
                    </p>
                  )}
                </div>
                {!isLoading && (
                  <button
                    onClick={() => dismiss(t.id)}
                    className="text-muted-foreground hover:text-primary transition-colors p-0.5 rounded focus:outline-none focus:ring-1 focus:ring-interactive"
                    aria-label="Dismiss notification"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                )}
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}
