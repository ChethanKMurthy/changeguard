import { NextResponse, type NextRequest } from "next/server";

import { isValidWorkspace, newWorkspaceId, WORKSPACE_COOKIE, WORKSPACE_MAX_AGE, workspacesEnabled } from "@/lib/workspace";

/**
 * Give each browser a workspace on its first page view, before any API call
 * runs, so parallel requests from that page all carry the same ID.
 */
export function proxy(request: NextRequest) {
  const response = NextResponse.next();
  if (workspacesEnabled() && !isValidWorkspace(request.cookies.get(WORKSPACE_COOKIE)?.value)) {
    response.cookies.set(WORKSPACE_COOKIE, newWorkspaceId(), {
      httpOnly: true,
      sameSite: "lax",
      secure: request.nextUrl.protocol === "https:",
      path: "/",
      maxAge: WORKSPACE_MAX_AGE,
    });
  }
  return response;
}

export const config = {
  // Pages only: skip the API proxy (it handles its own cookie), Next internals, and static files.
  matcher: ["/((?!api/|_next/|samples/|favicon.ico).*)"],
};
