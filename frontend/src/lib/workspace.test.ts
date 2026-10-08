import { describe, expect, it } from "vitest";

import { isValidWorkspace, newWorkspaceId, workspaceCookie } from "./workspace";

describe("workspace ids", () => {
  it("generates ids the engine accepts", () => {
    const id = newWorkspaceId();
    expect(isValidWorkspace(id)).toBe(true);
    expect(newWorkspaceId()).not.toBe(id);
  });

  it("rejects malformed values", () => {
    for (const value of [undefined, null, "", "short", "../../etc/passwd-xxxxxxxx", "a".repeat(65), "has space in it 123456"]) {
      expect(isValidWorkspace(value)).toBe(false);
    }
  });

  it("issues an HttpOnly, SameSite cookie, Secure over https", () => {
    expect(workspaceCookie("a".repeat(32), true)).toMatch(/HttpOnly; SameSite=Lax; Secure$/);
    expect(workspaceCookie("a".repeat(32), false)).not.toContain("Secure");
  });
});
