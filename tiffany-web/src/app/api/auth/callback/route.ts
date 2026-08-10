import { NextRequest, NextResponse } from "next/server";
import { checkRateLimit } from "@/lib/rate-limit";
import crypto from "crypto";

export async function GET(req: NextRequest) {
  const ip = req.headers.get("x-forwarded-for") || "127.0.0.1";
  
  // Rate limit callback
  const rateLimit = await checkRateLimit(ip, "oauth_callback", 20, 900);
  if (!rateLimit.success) {
    return NextResponse.json({ error: "Too many login attempts." }, { status: 429 });
  }

  const code = req.nextUrl.searchParams.get("code");
  const error = req.nextUrl.searchParams.get("error");
  const returnedState = req.nextUrl.searchParams.get("state");
  
  if (error) {
    return NextResponse.redirect(new URL("/?error=auth_failed", req.url));
  }
  
  if (!code) {
    return NextResponse.redirect(new URL("/?error=no_code", req.url));
  }

  // Validate State for CSRF protection
  const storedState = req.cookies.get("oauth_state")?.value;
  
  if (!storedState || !returnedState) {
    console.warn("Missing OAuth state");
    return NextResponse.redirect(new URL("/?error=missing_state", req.url));
  }
  
  try {
    const a = Buffer.from(storedState);
    const b = Buffer.from(returnedState);
    if (a.length !== b.length || !crypto.timingSafeEqual(a, b)) {
      console.warn("OAuth state mismatch (CSRF attempt)");
      return NextResponse.redirect(new URL("/?error=invalid_state", req.url));
    }
  } catch (e) {
    console.warn("OAuth state comparison failed");
    return NextResponse.redirect(new URL("/?error=invalid_state", req.url));
  }

  const clientId = process.env.DISCORD_CLIENT_ID;
  const clientSecret = process.env.DISCORD_CLIENT_SECRET;
  const redirectUri = process.env.NEXT_PUBLIC_APP_URL 
    ? `${process.env.NEXT_PUBLIC_APP_URL}/api/auth/callback` 
    : "http://localhost:3000/api/auth/callback";

  if (!clientId || !clientSecret) {
    return NextResponse.json({ error: "Missing Discord OAuth credentials" }, { status: 500 });
  }

  try {
    let tokenData;
    
    const tokenResponse = await fetch("https://discord.com/api/oauth2/token", {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: new URLSearchParams({
        client_id: clientId,
        client_secret: clientSecret,
        grant_type: "authorization_code",
        code,
        redirect_uri: redirectUri,
      }),
    });

    tokenData = await tokenResponse.json();

    if (!tokenResponse.ok) {
      console.error("Token exchange failed:", tokenData);
      return NextResponse.redirect(new URL("/?error=token_exchange_failed", req.url));
    }

    // Set secure HttpOnly cookie for session
    const response = NextResponse.redirect(new URL("/dashboard", req.url));
    
    // Invalidate the OAuth state cookie
    response.cookies.delete("oauth_state");
    
    response.cookies.set("discord_token", tokenData.access_token, {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax",
      maxAge: tokenData.expires_in,
      path: "/",
    });

    return response;
  } catch (err) {
    console.error("OAuth Callback error:", err);
    return NextResponse.redirect(new URL("/?error=internal_auth_error", req.url));
  }
}
