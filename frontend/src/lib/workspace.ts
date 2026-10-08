/**
 * Workspaces keep one browser's analyses invisible to everyone else when the
 * web app is shared. The ID is random, lives in an HttpOnly cookie, and is
 * forwarded to the engine by the same-origin API proxy. It is not a login:
 * anyone holding the cookie value sees that workspace.
 */
export const WORKSPACE_COOKIE = "cg_ws";
export const WORKSPACE_HEADER = "x-changeguard-workspace";
export const WORKSPACE_MAX_AGE = 60 * 60 * 24 * 365;

const VALID = /^[A-Za-z0-9_-]{16,64}$/;

export function isValidWorkspace(value: string | undefined | null): value is string {
  return typeof value === "string" && VALID.test(value);
}

export function newWorkspaceId(): string {
  return crypto.randomUUID().replaceAll("-", "");
}

/** Set CHANGEGUARD_WORKSPACES=shared to let everyone using this web app see every report (e.g. behind team SSO). */
export function workspacesEnabled(): boolean {
  return process.env.CHANGEGUARD_WORKSPACES !== "shared";
}

export function workspaceCookie(value: string, secure: boolean): string {
  return `${WORKSPACE_COOKIE}=${value}; Path=/; Max-Age=${WORKSPACE_MAX_AGE}; HttpOnly; SameSite=Lax${secure ? "; Secure" : ""}`;
}
