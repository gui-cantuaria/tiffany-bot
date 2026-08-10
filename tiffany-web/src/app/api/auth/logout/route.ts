import { NextRequest, NextResponse } from "next/server";

export async function GET(req: NextRequest) {
  return POST(req);
}

export async function POST(req: NextRequest) {
  // Redirect to landing page
  const response = NextResponse.redirect(new URL("/", req.url));
  
  // Invalidate all authentication cookies
  response.cookies.delete("discord_token");
  response.cookies.delete("oauth_state");
  
  return response;
}
