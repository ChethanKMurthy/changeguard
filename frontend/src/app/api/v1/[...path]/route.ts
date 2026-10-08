/**
 * Same-origin proxy to the ChangeGuard engine (backend-for-frontend).
 *
 * - The browser only talks to this origin, so the engine can stay private and
 *   no CORS configuration is needed.
 * - The engine API key (CHANGEGUARD_API_KEY) is added here, server-side; it is
 *   never sent to the browser.
 * - Request and response bodies are streamed, so uploads and server-sent
 *   progress events pass through without buffering.
 * - Each browser's workspace ID (an HttpOnly cookie) is forwarded so that, on a
 *   shared deployment, visitors only see the analyses they created. Clients
 *   cannot pick a workspace header themselves: only the cookie is honoured.
 */
import type { NextRequest } from "next/server";

import { isValidWorkspace, newWorkspaceId, WORKSPACE_COOKIE, WORKSPACE_HEADER, workspaceCookie, workspacesEnabled } from "@/lib/workspace";

const UPSTREAM = process.env.CHANGEGUARD_API_URL ?? "http://127.0.0.1:8000";
const API_KEY = process.env.CHANGEGUARD_API_KEY;

const FORWARDED_REQUEST_HEADERS = ["accept", "content-type", "last-event-id", "x-request-id"];
const HOP_BY_HOP_RESPONSE_HEADERS = ["connection", "content-encoding", "content-length", "keep-alive", "transfer-encoding"];

type Context = { params: Promise<{ path: string[] }> };

function problem(status: number, title: string, detail: string, code: string): Response {
  return Response.json(
    { type: "about:blank", title, status, detail, code },
    { status, headers: { "content-type": "application/problem+json", "cache-control": "no-store" } },
  );
}

async function forward(request: NextRequest, context: Context): Promise<Response> {
  const { path } = await context.params;
  if (path.some((segment) => segment === "." || segment === ".." || segment.includes("/"))) {
    return problem(400, "Bad request", "invalid path", "invalid_path");
  }
  const target = new URL(`/api/v1/${path.map(encodeURIComponent).join("/")}`, UPSTREAM);
  target.search = request.nextUrl.search;

  const headers = new Headers();
  for (const name of FORWARDED_REQUEST_HEADERS) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  const forwardedFor = request.headers.get("x-forwarded-for");
  if (forwardedFor) headers.set("x-forwarded-for", forwardedFor);
  if (API_KEY) headers.set("x-api-key", API_KEY);

  let issuedWorkspace: string | null = null;
  if (workspacesEnabled()) {
    let workspace = request.cookies.get(WORKSPACE_COOKIE)?.value;
    if (!isValidWorkspace(workspace)) {
      workspace = newWorkspaceId();
      issuedWorkspace = workspace;
    }
    headers.set(WORKSPACE_HEADER, workspace);
  }

  const init: RequestInit & { duplex?: "half" } = {
    method: request.method,
    headers,
    redirect: "manual",
    signal: request.signal,
    cache: "no-store",
  };
  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = request.body;
    init.duplex = "half";
  }

  let upstream: Response;
  try {
    upstream = await fetch(target, init);
  } catch {
    return problem(
      502,
      "Engine unreachable",
      "The ChangeGuard engine did not respond. Start it with `make dev` or check CHANGEGUARD_API_URL.",
      "engine_unreachable",
    );
  }
  const responseHeaders = new Headers(upstream.headers);
  for (const name of HOP_BY_HOP_RESPONSE_HEADERS) responseHeaders.delete(name);
  if (issuedWorkspace) responseHeaders.append("set-cookie", workspaceCookie(issuedWorkspace, request.nextUrl.protocol === "https:"));
  return new Response(upstream.body, { status: upstream.status, statusText: upstream.statusText, headers: responseHeaders });
}

export { forward as DELETE, forward as GET, forward as POST };
