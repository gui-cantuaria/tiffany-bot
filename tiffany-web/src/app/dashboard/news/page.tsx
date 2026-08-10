"use client";

import { Suspense } from "react";
import { Bot, Rss, ArrowRight } from "lucide-react";
import { useSearchParams } from "next/navigation";

function NewsSettingsContent() {
  const searchParams = useSearchParams();
  const guildId = searchParams.get("server");

  return (
    <div className="space-y-8 animate-in fade-in duration-500 pb-24">
      <div>
        <h2 className="text-3xl font-bold tracking-tight mb-2 flex items-center gap-2">
          <Bot className="w-8 h-8 text-[var(--color-tiffany-primary)]" /> News Feeds
        </h2>
        <p className="text-[var(--color-tiffany-text-secondary)] text-lg">
          Automated technology and gaming news delivery.
        </p>
      </div>

      <div className="p-12 border border-[var(--color-tiffany-border)] rounded-2xl bg-[var(--color-tiffany-surface)] text-center flex flex-col items-center">
        <div className="w-16 h-16 rounded-full bg-[var(--color-tiffany-primary)]/10 flex items-center justify-center mb-6">
          <Rss className="w-8 h-8 text-[var(--color-tiffany-primary)]" />
        </div>
        <h3 className="text-2xl font-bold mb-3 text-white">Coming Soon to Tiffany OS</h3>
        <p className="text-[var(--color-tiffany-text-secondary)] max-w-lg mb-8 leading-relaxed">
          We are currently rebuilding our News ingestion engine. Soon, Tiffany will be able to filter, format, and publish news directly from your favorite RSS feeds like IGN, The Verge, and Canaltech.
        </p>
        
        <div className="flex items-center gap-4 text-sm font-semibold text-[var(--color-tiffany-text-muted)] border border-[var(--color-tiffany-border-subtle)] bg-[var(--color-tiffany-bg-elevated)] px-6 py-3 rounded-full">
          <span>Sources</span>
          <ArrowRight className="w-4 h-4" />
          <span>Tiffany Filter Engine</span>
          <ArrowRight className="w-4 h-4" />
          <span>Discord</span>
        </div>
      </div>
    </div>
  );
}

export default function NewsSettings() {
  return (
    <Suspense fallback={<div className="h-24 bg-[var(--color-tiffany-surface)] rounded-2xl animate-pulse" />}>
      <NewsSettingsContent />
    </Suspense>
  );
}
