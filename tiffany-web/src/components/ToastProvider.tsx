"use client";

import { createContext, useContext, useState, ReactNode } from "react";
import { CheckCircle, AlertTriangle, X } from "lucide-react";
import { cn } from "@/lib/utils";

type ToastType = "success" | "error" | "info";

interface Toast {
  id: string;
  title: string;
  description?: string;
  type: ToastType;
}

interface ToastContextType {
  toast: (options: Omit<Toast, "id">) => void;
}

const ToastContext = createContext<ToastContextType | undefined>(undefined);

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error("useToast must be used within a ToastProvider");
  }
  return context;
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const toast = ({ title, description, type }: Omit<Toast, "id">) => {
    const id = Math.random().toString(36).substr(2, 9);
    setToasts((prev) => [...prev, { id, title, description, type }]);
    
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 5000);
  };

  const removeToast = (id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  };

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <div className="fixed bottom-0 right-0 z-[100] p-6 flex flex-col gap-3 pointer-events-none w-full sm:w-[400px]">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={cn(
              "pointer-events-auto flex items-start gap-3 p-4 rounded-xl border shadow-xl animate-in slide-in-from-right-8 fade-in duration-300 relative overflow-hidden",
              t.type === "success" && "bg-[var(--color-tiffany-bg-elevated)] border-green-500/30",
              t.type === "error" && "bg-[var(--color-tiffany-bg-elevated)] border-[var(--color-tiffany-danger)]/50",
              t.type === "info" && "bg-[var(--color-tiffany-bg-elevated)] border-[var(--color-tiffany-primary)]/30"
            )}
          >
            {t.type === "success" && <div className="absolute left-0 top-0 bottom-0 w-1 bg-green-500 shadow-[var(--shadow-tiffany-glow)]" />}
            {t.type === "error" && <div className="absolute left-0 top-0 bottom-0 w-1 bg-[var(--color-tiffany-danger)] shadow-[var(--shadow-tiffany-glow)]" />}
            {t.type === "info" && <div className="absolute left-0 top-0 bottom-0 w-1 bg-[var(--color-tiffany-primary)] shadow-[var(--shadow-tiffany-glow)]" />}
            
            <div className="shrink-0 mt-0.5">
              {t.type === "success" && <CheckCircle className="w-5 h-5 text-green-400" />}
              {t.type === "error" && <AlertTriangle className="w-5 h-5 text-[var(--color-tiffany-danger)]" />}
              {t.type === "info" && <div className="w-5 h-5 rounded-full bg-[var(--color-tiffany-primary)]/20 border border-[var(--color-tiffany-primary)]" />}
            </div>
            
            <div className="flex-1 min-w-0 pr-6">
              <div className="text-sm font-bold text-white">{t.title}</div>
              {t.description && (
                <div className="text-sm text-[var(--color-tiffany-text-secondary)] mt-1">{t.description}</div>
              )}
            </div>
            
            <button 
              onClick={() => removeToast(t.id)}
              className="absolute right-4 top-4 text-[var(--color-tiffany-text-muted)] hover:text-white transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
