"use client";

import { useEffect } from "react";
import { AlertTriangle, RefreshCcw, Home } from "lucide-react";
import Link from "next/link";
import { cn } from "@/lib/utils";

export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Log the error to an error reporting service in production, 
    // but avoid exposing it to the user.
    console.error("Dashboard error caught by boundary:", error);
  }, [error]);

  return (
    <div className="min-h-[70vh] flex flex-col items-center justify-center p-6 text-center animate-in fade-in duration-500">
      <div className="w-20 h-20 rounded-full bg-[var(--color-tiffany-danger)]/10 flex items-center justify-center mb-6">
        <AlertTriangle className="w-10 h-10 text-[var(--color-tiffany-danger)]" />
      </div>
      
      <h2 className="text-3xl font-bold tracking-tight mb-3">Something went wrong</h2>
      
      <p className="text-[var(--color-tiffany-text-secondary)] text-lg max-w-md mb-8">
        We encountered an unexpected error while loading this page. 
        Our systems have safely halted the operation to protect your server.
      </p>
      
      <div className="flex flex-col sm:flex-row gap-4">
        <button
          onClick={() => reset()}
          className={cn(
            "px-6 py-3 rounded-xl font-semibold transition-all flex items-center justify-center gap-2",
            "bg-[var(--color-tiffany-primary)] text-white hover:bg-[var(--color-tiffany-primary-hover)] shadow-[var(--shadow-tiffany-glow)]"
          )}
        >
          <RefreshCcw className="w-5 h-5" />
          Try Again
        </button>
        
        <Link 
          href="/dashboard/servers"
          className={cn(
            "px-6 py-3 rounded-xl font-semibold transition-all flex items-center justify-center gap-2",
            "bg-[var(--color-tiffany-surface-hover)] text-white hover:bg-[var(--color-tiffany-surface-active)] border border-[var(--color-tiffany-border)]"
          )}
        >
          <Home className="w-5 h-5" />
          Return to Servers
        </Link>
      </div>
    </div>
  );
}
