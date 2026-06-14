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
  // The catch-all [...path] drops a trailing slash, but several FastAPI routes
  // are declared at "/" (e.g. /api/v1/apps/, /api/v1/memories/, /api/v1/config/,
  // /api/v1/stats/). Preserve the inbound trailing slash so the upstream matches
  // directly instead of issuing a 307 trailing-slash redirect.
  const pathname = req.nextUrl.pathname; // e.g. /api/v1/apps/
  const trailing = pathname.endsWith("/") ? "/" : "";
  const targetUrl = `${API_ORIGIN}/api/${pathParts.join("/")}${trailing}${search}`;

  const headers = new Headers();
  for (const name of FORWARDED_REQUEST_HEADERS) {
    const value = req.headers.get(name);
    if (value) headers.set(name, value);
  }
  if (CF_ACCESS_CLIENT_ID) headers.set("CF-Access-Client-Id", CF_ACCESS_CLIENT_ID);
  if (CF_ACCESS_CLIENT_SECRET) headers.set("CF-Access-Client-Secret", CF_ACCESS_CLIENT_SECRET);

  // Buffer the body once so it can be re-sent across a manual redirect re-fetch.
  let body: ArrayBuffer | undefined;
  if (req.method !== "GET" && req.method !== "HEAD") {
    const buf = await req.arrayBuffer();
    if (buf.byteLength > 0) body = buf;
  }

  // Handle redirects MANUALLY. We must distinguish two very different 3xx cases:
  //   - Same-origin (FastAPI trailing-slash 307: /memories -> /memories/): safe
  //     to follow, and we re-attach the CF-Access-* headers ourselves so they are
  //     never dropped.
  //   - Cross-origin (CF Access bounces a rejected/expired service token to
  //     <team>.cloudflareaccess.com): undici would STRIP the CF-Access-* headers
  //     on a cross-origin hop (stripHeadersOnCrossOriginRedirect) and land on an
  //     HTML login page, which we would otherwise return to the browser as a
  //     200 text/html — silently masking the auth failure. Instead we surface it
  //     as a clear JSON error.
  const apiHost = new URL(API_ORIGIN).host;
  const MAX_HOPS = 5;
  let currentUrl = targetUrl;
  let upstream: Response;

  for (let hop = 0; ; hop++) {
    const init: RequestInit = { method: req.method, headers, redirect: "manual" };
    if (body) init.body = body;

    try {
      upstream = await fetch(currentUrl, init);
    } catch (err) {
      return new Response(
        JSON.stringify({ error: "Upstream API unreachable", detail: String(err) }),
        { status: 502, headers: { "content-type": "application/json" } },
      );
    }

    const isRedirect = upstream.status >= 300 && upstream.status < 400;
    if (!isRedirect) break;

    const location = upstream.headers.get("location");
    if (!location) break; // nothing to follow; fall through and return as-is

    const nextUrl = new URL(location, currentUrl);
    if (nextUrl.host !== apiHost) {
      // Cross-origin redirect == CF Access rejected the service token (or the
      // session expired). Do NOT follow into the IdP login HTML.
      return new Response(
        JSON.stringify({
          error: "Cloudflare Access rejected the upstream request",
          detail:
            "Upstream returned a cross-origin redirect to the login page. " +
            "Verify CF_ACCESS_CLIENT_ID / CF_ACCESS_CLIENT_SECRET and that the " +
            "API's CF Access application has a Service Auth policy for this token.",
          location: nextUrl.origin,
        }),
        { status: 502, headers: { "content-type": "application/json" } },
      );
    }

    if (hop >= MAX_HOPS) {
      return new Response(
        JSON.stringify({ error: "Too many upstream redirects", detail: nextUrl.toString() }),
        { status: 508, headers: { "content-type": "application/json" } },
      );
    }
    currentUrl = nextUrl.toString();
    // loop: re-fetch same-origin with CF-Access-* headers still attached
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
