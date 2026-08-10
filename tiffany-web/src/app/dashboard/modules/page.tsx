"use client";

import { useEffect, useState, Suspense } from "react";
import { getGuildConfig, updateGuildConfig } from "@/lib/api";
import { Save, AlertTriangle, Blocks, Music, Bot, Gamepad2, ShoppingBag, Gift, TerminalSquare, Coins } from "lucide-react";
import { cn } from "@/lib/utils";
import { useSearchParams } from "next/navigation";
import { useToast } from "@/components/ToastProvider";

function ModulesSettingsContent() {
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
          Please select a server to manage Modules.
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

  return (
    <div className="space-y-8 animate-in fade-in duration-500 pb-24">
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <h2 className="text-3xl font-bold tracking-tight mb-2 flex items-center gap-2">
            <Blocks className="w-8 h-8 text-[var(--color-tiffany-primary)]" /> Modules
          </h2>
          <p className="text-[var(--color-tiffany-text-secondary)] text-lg">
            Turn features on or off. Disabled modules will hide their commands completely.
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

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        <ModuleCard 
          icon={<Music className="w-6 h-6 text-pink-400" />}
          title="Music"
          description="High quality Lavalink audio playback."
          active={config.features?.music}
          onToggle={() => toggleFeature("music")}
        />
        <ModuleCard 
          icon={<Bot className="w-6 h-6 text-blue-400" />}
          title="AI Chat"
          description="GPT-4 integration and conversations."
          active={config.features?.chat}
          onToggle={() => toggleFeature("chat")}
        />
        <ModuleCard 
          icon={<Bot className="w-6 h-6 text-indigo-400" />}
          title="AI Imagine"
          description="Neural image generation commands."
          active={config.features?.imagine}
          onToggle={() => toggleFeature("imagine")}
        />
        <ModuleCard 
          icon={<Coins className="w-6 h-6 text-yellow-400" />}
          title="Roleplay & Economy"
          description="Profiles, marriage, currency and inventory."
          active={config.features?.roleplay}
          onToggle={() => toggleFeature("roleplay")}
        />
        <ModuleCard 
          icon={<Gamepad2 className="w-6 h-6 text-green-400" />}
          title="Games"
          description="Minigames and interactive Discord games."
          active={config.features?.games}
          onToggle={() => toggleFeature("games")}
        />
        <ModuleCard 
          icon={<Gift className="w-6 h-6 text-purple-400" />}
          title="Giveaways"
          description="Host giveaways with requirements."
          active={config.features?.giveaways}
          onToggle={() => toggleFeature("giveaways")}
        />
        <ModuleCard 
          icon={<TerminalSquare className="w-6 h-6 text-teal-400" />}
          title="Embed Builder"
          description="Create beautiful rich messages."
          active={config.features?.embeds}
          onToggle={() => toggleFeature("embeds")}
        />
        <ModuleCard 
          icon={<ShoppingBag className="w-6 h-6 text-orange-400" />}
          title="Deals & Offers"
          description="Automated hardware and gaming deals."
          active={config.features?.offers}
          onToggle={() => toggleFeature("offers")}
        />
      </div>
    </div>
  );
}

function ModuleCard({ icon, title, description, active, onToggle }: { icon: React.ReactNode, title: string, description: string, active: boolean, onToggle: () => void }) {
  return (
    <div 
      onClick={onToggle}
      className={cn(
        "p-6 rounded-2xl border transition-all cursor-pointer flex flex-col group relative overflow-hidden",
        active 
          ? "border-[var(--color-tiffany-primary)]/50 bg-[var(--color-tiffany-primary)]/5 shadow-[var(--shadow-tiffany-glow)]" 
          : "border-[var(--color-tiffany-border)] bg-[var(--color-tiffany-surface)] hover:bg-[var(--color-tiffany-surface-hover)] hover:border-[var(--color-tiffany-border-subtle)]"
      )}
    >
      <div className="flex items-center justify-between mb-4">
        <div className="w-12 h-12 rounded-xl bg-[var(--color-tiffany-bg-elevated)] border border-[var(--color-tiffany-border)] flex items-center justify-center shrink-0">
          {icon}
        </div>
        <div className={cn(
          "w-12 h-6 rounded-full transition-colors relative flex-shrink-0 shadow-inner",
          active ? "bg-[var(--color-tiffany-primary)] shadow-[var(--shadow-tiffany-glow)]" : "bg-[var(--color-tiffany-border-subtle)] border border-[var(--color-tiffany-border)]"
        )}>
          <div className={cn(
            "absolute top-1 w-4 h-4 rounded-full bg-white transition-all shadow-sm",
            active ? "left-7" : "left-1"
          )} />
        </div>
      </div>
      <h3 className="font-bold text-lg text-white mb-2">{title}</h3>
      <p className="text-sm text-[var(--color-tiffany-text-secondary)]">{description}</p>
    </div>
  );
}

export default function ModulesSettings() {
  return (
    <Suspense fallback={<div className="h-24 bg-[var(--color-tiffany-surface)] rounded-2xl animate-pulse" />}>
      <ModulesSettingsContent />
    </Suspense>
  );
}
