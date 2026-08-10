import { Users, MessagesSquare, Music, ShieldAlert, Activity, CheckCircle2 } from "lucide-react";
import { cn } from "@/lib/utils";

import { redirect } from "next/navigation";

export default async function DashboardOverview({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const params = await searchParams;
  if (!params.server) {
    redirect("/dashboard/servers");
  }

  return (
    <div className="space-y-8 animate-in fade-in duration-500 relative z-10">
      <div>
        <h2 className="text-3xl font-bold tracking-tight mb-2">Server Overview</h2>
        <p className="text-[var(--color-tiffany-text-secondary)] text-lg">
          Manage your server settings, modules, and track Tiffany's real-time activity.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-6">
        <StatCard 
          title="Total Members"
          value="4,291"
          trend="+12% this week"
          icon={<Users className="w-5 h-5 text-blue-400" />}
        />
        <StatCard 
          title="Messages Scanned"
          value="128.4k"
          trend="Secure"
          icon={<MessagesSquare className="w-5 h-5 text-[var(--color-tiffany-success)]" />}
        />
        <StatCard 
          title="Audio Hours"
          value="48.2"
          trend="High usage"
          icon={<Music className="w-5 h-5 text-[var(--color-tiffany-secondary)]" />}
        />
        <StatCard 
          title="Actions Taken"
          value="142"
          trend="Moderation active"
          icon={<ShieldAlert className="w-5 h-5 text-[var(--color-tiffany-warning)]" />}
        />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <div className="xl:col-span-2 rounded-[var(--radius-card)] border border-[var(--color-tiffany-border)] bg-[var(--color-tiffany-surface)] overflow-hidden shadow-lg">
          <div className="p-6 border-b border-[var(--color-tiffany-border-subtle)] bg-[var(--color-tiffany-bg-elevated)]/50 flex items-center justify-between">
            <h3 className="text-lg font-semibold flex items-center gap-2">
              <Activity className="w-5 h-5 text-[var(--color-tiffany-primary)]" /> Recent Audit Logs
            </h3>
            <span className="text-xs text-[var(--color-tiffany-text-muted)] font-medium bg-[var(--color-tiffany-surface-hover)] px-2 py-1 rounded">LIVE</span>
          </div>
          <div className="p-6 space-y-4">
            <LogItem action="User muted (Spam)" target="Spammer#9999" time="2m ago" />
            <LogItem action="Message deleted" target="BadWordFilter" time="15m ago" />
            <LogItem action="Song skipped" target="DJ Admin" time="1h ago" />
            <LogItem action="Settings changed" target="Moderation Config" time="3h ago" />
          </div>
        </div>

        <div className="rounded-[var(--radius-card)] border border-[var(--color-tiffany-border)] bg-[var(--color-tiffany-surface)] overflow-hidden shadow-lg">
          <div className="p-6 border-b border-[var(--color-tiffany-border-subtle)] bg-[var(--color-tiffany-bg-elevated)]/50">
            <h3 className="text-lg font-semibold flex items-center gap-2">
              <CheckCircle2 className="w-5 h-5 text-[var(--color-tiffany-success)]" /> Quick Actions
            </h3>
          </div>
          <div className="p-6 space-y-3">
            <QuickAction title="Enable Strict Filter" description="Max protection against spam." active={false} />
            <QuickAction title="Music 24/7 Mode" description="Lavalink stays connected." active={true} />
            <QuickAction title="Auto-Role" description="Assign roles to new members." active={true} />
          </div>
        </div>
      </div>
    </div>
  );
}

function StatCard({ title, value, trend, icon }: { title: string, value: string, trend: string, icon: React.ReactNode }) {
  return (
    <div className="rounded-[var(--radius-card)] border border-[var(--color-tiffany-border)] bg-[var(--color-tiffany-surface)] p-6 hover:border-[var(--color-tiffany-primary)]/50 transition-colors shadow-lg relative overflow-hidden group">
      <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
        {icon}
      </div>
      <div className="flex items-start justify-between mb-6">
        <h4 className="text-sm font-semibold text-[var(--color-tiffany-text-secondary)]">{title}</h4>
        <div className="p-2 rounded-lg bg-[var(--color-tiffany-surface-hover)] border border-[var(--color-tiffany-border)]">
          {icon}
        </div>
      </div>
      <div className="text-4xl font-extrabold tracking-tight mb-2 text-white">{value}</div>
      <div className="text-xs text-[var(--color-tiffany-text-muted)] font-semibold uppercase tracking-wider">{trend}</div>
    </div>
  );
}

function QuickAction({ title, description, active }: { title: string, description: string, active: boolean }) {
  return (
    <div className="flex items-center justify-between p-4 rounded-xl border border-[var(--color-tiffany-border)] bg-[var(--color-tiffany-bg-elevated)] hover:bg-[var(--color-tiffany-surface-hover)] hover:border-[var(--color-tiffany-primary)]/30 transition-all cursor-pointer group">
      <div>
        <div className="font-semibold text-sm mb-1 group-hover:text-white transition-colors">{title}</div>
        <div className="text-xs text-[var(--color-tiffany-text-muted)]">{description}</div>
      </div>
      <div className={cn(
        "w-12 h-6 rounded-full transition-colors relative shadow-inner",
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

function LogItem({ action, target, time }: { action: string, target: string, time: string }) {
  return (
    <div className="flex items-center justify-between py-3 border-b border-[var(--color-tiffany-border-subtle)] last:border-0 last:pb-0">
      <div className="flex flex-col">
        <span className="font-semibold text-sm text-white">{action}</span>
        <span className="text-[var(--color-tiffany-text-secondary)] text-xs mt-1">{target}</span>
      </div>
      <span className="text-[var(--color-tiffany-text-muted)] text-xs font-medium bg-[var(--color-tiffany-bg-elevated)] px-2 py-1 rounded-md border border-[var(--color-tiffany-border-subtle)]">{time}</span>
    </div>
  );
}
