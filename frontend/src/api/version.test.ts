import { afterEach, describe, expect, it, vi } from "vitest";
import { getBackendVersion } from "./version";

describe("getBackendVersion", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("uses the public no-store version route without attaching an auth header", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ build_sha: "a".repeat(40) }) });
    vi.stubGlobal("fetch", fetchMock);
    await expect(getBackendVersion()).resolves.toEqual({ build_sha: "a".repeat(40) });
    expect(fetchMock).toHaveBeenCalledWith("/api/version", { cache: "no-store", credentials: "omit" });
  });

  it("rejects failed or malformed responses for the best-effort caller to ignore", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false }));
    await expect(getBackendVersion()).rejects.toThrow("Backend version unavailable");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ build_sha: 42 }) }));
    await expect(getBackendVersion()).rejects.toThrow("Backend version unavailable");
  });
});
