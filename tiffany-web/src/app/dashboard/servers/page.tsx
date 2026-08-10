import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { ServerSelectorUI } from "./ServerSelectorUI";

// Define standard Discord Guild object
export interface DiscordGuild {
  id: string;
  name: string;
  icon: string | null;
  owner: boolean;
  permissions: string;
  features: string[];
}

export default async function ServersPage() {
  const cookieStore = await cookies();
  const token = cookieStore.get("discord_token")?.value;

  if (!token) {
    redirect("/api/auth/login");
  }

  // Fetch guilds from Discord
  let guilds: DiscordGuild[] = [];
  let errorState = null;

  try {
    const res = await fetch("https://discord.com/api/users/@me/guilds", {
      headers: {
        Authorization: `Bearer ${token}`,
      },
      next: { revalidate: 60 },
    });

    if (res.ok) {
      guilds = await res.json();
    } else {
      errorState = "Discord API rejected the token. Your session may have expired.";
    }
  } catch (err) {
    errorState = "Failed to connect to Discord to fetch your servers.";
  }

  // Filter guilds where user has MANAGE_GUILD (0x20) or ADMINISTRATOR (0x8)
  const MANAGE_GUILD = 0x20;
  const ADMINISTRATOR = 0x8;
  
  const manageableGuilds = guilds.filter((g) => {
    const perms = BigInt(g.permissions);
    return (perms & BigInt(ADMINISTRATOR)) === BigInt(ADMINISTRATOR) || 
           (perms & BigInt(MANAGE_GUILD)) === BigInt(MANAGE_GUILD) || 
           g.owner;
  });

  return (
    <div className="min-h-screen bg-[var(--color-tiffany-bg)] text-[var(--color-tiffany-text)] p-8">
      <div className="max-w-4xl mx-auto pt-16">
        <div className="mb-12">
          <h1 className="text-4xl font-extrabold tracking-tight mb-4">Select a Server</h1>
          <p className="text-xl text-[var(--color-tiffany-text-secondary)]">
            Choose a server to manage its Tiffany OS configuration.
          </p>
        </div>

        {errorState ? (
          <div className="p-6 rounded-xl border border-[var(--color-tiffany-danger)] bg-[var(--color-tiffany-danger)]/10 text-white">
            <h3 className="font-bold text-lg mb-2 text-[var(--color-tiffany-danger)]">Authentication Error</h3>
            <p>{errorState}</p>
            <a href="/api/auth/login" className="inline-block mt-4 px-4 py-2 bg-[var(--color-tiffany-danger)] text-white font-medium rounded hover:bg-red-600 transition-colors">
              Reconnect Discord
            </a>
          </div>
        ) : manageableGuilds.length === 0 ? (
          <div className="p-12 text-center rounded-2xl border border-[var(--color-tiffany-border)] bg-[var(--color-tiffany-surface)]">
            <div className="w-16 h-16 mx-auto rounded-full bg-[var(--color-tiffany-surface-hover)] flex items-center justify-center mb-4">
              <span className="text-2xl">🤷</span>
            </div>
            <h3 className="text-xl font-bold mb-2">No servers found</h3>
            <p className="text-[var(--color-tiffany-text-secondary)] max-w-md mx-auto">
              You don't have Administrator or Manage Server permissions on any Discord server.
            </p>
          </div>
        ) : (
          <ServerSelectorUI guilds={manageableGuilds} />
        )}
      </div>
    </div>
  );
}
