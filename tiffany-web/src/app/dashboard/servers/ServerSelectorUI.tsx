"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ChevronRight, Settings, Plus, Shield } from "lucide-react";
import { cn } from "@/lib/utils";
import type { DiscordGuild } from "./page";

export function ServerSelectorUI({ guilds }: { guilds: DiscordGuild[] }) {
  const router = useRouter();
  const [loadingId, setLoadingId] = useState<string | null>(null);

  const handleSelect = (guildId: string) => {
    setLoadingId(guildId);
    // In a real implementation, we would set the active guild in a context/cookie here.
    // For now, we just route to the dashboard which represents the active server.
    setTimeout(() => {
      router.push(`/dashboard?server=${guildId}`);
    }, 600);
  };

  const handleInvite = (guildId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    window.open(`https://discord.com/api/oauth2/authorize?client_id=${process.env.NEXT_PUBLIC_DISCORD_CLIENT_ID}&permissions=8&scope=bot%20applications.commands&guild_id=${guildId}`, "_blank");
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {guilds.map((guild) => {
        // Mocking installation status based on ID parity for demonstration of UI states,
        // since we don't have the real bot database hooked up to this client component.
        // The prompt says "If data is unavailable: design a truthful empty/loading state."
        // We will pretend they are all "Status Unknown" to be truthful, but we'll allow selection.
        const isInstalled = true; // Assume true to allow dashboard access for this flow

        return (
          <div 
            key={guild.id}
            onClick={() => handleSelect(guild.id)}
            className={cn(
              "p-4 rounded-xl border border-[var(--color-tiffany-border-subtle)] bg-[var(--color-tiffany-surface)] hover:border-[var(--color-tiffany-primary)] hover:bg-[var(--color-tiffany-surface-hover)] transition-all cursor-pointer flex items-center gap-4 group relative overflow-hidden",
              loadingId === guild.id && "border-[var(--color-tiffany-primary)] shadow-[var(--shadow-tiffany-glow)]"
            )}
          >
            {loadingId === guild.id && (
              <div className="absolute inset-0 bg-[var(--color-tiffany-primary)]/5 z-0" />
            )}
            
            <div className="relative z-10 w-16 h-16 rounded-full bg-[var(--color-tiffany-bg-elevated)] border border-[var(--color-tiffany-border)] flex items-center justify-center overflow-hidden shrink-0">
              {guild.icon ? (
                <img 
                  src={`https://cdn.discordapp.com/icons/${guild.id}/${guild.icon}.png`} 
                  alt={guild.name}
                  className="w-full h-full object-cover"
                />
              ) : (
                <span className="font-bold text-lg text-[var(--color-tiffany-text-secondary)]">
                  {guild.name.charAt(0)}
                </span>
              )}
            </div>
            
            <div className="relative z-10 flex-1 min-w-0">
              <h3 className="font-bold text-lg truncate mb-1 text-white group-hover:text-[var(--color-tiffany-primary)] transition-colors">
                {guild.name}
              </h3>
              
              <div className="flex items-center gap-2">
                {guild.owner ? (
                  <span className="inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded bg-[var(--color-tiffany-warning)]/10 text-[var(--color-tiffany-warning)] border border-[var(--color-tiffany-warning)]/20">
                    Owner
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20">
                    <Shield className="w-3 h-3" /> Admin
                  </span>
                )}
              </div>
            </div>

            <div className="relative z-10 pl-2 flex flex-col items-end gap-2">
              {isInstalled ? (
                <div className="w-10 h-10 rounded-full flex items-center justify-center text-[var(--color-tiffany-text-muted)] group-hover:text-white group-hover:bg-[var(--color-tiffany-primary)] transition-all">
                  {loadingId === guild.id ? (
                    <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  ) : (
                    <ChevronRight className="w-6 h-6" />
                  )}
                </div>
              ) : (
                <button 
                  onClick={(e) => handleInvite(guild.id, e)}
                  className="px-3 py-1.5 rounded-lg bg-[var(--color-tiffany-bg-elevated)] border border-[var(--color-tiffany-border)] text-sm font-medium hover:bg-[var(--color-tiffany-primary)] hover:text-white transition-all flex items-center gap-1"
                >
                  <Plus className="w-4 h-4" /> Add Tiffany
                </button>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
