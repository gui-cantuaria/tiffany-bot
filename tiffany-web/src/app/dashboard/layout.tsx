"use client";

import { ReactNode } from "react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { Settings, Home, Shield, Music, Package, CreditCard, Activity, Box, Bell, ChevronLeft, Bot } from "lucide-react";
import { cn } from "@/lib/utils";
import { Suspense } from "react";

function DashboardLayoutContent({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const serverId = searchParams.get("server") || "";
  const qs = serverId ? `?server=${serverId}` : "";
  const hasServer = !!serverId;

  return (
    <div className="flex h-screen bg-[var(--color-tiffany-bg)] overflow-hidden text-[var(--color-tiffany-text)] selection:bg-[var(--color-tiffany-primary)]/30">
      
      {/* Global Sidebar (Server Selector) - Desktop */}
      <div className="hidden md:flex w-[72px] flex-shrink-0 bg-[var(--color-tiffany-bg-elevated)] border-r border-[var(--color-tiffany-border-subtle)] flex-col items-center py-4 gap-4 z-20">
        <Link 
          href="/dashboard/servers"
          className="w-12 h-12 rounded-[24px] hover:rounded-[16px] bg-[var(--color-tiffany-primary)] text-white flex items-center justify-center transition-all duration-200 shadow-[var(--shadow-tiffany-glow)]"
        >
          <ChevronLeft className="w-6 h-6" />
        </Link>
        
        <div className="w-8 h-[2px] bg-[var(--color-tiffany-border)] rounded-full" />
        
        {/* Mock Server Selection Context */}
        <div className="w-12 h-12 rounded-[16px] bg-[var(--color-tiffany-surface-hover)] border-2 border-[var(--color-tiffany-primary)] flex items-center justify-center relative shadow-[var(--shadow-tiffany-glow)]">
          <span className="text-white font-bold text-sm">SRV</span>
          <div className="absolute left-[-18px] w-2 h-10 bg-white rounded-r-full" />
        </div>
      </div>

      {/* Module Sidebar (Contextual) */}
      {hasServer && (
        <div className="w-72 flex-shrink-0 bg-[var(--color-tiffany-surface)] border-r border-[var(--color-tiffany-border-subtle)] flex flex-col z-10 hidden md:flex">
          <div className="h-16 flex items-center px-6 border-b border-[var(--color-tiffany-border-subtle)] bg-[var(--color-tiffany-bg-elevated)]/50">
            <h2 className="font-bold text-lg truncate flex items-center gap-2">
              <Bot className="w-5 h-5 text-[var(--color-tiffany-primary)]" />
              Tiffany Settings
            </h2>
          </div>
        
        <div className="flex-1 overflow-y-auto p-4 space-y-1 custom-scrollbar">
          <SidebarItem icon={<Activity />} label="Overview" href={`/dashboard${qs}`} active={pathname === "/dashboard"} />
          
          <div className="pt-6 pb-2 px-3 text-[11px] font-bold text-[var(--color-tiffany-text-muted)] uppercase tracking-widest">
            Configuration
          </div>
          <SidebarItem icon={<Settings />} label="General" href={`/dashboard/general${qs}`} active={pathname === "/dashboard/general"} />
          <SidebarItem icon={<Shield />} label="Moderation" href={`/dashboard/moderation${qs}`} active={pathname === "/dashboard/moderation"} />
          <SidebarItem icon={<Music />} label="Audio & Player" href={`/dashboard/audio${qs}`} active={pathname === "/dashboard/audio"} />
          
          <div className="pt-6 pb-2 px-3 text-[11px] font-bold text-[var(--color-tiffany-text-muted)] uppercase tracking-widest">
            Extensions
          </div>
          <SidebarItem icon={<Package />} label="Modules" href={`/dashboard/modules${qs}`} active={pathname === "/dashboard/modules"} />
          <SidebarItem icon={<Box />} label="Custom Commands" href={`/dashboard/commands${qs}`} active={pathname === "/dashboard/commands"} />
          
          <div className="pt-6 pb-2 px-3 text-[11px] font-bold text-[var(--color-tiffany-text-muted)] uppercase tracking-widest">
            Content Feeds
          </div>
          <SidebarItem icon={<Bot />} label="News" href={`/dashboard/news${qs}`} active={pathname === "/dashboard/news"} />
          <SidebarItem icon={<Activity />} label="Deals & Offers" href={`/dashboard/deals${qs}`} active={pathname === "/dashboard/deals"} />
          
          <div className="pt-6 pb-2 px-3 text-[11px] font-bold text-[var(--color-tiffany-text-muted)] uppercase tracking-widest">
            Billing
          </div>
          <SidebarItem icon={<CreditCard />} label="Premium" href={`/dashboard/premium${qs}`} active={pathname === "/dashboard/premium"} />
        </div>
        
          {/* User Profile Footer */}
          <div className="p-4 border-t border-[var(--color-tiffany-border-subtle)] bg-[var(--color-tiffany-bg-elevated)] flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-[var(--color-tiffany-surface-hover)] border border-[var(--color-tiffany-border)] flex items-center justify-center shrink-0 shadow-sm">
              <span className="font-bold text-sm">US</span>
            </div>
            <div className="flex flex-col min-w-0">
              <span className="font-semibold text-sm truncate text-white">Admin User</span>
              <span className="text-xs text-[var(--color-tiffany-text-muted)] truncate">#1234</span>
            </div>
          </div>
        </div>
      )}

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden relative">
        {/* Topbar */}
        {hasServer && (
          <header className="h-16 border-b border-[var(--color-tiffany-border-subtle)] flex items-center justify-between px-8 bg-[var(--color-tiffany-bg)]/80 backdrop-blur-md z-10 shrink-0 sticky top-0">
            <h1 className="text-lg font-bold">Server Configuration</h1>
            <div className="flex items-center gap-4">
              <button className="text-[var(--color-tiffany-text-secondary)] hover:text-white transition-colors w-10 h-10 rounded-full hover:bg-[var(--color-tiffany-surface)] flex items-center justify-center">
                <Bell className="w-5 h-5" />
              </button>
            </div>
          </header>
        )}
        
        {/* Page Content */}
        <main className="flex-1 overflow-y-auto p-6 md:p-10 relative">
          <div className="max-w-6xl mx-auto relative z-10 pb-20 md:pb-0">
            {children}
          </div>
        </main>
        
        {/* Mobile Navigation (Bottom) */}
        {hasServer && (
          <div className="md:hidden fixed bottom-0 left-0 right-0 bg-[var(--color-tiffany-bg-elevated)] border-t border-[var(--color-tiffany-border-subtle)] flex items-center justify-around p-2 z-50">
            <Link href={`/dashboard${qs}`} className={cn("p-2 rounded-lg flex flex-col items-center gap-1", pathname === "/dashboard" ? "text-[var(--color-tiffany-primary)]" : "text-[var(--color-tiffany-text-muted)]")}>
              <Activity className="w-5 h-5" />
              <span className="text-[10px]">Overview</span>
            </Link>
            <Link href={`/dashboard/general${qs}`} className={cn("p-2 rounded-lg flex flex-col items-center gap-1", pathname === "/dashboard/general" ? "text-[var(--color-tiffany-primary)]" : "text-[var(--color-tiffany-text-muted)]")}>
              <Settings className="w-5 h-5" />
              <span className="text-[10px]">General</span>
            </Link>
            <Link href={`/dashboard/modules${qs}`} className={cn("p-2 rounded-lg flex flex-col items-center gap-1", pathname === "/dashboard/modules" ? "text-[var(--color-tiffany-primary)]" : "text-[var(--color-tiffany-text-muted)]")}>
              <Package className="w-5 h-5" />
              <span className="text-[10px]">Modules</span>
            </Link>
            <Link href={`/dashboard/deals${qs}`} className={cn("p-2 rounded-lg flex flex-col items-center gap-1", pathname === "/dashboard/deals" ? "text-[var(--color-tiffany-primary)]" : "text-[var(--color-tiffany-text-muted)]")}>
              <Activity className="w-5 h-5" />
              <span className="text-[10px]">Deals</span>
            </Link>
            <Link href={`/dashboard/servers`} className="p-2 rounded-lg flex flex-col items-center gap-1 text-[var(--color-tiffany-text-muted)]">
              <ChevronLeft className="w-5 h-5" />
              <span className="text-[10px]">Servers</span>
            </Link>
          </div>
        )}
      </div>
    </div>
  );
}

export default function DashboardLayout({ children }: { children: ReactNode }) {
  return (
    <Suspense fallback={<div className="h-screen bg-[var(--color-tiffany-bg)]" />}>
      <DashboardLayoutContent>{children}</DashboardLayoutContent>
    </Suspense>
  );
}

function SidebarItem({ icon, label, href, active = false }: { icon: React.ReactNode, label: string, href: string, active?: boolean }) {
  return (
    <Link 
      href={href}
      className={cn(
        "flex items-center gap-3 px-4 py-2.5 rounded-lg transition-all text-sm font-medium group relative overflow-hidden",
        active 
          ? "bg-[var(--color-tiffany-surface-hover)] text-white border border-[var(--color-tiffany-border)]" 
          : "text-[var(--color-tiffany-text-secondary)] hover:bg-[var(--color-tiffany-surface)] hover:text-white border border-transparent"
      )}
    >
      {active && (
        <div className="absolute left-0 top-0 bottom-0 w-1 bg-[var(--color-tiffany-primary)] shadow-[var(--shadow-tiffany-glow)]" />
      )}
      <span className={cn(
        "w-5 h-5 flex items-center justify-center transition-colors",
        active ? "text-[var(--color-tiffany-primary)]" : "text-[var(--color-tiffany-text-muted)] group-hover:text-[var(--color-tiffany-text-secondary)]"
      )}>
        {icon}
      </span>
      {label}
    </Link>
  );
}
