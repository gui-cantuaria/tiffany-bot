import { cookies } from "next/headers";

export interface DiscordGuild {
  id: string;
  name: string;
  icon: string | null;
  owner: boolean;
  permissions: string;
  features: string[];
}

/**
 * Gets the Discord OAuth token from the HttpOnly cookie.
 */
export async function getSessionToken(): Promise<string | null> {
  const cookieStore = await cookies();
  const token = cookieStore.get("discord_token")?.value;
  return token || null;
}

/**
 * Validates if the given token has admin/manage_guild access to the specified guildId.
 */
export async function verifyGuildAccess(guildId: string, token: string): Promise<boolean> {
  if (!token) return false;

  try {
    const res = await fetch("https://discord.com/api/users/@me/guilds", {
      headers: {
        Authorization: `Bearer ${token}`,
      },
      next: { revalidate: 60 },
    });

    if (!res.ok) {
      return false;
    }

    const guilds: DiscordGuild[] = await res.json();
    const targetGuild = guilds.find(g => g.id === guildId);

    if (!targetGuild) {
      return false;
    }

    const MANAGE_GUILD = 0x20;
    const ADMINISTRATOR = 0x8;
    const perms = BigInt(targetGuild.permissions);

    return targetGuild.owner || 
           (perms & BigInt(ADMINISTRATOR)) === BigInt(ADMINISTRATOR) || 
           (perms & BigInt(MANAGE_GUILD)) === BigInt(MANAGE_GUILD);

  } catch (error) {
    console.error("Error verifying guild access:", error);
    return false;
  }
}
