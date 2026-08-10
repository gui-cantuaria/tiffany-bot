"use client";

import { Suspense } from "react";
import { Box, ExternalLink, ShieldCheck } from "lucide-react";
import { useSearchParams } from "next/navigation";

function CommandsSettingsContent() {
  const searchParams = useSearchParams();
  const guildId = searchParams.get("server");

  return (
    <div className="space-y-8 animate-in fade-in duration-500 pb-24">
      <div>
        <h2 className="text-3xl font-bold tracking-tight mb-2 flex items-center gap-2">
          <Box className="w-8 h-8 text-blue-400" /> Custom Commands
        </h2>
        <p className="text-[var(--color-tiffany-text-secondary)] text-lg">
          Manage how commands are executed in your server.
        </p>
      </div>

      <div className="p-12 border border-[var(--color-tiffany-border)] rounded-2xl bg-[var(--color-tiffany-surface)] flex flex-col md:flex-row items-center gap-8 shadow-lg">
        <div className="w-24 h-24 rounded-full bg-blue-500/10 flex items-center justify-center shrink-0">
          <ShieldCheck className="w-12 h-12 text-blue-400" />
        </div>
        <div>
          <h3 className="text-2xl font-bold mb-3 text-white">Native Discord Integration</h3>
          <p className="text-[var(--color-tiffany-text-secondary)] text-lg mb-6 leading-relaxed">
            Tiffany OS uses Discord's native slash command permission system. Instead of configuring channel and role limits in our dashboard, you can manage them directly inside your Discord server.
          </p>
          <div className="bg-[var(--color-tiffany-bg-elevated)] p-4 rounded-xl border border-[var(--color-tiffany-border-subtle)]">
            <p className="text-sm font-semibold text-white mb-2">How to configure permissions:</p>
            <ol className="list-decimal list-inside text-sm text-[var(--color-tiffany-text-secondary)] space-y-2">
              <li>Open your <strong>Server Settings</strong> in Discord</li>
              <li>Go to <strong>Integrations</strong></li>
              <li>Select <strong>Tiffany Bot</strong></li>
              <li>Modify permissions for each command individually</li>
            </ol>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mt-8">
        <div className="p-6 border border-[var(--color-tiffany-border-subtle)] rounded-xl bg-[var(--color-tiffany-bg-elevated)]">
          <h4 className="font-bold text-white mb-2">Want to disable a whole category?</h4>
          <p className="text-sm text-[var(--color-tiffany-text-secondary)] mb-4">
            If you want to completely disable a module (e.g. Music, Economy, Games) so its commands don't even show up, you can do that in the Modules tab.
          </p>
          <a 
            href={`/dashboard/modules${guildId ? `?server=${guildId}` : ""}`}
            className="inline-flex items-center gap-2 text-sm font-semibold text-[var(--color-tiffany-primary)] hover:text-white transition-colors"
          >
            Go to Modules <ExternalLink className="w-4 h-4" />
          </a>
        </div>
        
        <div className="p-6 border border-[var(--color-tiffany-border-subtle)] rounded-xl bg-[var(--color-tiffany-bg-elevated)]">
          <h4 className="font-bold text-white mb-2">Looking for all commands?</h4>
          <p className="text-sm text-[var(--color-tiffany-text-secondary)] mb-4">
            You can view the full list of Tiffany's commands and see how they look inside Discord in our public command explorer.
          </p>
          <a 
            href="/commands"
            target="_blank"
            className="inline-flex items-center gap-2 text-sm font-semibold text-white hover:text-[var(--color-tiffany-primary)] transition-colors"
          >
            View Command List <ExternalLink className="w-4 h-4" />
          </a>
        </div>
      </div>
    </div>
  );
}

export default function CommandsSettings() {
  return (
    <Suspense fallback={<div className="h-24 bg-[var(--color-tiffany-surface)] rounded-2xl animate-pulse" />}>
      <CommandsSettingsContent />
    </Suspense>
  );
}
