import { beforeEach, describe, expect, it, vi } from "vitest";
import { clearPendingInvitation, pendingInvitation, savePendingInvitation, tokenFromFragment } from "./transport";

const token = "single-use-token-that-is-long-enough";

describe("invitation browser transport", () => {
  beforeEach(() => { sessionStorage.clear(); localStorage.clear(); vi.restoreAllMocks(); });

  it("accepts exactly one fragment token and never a query string", () => {
    expect(tokenFromFragment(`#token=${encodeURIComponent(token)}`)).toBe(token);
    expect(tokenFromFragment(`?token=${token}`)).toBeNull();
    expect(tokenFromFragment(`#token=${token}&token=${token}`)).toBeNull();
    expect(tokenFromFragment("#token=short")).toBeNull();
  });

  it("stores a login handoff only for this session and expires it promptly", () => {
    const now = 1_000_000;
    vi.spyOn(Date, "now").mockReturnValue(now);
    expect(savePendingInvitation(token)).toBe(true);
    expect(pendingInvitation()).toBe(token);
    expect(localStorage.length).toBe(0);
    vi.spyOn(Date, "now").mockReturnValue(now + 15 * 60 * 1000);
    expect(pendingInvitation()).toBeNull();
    expect(sessionStorage.length).toBe(0);
    savePendingInvitation(token);
    clearPendingInvitation();
    expect(pendingInvitation()).toBeNull();
  });
});
