"use client";

import { useEffect, useState, Suspense } from "react";
import { getGuildConfig, updateGuildConfig } from "@/lib/api";
import { Shield, MessageSquare, Save, Settings, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";
import { useSearchParams } from "next/navigation";
import { useToast } from "@/components/ToastProvider";

function GeneralSettingsContent() {
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

  const toggleFeature = (key: string) => {
    setConfig((prev: any) => ({
      ...prev,
      features: {
        ...prev.features,
        [key]: !prev.features[key]
      }
    }));
    setHasChanges(true);
  };

  const toggleSetting = (key: string) => {
    setConfig((prev: any) => ({
      ...prev,
      [key]: !prev[key]
    }));
    setHasChanges(true);
  };

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="h-24 bg-[var(--color-tiffany-surface)] rounded-2xl animate-pulse" />
        <div className="h-64 bg-[var(--color-tiffany-surface)] rounded-2xl animate-pulse" />
        <div className="h-64 bg-[var(--color-tiffany-surface)] rounded-2xl animate-pulse" />
      </div>
    );
  }

  if (!guildId) {
    return (
      <div className="p-12 border border-[var(--color-tiffany-border)] rounded-2xl bg-[var(--color-tiffany-surface)] text-center flex flex-col items-center">
        <h3 className="text-xl font-bold mb-2">No Server Selected</h3>
        <p className="text-[var(--color-tiffany-text-secondary)] max-w-md">
          Please select a server from the server menu to configure Tiffany.
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
        <p className="text-[var(--color-tiffany-text-secondary)] max-w-md">
          The Tiffany Bot infrastructure API is not running or unreachable on this environment.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-8 animate-in fade-in duration-500 pb-24">
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <h2 className="text-3xl font-bold tracking-tight mb-2">General Settings</h2>
          <p className="text-[var(--color-tiffany-text-secondary)] text-lg">
            Configure global behavior and core modules for your server.
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

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <SettingSection 
          title="Security & Moderation" 
          description="Global protection settings"
          icon={<Shield className="w-5 h-5 text-[var(--color-tiffany-warning)]" />}
        >
          <ToggleItem 
            title="Strict Filter" 
            description="Aggressively block profanity, spam, and unverified links using heuristic analysis." 
            active={config.strict_filter} 
            onChange={() => toggleSetting("strict_filter")}
          />
          <ToggleItem 
            title="Anti-Spam Thresholds" 
            description="Automatically mute users sending too many messages too quickly." 
            active={config.anti_spam} 
            onChange={() => toggleSetting("anti_spam")}
          />
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
      <div className="p-2 flex-1">
        {children}
      </div>
    </div>
  );
}

function ToggleItem({ title, description, active, onChange }: { title: string, description: string, active: boolean, onChange: () => void }) {
  return (
    <div 
      className="flex items-start justify-between gap-6 p-4 rounded-xl hover:bg-[var(--color-tiffany-surface-hover)] transition-colors cursor-pointer group"
      onClick={onChange}
    >
      <div className="flex-1">
        <div className="font-semibold text-sm mb-1 text-white">{title}</div>
        <div className="text-sm text-[var(--color-tiffany-text-secondary)] leading-relaxed pr-4">{description}</div>
      </div>
      <div className={cn(
        "w-12 h-6 rounded-full transition-colors relative flex-shrink-0 mt-1 shadow-inner",
        active ? "bg-[var(--color-tiffany-primary)] shadow-[var(--shadow-tiffany-glow)]" : "bg-[var(--color-tiffany-border-subtle)] border border-[var(--color-tiffany-border)]"
      )}>
        <div className={cn(
          "absolute top-1 w-4 h-4 rounded-full bg-white transition-all shadow-sm",
          active ? "left-7" : "left-1"
        )} />
      </div>
    </div>
  );
}

export default function GeneralSettings() {
  return (
    <Suspense fallback={<div className="h-24 bg-[var(--color-tiffany-surface)] rounded-2xl animate-pulse" />}>
      <GeneralSettingsContent />
    </Suspense>
  );
}
