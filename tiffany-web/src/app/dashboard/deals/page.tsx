"use client";

import { useEffect, useState, Suspense } from "react";
import { getGuildConfig, updateGuildConfig } from "@/lib/api";
import { Save, AlertTriangle, ShoppingBag, Tags, Link as LinkIcon, Hash } from "lucide-react";
import { cn } from "@/lib/utils";
import { useSearchParams } from "next/navigation";
import { useToast } from "@/components/ToastProvider";

function DealsSettingsContent() {
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
        let data = res.data;
        if (!data.allowed_categories) {
          data.allowed_categories = ["hardware", "jogos", "periféricos", "acessórios", "monitores", "outros"];
        }
        if (!data.affiliate_tags) {
          data.affiliate_tags = {};
        }
        setConfig(data);
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

  const toggleCategory = (cat: string) => {
    setConfig((prev: any) => {
      const cats = prev.allowed_categories || [];
      const newCats = cats.includes(cat) ? cats.filter((c: string) => c !== cat) : [...cats, cat];
      return { ...prev, allowed_categories: newCats };
    });
    setHasChanges(true);
  };

  const updateAffiliate = (provider: string, tag: string) => {
    setConfig((prev: any) => ({
      ...prev,
      affiliate_tags: {
        ...(prev.affiliate_tags || {}),
        [provider]: tag
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
          Please select a server to manage Deals.
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

  const isOffersEnabled = config.features?.offers ?? true;
  const categories = ["hardware", "jogos", "periféricos", "acessórios", "monitores", "outros"];

  return (
    <div className="space-y-8 animate-in fade-in duration-500 pb-24">
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <h2 className="text-3xl font-bold tracking-tight mb-2 flex items-center gap-2">
            <ShoppingBag className="w-8 h-8 text-orange-400" /> Deals & Offers
          </h2>
          <p className="text-[var(--color-tiffany-text-secondary)] text-lg">
            Configure automated deals drops and affiliate links.
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

      {!isOffersEnabled && (
        <div className="p-4 rounded-xl border border-[var(--color-tiffany-warning)] bg-[var(--color-tiffany-warning)]/10 text-white flex gap-3 items-start">
          <AlertTriangle className="w-5 h-5 text-[var(--color-tiffany-warning)] shrink-0 mt-0.5" />
          <div>
            <h4 className="font-bold text-[var(--color-tiffany-warning)] mb-1">Deals Module Disabled</h4>
            <p className="text-sm text-[var(--color-tiffany-text-secondary)]">
              The Deals module is currently disabled. Tiffany will not post any offers until you enable it in the Modules tab.
            </p>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <SettingSection 
          title="Destination Channel" 
          description="Where Tiffany posts deals"
          icon={<Hash className="w-5 h-5 text-indigo-400" />}
        >
          <div className="p-4">
            <label className="block text-sm font-semibold mb-2">Offers Channel ID</label>
            <input 
              type="text" 
              placeholder="e.g. 109823471928374"
              value={config.offers_channel || ""}
              onChange={(e) => {
                const val = e.target.value.replace(/\D/g, "");
                setConfig((prev: any) => ({ ...prev, offers_channel: val ? parseInt(val) : null }));
                setHasChanges(true);
              }}
              className="w-full bg-[var(--color-tiffany-bg-elevated)] border border-[var(--color-tiffany-border)] rounded-xl px-4 py-3 text-white focus:outline-none focus:border-[var(--color-tiffany-primary)] focus:ring-1 focus:ring-[var(--color-tiffany-primary)] transition-all"
            />
          </div>
        </SettingSection>

        <SettingSection 
          title="Filter Categories" 
          description="Which types of deals to allow"
          icon={<Tags className="w-5 h-5 text-teal-400" />}
        >
          <div className="p-4 flex flex-wrap gap-2">
            {categories.map(cat => {
              const active = (config.allowed_categories || []).includes(cat);
              return (
                <button
                  key={cat}
                  onClick={() => toggleCategory(cat)}
                  className={cn(
                    "px-3 py-1.5 rounded-lg text-sm font-medium transition-all border",
                    active 
                      ? "bg-teal-500/20 text-teal-300 border-teal-500/50" 
                      : "bg-[var(--color-tiffany-surface-hover)] text-[var(--color-tiffany-text-muted)] border-transparent"
                  )}
                >
                  {cat}
                </button>
              );
            })}
          </div>
        </SettingSection>

        <SettingSection 
          title="Affiliate Integrations" 
          description="Monetize deals with your own tags"
          icon={<LinkIcon className="w-5 h-5 text-green-400" />}
        >
          <div className="p-4 space-y-4">
            <AffiliateInput 
              provider="Amazon" 
              value={(config.affiliate_tags || {}).amazon || ""} 
              onChange={(val) => updateAffiliate("amazon", val)}
              status="ACTIVE"
            />
            <AffiliateInput 
              provider="AliExpress" 
              value={(config.affiliate_tags || {}).aliexpress || ""} 
              onChange={(val) => updateAffiliate("aliexpress", val)}
              status="ACTIVE"
            />
            <AffiliateInput 
              provider="Shopee" 
              value={(config.affiliate_tags || {}).shopee || ""} 
              onChange={(val) => updateAffiliate("shopee", val)}
              status="CONFIGURED"
            />
            <AffiliateInput 
              provider="Mercado Livre" 
              value={(config.affiliate_tags || {}).mercadolivre || ""} 
              onChange={(val) => updateAffiliate("mercadolivre", val)}
              status="NOT_YET_AVAILABLE"
              disabled={true}
            />
          </div>
        </SettingSection>
      </div>
    </div>
  );
}

function AffiliateInput({ provider, value, onChange, status, disabled = false }: { provider: string, value: string, onChange: (val: string) => void, status: string, disabled?: boolean }) {
  return (
    <div>
      <div className="flex justify-between items-center mb-1">
        <label className="text-sm font-semibold text-white">{provider} Tag</label>
        {status === "ACTIVE" && <span className="text-[10px] font-bold bg-green-500/20 text-green-400 px-2 py-0.5 rounded-md">ACTIVE</span>}
        {status === "CONFIGURED" && <span className="text-[10px] font-bold bg-blue-500/20 text-blue-400 px-2 py-0.5 rounded-md">READY</span>}
        {status === "NOT_YET_AVAILABLE" && <span className="text-[10px] font-bold bg-[var(--color-tiffany-surface-hover)] text-[var(--color-tiffany-text-muted)] px-2 py-0.5 rounded-md">COMING SOON</span>}
      </div>
      <input 
        type="text" 
        disabled={disabled}
        placeholder={disabled ? "Integration pending" : "e.g. tag-20"}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={cn(
          "w-full bg-[var(--color-tiffany-bg-elevated)] border border-[var(--color-tiffany-border)] rounded-xl px-4 py-2 text-white transition-all",
          disabled ? "opacity-50 cursor-not-allowed" : "focus:outline-none focus:border-[var(--color-tiffany-primary)] focus:ring-1 focus:ring-[var(--color-tiffany-primary)]"
        )}
      />
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

export default function DealsSettings() {
  return (
    <Suspense fallback={<div className="h-24 bg-[var(--color-tiffany-surface)] rounded-2xl animate-pulse" />}>
      <DealsSettingsContent />
    </Suspense>
  );
}
