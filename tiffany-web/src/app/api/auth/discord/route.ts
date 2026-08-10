import { NextRequest, NextResponse } from "next/server";
import { checkRateLimit } from "@/lib/rate-limit";

export async function GET(req: NextRequest) {
  const ip = req.headers.get("x-forwarded-for") || "127.0.0.1";
  
  // Rate limit: 10 login attempts per 15 minutes per IP
  const rateLimit = await checkRateLimit(ip, "oauth_init", 10, 900);
  if (!rateLimit.success) {
    return NextResponse.json({ error: "Too many login attempts, please try again later." }, { status: 429 });
  }

  const clientId = process.env.DISCORD_CLIENT_ID;
  const redirectUri = process.env.NEXT_PUBLIC_APP_URL 
    ? `${process.env.NEXT_PUBLIC_APP_URL}/api/auth/callback` 
    : "http://localhost:3000/api/auth/callback";

  if (!clientId) {
    return NextResponse.json({ error: "DISCORD_CLIENT_ID not configured" }, { status: 500 });
  }

  // Generate cryptographically secure state
  const stateBuffer = new Uint8Array(32);
  crypto.getRandomValues(stateBuffer);
  const state = Buffer.from(stateBuffer).toString("hex");

  const scope = "identify guilds";
  const authUrl = new URL("https://discord.com/api/oauth2/authorize");
  authUrl.searchParams.set("client_id", clientId);
  authUrl.searchParams.set("redirect_uri", redirectUri);
  authUrl.searchParams.set("response_type", "code");
  authUrl.searchParams.set("scope", scope);
  authUrl.searchParams.set("state", state);
  authUrl.searchParams.set("prompt", "none");

  const response = NextResponse.redirect(authUrl.toString());
  
  // Set state cookie to validate in callback
  // Use Lax because OAuth redirect is a cross-site top-level navigation
  response.cookies.set("oauth_state", state, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    maxAge: 600, // 10 minutes to complete login
    path: "/",
  });

  return response;
}
