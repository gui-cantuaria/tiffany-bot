"use client";

import { useEffect, useState, Suspense } from "react";
import { getGuildConfig, updateGuildConfig } from "@/lib/api";
import { Music, Save, AlertTriangle, Settings2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { useSearchParams } from "next/navigation";
import { useToast } from "@/components/ToastProvider";

function AudioSettingsContent() {
  const searchParams = useSearchParams();
  const guildId = searchParams.get("server");
  const [config, setConfig] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);

  const { toast } = useToast();

  useEffect(() => {
    if (!guildId) {
      setLoading(false);
      return;
    }
    getGuildConfig(guildId).then(res => {
      if (res.success && res.data) {
        setConfig(res.data);
      } else {
        toast({ title: "Failed to load config", description: res.error, type: "error" });
      }
      setLoading(false);
    });
  }, [guildId]);

  const handleSave = async () => {
    if (!guildId) return;
    setSaving(true);
    const res = await updateGuildConfig(guildId, config);
    setSaving(false);
    
    if (res.success) {
      setHasChanges(false);
      toast({ title: "Configuration saved", description: "Your changes have been applied successfully.", type: "success" });
      if (res.data) setConfig(res.data);
    } else {
      toast({ title: "Failed to save", description: res.error || "An unknown error occurred.", type: "error" });
    }
  };

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="h-24 bg-[var(--color-tiffany-surface)] rounded-2xl animate-pulse" />
        <div className="h-64 bg-[var(--color-tiffany-surface)] rounded-2xl animate-pulse" />
      </div>
    );
  }

  if (!guildId) {
    return (
      <div className="p-12 border border-[var(--color-tiffany-border)] rounded-2xl bg-[var(--color-tiffany-surface)] text-center flex flex-col items-center">
        <h3 className="text-xl font-bold mb-2">No Server Selected</h3>
        <p className="text-[var(--color-tiffany-text-secondary)] max-w-md">
          Please select a server to configure Audio settings.
        </p>
      </div>
    );
  }

  if (!config) {
    return (
      <div className="p-12 border border-[var(--color-tiffany-border)] rounded-2xl bg-[var(--color-tiffany-surface)] text-center flex flex-col items-center">
        <div className="w-16 h-16 rounded-full bg-[var(--color-tiffany-danger)]/10 flex items-center justify-center mb-4">
          <AlertTriangle className="w-8 h-8 text-[var(--color-tiffany-danger)]" />
        </div>
        <h3 className="text-xl font-bold mb-2">Backend Connection Failed</h3>
      </div>
    );
  }

  const isMusicEnabled = config.features?.music ?? true;

  return (
    <div className="space-y-8 animate-in fade-in duration-500 pb-24">
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <h2 className="text-3xl font-bold tracking-tight mb-2">Audio & Player</h2>
          <p className="text-[var(--color-tiffany-text-secondary)] text-lg">
            Configure Lavalink playback, DJ roles, and music permissions.
          </p>
        </div>
        
        <button 
          onClick={handleSave}
          disabled={!hasChanges || saving}
          className={cn(
            "px-6 py-2.5 rounded-xl font-semibold transition-all flex items-center justify-center gap-2",
            hasChanges && !saving 
              ? "bg-[var(--color-tiffany-primary)] text-white hover:bg-[var(--color-tiffany-primary-hover)] shadow-[var(--shadow-tiffany-glow)]"
              : "bg-[var(--color-tiffany-surface-hover)] text-[var(--color-tiffany-text-muted)] cursor-not-allowed border border-[var(--color-tiffany-border)]"
          )}
        >
          {saving ? <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : <Save className="w-4 h-4" />}
          {saving ? "Saving..." : "Save Changes"}
        </button>
      </div>

      {!isMusicEnabled && (
        <div className="p-4 rounded-xl border border-[var(--color-tiffany-warning)] bg-[var(--color-tiffany-warning)]/10 text-white flex gap-3 items-start">
          <AlertTriangle className="w-5 h-5 text-[var(--color-tiffany-warning)] shrink-0 mt-0.5" />
          <div>
            <h4 className="font-bold text-[var(--color-tiffany-warning)] mb-1">Music Module Disabled</h4>
            <p className="text-sm text-[var(--color-tiffany-text-secondary)]">
              The Lavalink audio engine is currently disabled in the General settings. These configurations will not take effect until the module is enabled.
            </p>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 gap-8 max-w-2xl">
        <SettingSection 
          title="Playback Controls" 
          description="Who can control the music"
          icon={<Settings2 className="w-5 h-5 text-[var(--color-tiffany-primary)]" />}
        >
          <div className="p-4">
            <label className="block text-sm font-semibold mb-2">DJ Role ID</label>
            <input 
              type="text" 
              placeholder="e.g. 109823471928374"
              value={config.dj_role || ""}
              onChange={(e) => {
                const val = e.target.value.replace(/\D/g, "");
                setConfig((prev: any) => ({ ...prev, dj_role: val ? parseInt(val) : null }));
                setHasChanges(true);
              }}
              className="w-full bg-[var(--color-tiffany-bg-elevated)] border border-[var(--color-tiffany-border)] rounded-xl px-4 py-3 text-white focus:outline-none focus:border-[var(--color-tiffany-primary)] focus:ring-1 focus:ring-[var(--color-tiffany-primary)] transition-all"
            />
            <p className="text-xs text-[var(--color-tiffany-text-secondary)] mt-2">
              Users with this role can skip songs, clear the queue, and use advanced playback commands without needing a vote.
            </p>
          </div>
        </SettingSection>
      </div>
    </div>
  );
}

function SettingSection({ title, description, icon, children }: { title: string, description: string, icon: React.ReactNode, children: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-[var(--color-tiffany-border)] bg-[var(--color-tiffany-surface)] overflow-hidden shadow-lg flex flex-col h-full">
      <div className="p-6 border-b border-[var(--color-tiffany-border-subtle)] bg-[var(--color-tiffany-bg-elevated)]/50">
        <div className="flex items-center gap-3 mb-1">
          {icon}
          <h3 className="font-bold text-lg">{title}</h3>
        </div>
        <p className="text-sm text-[var(--color-tiffany-text-secondary)]">{description}</p>
      </div>
      <div className="p-2 flex-1 flex flex-col justify-center">
        {children}
      </div>
    </div>
  );
}

export default function AudioSettings() {
  return (
    <Suspense fallback={<div className="h-24 bg-[var(--color-tiffany-surface)] rounded-2xl animate-pulse" />}>
      <AudioSettingsContent />
    </Suspense>
  );
}
