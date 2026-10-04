import { beforeEach, describe, expect, it, vi } from "vitest";
import { acceptInvitation } from "./admin";
import { inspectInvitation, setupInvitedAccount } from "./auth";

describe("invitation API transport", () => {
  beforeEach(() => { localStorage.clear(); sessionStorage.clear(); vi.restoreAllMocks(); });

  it("sends the bearer secret only in expected POST JSON bodies, never request URLs", async () => {
    const token = "single-use-token-that-is-long-enough";
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => new Response("{}", { status: 200 }));
    await inspectInvitation(token);
    await setupInvitedAccount(token, "employee-chosen-password");
    await acceptInvitation(token);

    const expectedPaths = ["/api/auth/invitations/info", "/api/auth/invitations/setup", "/api/admin/invitations/accept"];
    expect(fetchMock).toHaveBeenCalledTimes(3);
    fetchMock.mock.calls.forEach(([url, options], index) => {
      expect(url).toBe(expectedPaths[index]);
      expect(String(url)).not.toContain(token);
      expect(options?.method).toBe("POST");
      expect(JSON.parse(String(options?.body))).toMatchObject({ token });
    });
    expect(JSON.parse(String(fetchMock.mock.calls[1][1]?.body))).toEqual({ token, password: "employee-chosen-password" });
    expect(localStorage.length).toBe(0);
  });
});
