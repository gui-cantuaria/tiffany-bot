"use client";

import { Suspense } from "react";
import { CreditCard, Zap, Check, ArrowRight, ShieldCheck } from "lucide-react";

function PremiumSettingsContent() {
  return (
    <div className="space-y-8 animate-in fade-in duration-500 pb-24">
      <div>
        <h2 className="text-3xl font-bold tracking-tight mb-2 flex items-center gap-2">
          <CreditCard className="w-8 h-8 text-[var(--color-tiffany-primary)]" /> Billing & Premium
        </h2>
        <p className="text-[var(--color-tiffany-text-secondary)] text-lg">
          Manage your subscription and server boosts.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        
        {/* Current Plan Overview */}
        <div className="lg:col-span-2 rounded-2xl border border-[var(--color-tiffany-primary)]/50 bg-[var(--color-tiffany-primary)]/5 p-8 relative overflow-hidden shadow-[var(--shadow-tiffany-glow)]">
          <div className="absolute top-0 right-0 p-8 opacity-10">
            <Zap className="w-32 h-32 text-[var(--color-tiffany-primary)]" />
          </div>
          
          <div className="relative z-10 flex flex-col h-full justify-between">
            <div>
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[var(--color-tiffany-primary)] text-white text-xs font-bold uppercase tracking-wider mb-4 shadow-lg shadow-[var(--color-tiffany-primary)]/20">
                <ShieldCheck className="w-4 h-4" /> Active Subscription
              </div>
              <h3 className="text-4xl font-extrabold text-white mb-2">Tiffany OS Pro</h3>
              <p className="text-[var(--color-tiffany-text-secondary)] text-lg max-w-md">
                Your server is currently boosted with the maximum AI and Audio quality limits.
              </p>
            </div>
            
            <div className="mt-8 pt-8 border-t border-[var(--color-tiffany-primary)]/20">
              <p className="text-sm text-[var(--color-tiffany-text-secondary)] mb-4">
                Next billing date: <strong>October 14, 2026</strong>
              </p>
              <button className="px-6 py-3 rounded-xl bg-[var(--color-tiffany-bg-elevated)] border border-[var(--color-tiffany-primary)] text-white font-bold hover:bg-[var(--color-tiffany-primary)] transition-all">
                Manage Subscription
              </button>
            </div>
          </div>
        </div>
        
        {/* Features Unlocked */}
        <div className="rounded-2xl border border-[var(--color-tiffany-border)] bg-[var(--color-tiffany-surface)] p-8">
          <h4 className="font-bold text-xl text-white mb-6">Current Benefits</h4>
          <ul className="space-y-4">
            <li className="flex items-start gap-3">
              <div className="w-6 h-6 rounded-full bg-green-500/20 flex items-center justify-center shrink-0 mt-0.5">
                <Check className="w-4 h-4 text-green-400" />
              </div>
              <span className="text-[var(--color-tiffany-text-secondary)] text-sm">Priority Audio Nodes</span>
            </li>
            <li className="flex items-start gap-3">
              <div className="w-6 h-6 rounded-full bg-green-500/20 flex items-center justify-center shrink-0 mt-0.5">
                <Check className="w-4 h-4 text-green-400" />
              </div>
              <span className="text-[var(--color-tiffany-text-secondary)] text-sm">GPT-4 Turbo Access</span>
            </li>
            <li className="flex items-start gap-3">
              <div className="w-6 h-6 rounded-full bg-green-500/20 flex items-center justify-center shrink-0 mt-0.5">
                <Check className="w-4 h-4 text-green-400" />
              </div>
              <span className="text-[var(--color-tiffany-text-secondary)] text-sm">Custom Embed Branding</span>
            </li>
            <li className="flex items-start gap-3">
              <div className="w-6 h-6 rounded-full bg-green-500/20 flex items-center justify-center shrink-0 mt-0.5">
                <Check className="w-4 h-4 text-green-400" />
              </div>
              <span className="text-[var(--color-tiffany-text-secondary)] text-sm">Automated Deal Feeds</span>
            </li>
            <li className="flex items-start gap-3">
              <div className="w-6 h-6 rounded-full bg-green-500/20 flex items-center justify-center shrink-0 mt-0.5">
                <Check className="w-4 h-4 text-green-400" />
              </div>
              <span className="text-[var(--color-tiffany-text-secondary)] text-sm">24/7 Premium Support</span>
            </li>
          </ul>
          
          <div className="mt-8 pt-6 border-t border-[var(--color-tiffany-border-subtle)]">
            <a href="/#pricing" className="group flex items-center justify-between text-sm font-semibold text-[var(--color-tiffany-primary)]">
              View all plans <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
            </a>
          </div>
        </div>

      </div>
    </div>
  );
}

export default function PremiumSettings() {
  return (
    <Suspense fallback={<div className="h-24 bg-[var(--color-tiffany-surface)] rounded-2xl animate-pulse" />}>
      <PremiumSettingsContent />
    </Suspense>
  );
}
