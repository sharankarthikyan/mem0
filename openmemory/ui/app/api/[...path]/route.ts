import { NextRequest } from "next/server";

// Server-side API proxy for the OpenMemory dashboard.
//
// The browser calls the UI's OWN origin (NEXT_PUBLIC_API_URL = the UI domain),
// so requests land here on the Next server, which forwards them to the real API.
// Two things make this the right pattern when the API is behind Cloudflare Access:
//   1. The CF Access service token (CF-Access-Client-Id / -Secret) is injected
//      HERE, server-side, and never reaches the browser (it's a secret).
//   2. Same-origin browser calls → no CORS and no cross-domain CF cookie issues.
//
// Configure on the UI service (all SERVER-SIDE, not NEXT_PUBLIC_*):
//   OPENMEMORY_API_ORIGIN   real API base, e.g. https://mem0-mcp.trybabble.io
//                           (or the Railway private host, e.g.
//                           http://openmemory-mcp.railway.internal:8765, which
//                           bypasses Cloudflare entirely — then no token needed)
//   CF_ACCESS_CLIENT_ID     Cloudflare Access service token id     (omit if internal)
//   CF_ACCESS_CLIENT_SECRET Cloudflare Access service token secret (omit if internal)

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const API_ORIGIN = (process.env.OPENMEMORY_API_ORIGIN || "http://localhost:8765").replace(/\/$/, "");
const CF_ACCESS_CLIENT_ID = process.env.CF_ACCESS_CLIENT_ID;
const CF_ACCESS_CLIENT_SECRET = process.env.CF_ACCESS_CLIENT_SECRET;

// Only these request headers are forwarded upstream (avoid leaking host/cookies).
const FORWARDED_REQUEST_HEADERS = ["content-type", "accept"];

async function proxy(req: NextRequest, pathParts: string[]): Promise<Response> {
  const search = req.nextUrl.search;
  const targetUrl = `${API_ORIGIN}/api/${pathParts.join("/")}${search}`;

  const headers = new Headers();
  for (const name of FORWARDED_REQUEST_HEADERS) {
    const value = req.headers.get(name);
    if (value) headers.set(name, value);
  }
  if (CF_ACCESS_CLIENT_ID) headers.set("CF-Access-Client-Id", CF_ACCESS_CLIENT_ID);
  if (CF_ACCESS_CLIENT_SECRET) headers.set("CF-Access-Client-Secret", CF_ACCESS_CLIENT_SECRET);

  // Follow redirects server-side. FastAPI issues 307s for trailing-slash
  // normalization (/memories -> /memories/); the hop stays on the same origin
  // (mem0-mcp -> mem0-mcp) so undici keeps the CF-Access-* headers. The browser
  // only ever sees the final response — no cross-origin Location leaks back.
  const init: RequestInit = { method: req.method, headers, redirect: "follow" };
  if (req.method !== "GET" && req.method !== "HEAD") {
    const body = await req.arrayBuffer();
    if (body.byteLength > 0) init.body = body;
  }

  let upstream: Response;
  try {
    upstream = await fetch(targetUrl, init);
  } catch (err) {
    return new Response(
      JSON.stringify({ error: "Upstream API unreachable", detail: String(err) }),
      { status: 502, headers: { "content-type": "application/json" } },
    );
  }

  const responseHeaders = new Headers();
  const contentType = upstream.headers.get("content-type");
  if (contentType) responseHeaders.set("content-type", contentType);
  const responseBody = await upstream.arrayBuffer();
  return new Response(responseBody, { status: upstream.status, headers: responseHeaders });
}

type RouteContext = { params: Promise<{ path: string[] }> };

export async function GET(req: NextRequest, ctx: RouteContext) {
  return proxy(req, (await ctx.params).path);
}
export async function POST(req: NextRequest, ctx: RouteContext) {
  return proxy(req, (await ctx.params).path);
}
export async function PUT(req: NextRequest, ctx: RouteContext) {
  return proxy(req, (await ctx.params).path);
}
export async function PATCH(req: NextRequest, ctx: RouteContext) {
  return proxy(req, (await ctx.params).path);
}
export async function DELETE(req: NextRequest, ctx: RouteContext) {
  return proxy(req, (await ctx.params).path);
}
export async function OPTIONS(req: NextRequest, ctx: RouteContext) {
  return proxy(req, (await ctx.params).path);
}
