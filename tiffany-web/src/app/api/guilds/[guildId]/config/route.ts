import { NextRequest, NextResponse } from "next/server";
import { getSessionToken, verifyGuildAccess } from "@/lib/auth";

const INTERNAL_API_URL = process.env.INTERNAL_API_URL || "http://127.0.0.1:8081";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ guildId: string }> }
) {
  const { guildId } = await params;
  const token = await getSessionToken();

  if (!token) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const isAuthorized = await verifyGuildAccess(guildId, token);
  if (!isAuthorized) {
    return NextResponse.json({ error: "Forbidden: You do not have permission to manage this server." }, { status: 403 });
  }

  try {
    const res = await fetch(`${INTERNAL_API_URL}/api/guilds/${guildId}/config`);
    if (!res.ok) {
      return NextResponse.json({ error: "Internal Backend Error" }, { status: res.status });
    }
    const data = await res.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error("Error communicating with internal backend:", error);
    return NextResponse.json({ error: "Service Unavailable" }, { status: 503 });
  }
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ guildId: string }> }
) {
  const { guildId } = await params;
  const token = await getSessionToken();

  if (!token) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const isAuthorized = await verifyGuildAccess(guildId, token);
  if (!isAuthorized) {
    return NextResponse.json({ error: "Forbidden: You do not have permission to manage this server." }, { status: 403 });
  }

  // Basic CSRF Protection: Enforce custom header and application/json
  const csrfHeader = request.headers.get("x-tiffany-csrf");
  if (csrfHeader !== "1") {
    return NextResponse.json({ error: "Missing or invalid CSRF header" }, { status: 403 });
  }

  const contentType = request.headers.get("content-type");
  if (!contentType || !contentType.includes("application/json")) {
    return NextResponse.json({ error: "Unsupported Media Type" }, { status: 415 });
  }

  // Enforce Payload Size Limit (50 KB)
  const contentLength = request.headers.get("content-length");
  if (contentLength && parseInt(contentLength, 10) > 51200) {
    return NextResponse.json({ error: "Payload Too Large" }, { status: 413 });
  }

  let payload;
  try {
    const text = await request.text();
    // Double check size after reading in case content-length was spoofed or missing
    if (text.length > 51200) {
      return NextResponse.json({ error: "Payload Too Large" }, { status: 413 });
    }
    payload = JSON.parse(text);
  } catch (err) {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  // Structural Validation: Ensure payload is an object
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return NextResponse.json({ error: "Invalid payload structure" }, { status: 400 });
  }

  try {
    const res = await fetch(`${INTERNAL_API_URL}/api/guilds/${guildId}/config`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });
    
    if (!res.ok) {
      return NextResponse.json({ error: "Internal Backend Error" }, { status: res.status });
    }
    
    const data = await res.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error("Error communicating with internal backend:", error);
    return NextResponse.json({ error: "Service Unavailable" }, { status: 503 });
  }
}
