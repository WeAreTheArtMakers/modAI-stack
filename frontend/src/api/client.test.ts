import { beforeEach, describe, expect, it, vi } from "vitest";
import { onAuthFailure, request, tokenStore } from "./client";

describe("API session refresh", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("refreshes once after a 401 and retries the original request", async () => {
    tokenStore.set("expired-access");
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ access_token: "new-access" }), { status: 200, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true }), { status: 200, headers: { "Content-Type": "application/json" } }));

    await expect(request<{ ok: boolean }>("/protected")).resolves.toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(tokenStore.access).toBe("new-access");
  });

  it("clears the session and notifies the app when refresh fails", async () => {
    tokenStore.set("expired-access");
    const onFailure = vi.fn();
    const unsubscribe = onAuthFailure(onFailure);
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(new Response(null, { status: 401 }));

    await expect(request("/protected")).rejects.toMatchObject({ status: 401 });
    expect(tokenStore.access).toBeNull();
    expect(tokenStore.refresh).toBeNull();
    expect(onFailure).toHaveBeenCalledTimes(1);
    unsubscribe();
  });
});
