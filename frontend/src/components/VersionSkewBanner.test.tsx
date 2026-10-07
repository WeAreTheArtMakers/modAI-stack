import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getBackendVersion } from "../api/version";
import { VersionSkewBanner } from "./VersionSkewBanner";

vi.mock("../api/version", () => ({ getBackendVersion: vi.fn() }));

const shaA = "a".repeat(40);
const shaB = "b".repeat(40);

describe("VersionSkewBanner", () => {
  beforeEach(() => vi.mocked(getBackendVersion).mockReset());
  afterEach(() => vi.useRealTimers());

  it("does not warn for matching valid release SHAs", async () => {
    vi.mocked(getBackendVersion).mockResolvedValue({ build_sha: shaA });
    render(<VersionSkewBanner frontendBuildSha={shaA} />);
    await waitFor(() => expect(getBackendVersion).toHaveBeenCalledTimes(1));
    expect(screen.queryByText("New version available")).not.toBeInTheDocument();
  });

  it("shows the manual reload banner only for different valid release SHAs", async () => {
    vi.mocked(getBackendVersion).mockResolvedValue({ build_sha: shaB });
    render(<VersionSkewBanner frontendBuildSha={shaA} />);
    expect(await screen.findByText("New version available")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reload" })).toBeInTheDocument();
  });

  it.each([
    ["development frontend", "development", shaB],
    ["development backend", shaA, "development"],
    ["empty backend", shaA, ""],
    ["malformed backend", shaA, "not-a-sha"],
  ])("does not warn for %s", async (_label, frontendSha, backendSha) => {
    vi.mocked(getBackendVersion).mockResolvedValue({ build_sha: backendSha });
    render(<VersionSkewBanner frontendBuildSha={frontendSha} />);
    await waitFor(() => expect(getBackendVersion).toHaveBeenCalledTimes(1));
    expect(screen.queryByText("New version available")).not.toBeInTheDocument();
  });

  it("ignores unavailable version data without showing a false warning", async () => {
    vi.mocked(getBackendVersion).mockResolvedValue({ build_sha: "unavailable" });
    render(<VersionSkewBanner frontendBuildSha={shaA} />);
    await act(async () => { await Promise.resolve(); });
    expect(getBackendVersion).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("New version available")).not.toBeInTheDocument();
  });

  it("rechecks on focus and visibility restoration", async () => {
    vi.mocked(getBackendVersion).mockResolvedValue({ build_sha: shaA });
    render(<VersionSkewBanner frontendBuildSha={shaA} />);
    await waitFor(() => expect(getBackendVersion).toHaveBeenCalledTimes(1));
    act(() => window.dispatchEvent(new Event("focus")));
    await waitFor(() => expect(getBackendVersion).toHaveBeenCalledTimes(2));
    const originalVisibility = document.visibilityState;
    Object.defineProperty(document, "visibilityState", { configurable: true, value: "visible" });
    act(() => document.dispatchEvent(new Event("visibilitychange")));
    await waitFor(() => expect(getBackendVersion).toHaveBeenCalledTimes(3));
    Object.defineProperty(document, "visibilityState", { configurable: true, value: originalVisibility });
  });

  it("polls once per minute and removes the timer when unmounted", async () => {
    vi.useFakeTimers();
    vi.mocked(getBackendVersion).mockResolvedValue({ build_sha: shaA });
    const { unmount } = render(<VersionSkewBanner frontendBuildSha={shaA} />);
    await act(async () => { await Promise.resolve(); });
    expect(getBackendVersion).toHaveBeenCalledTimes(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(60_000); });
    expect(getBackendVersion).toHaveBeenCalledTimes(2);
    unmount();
    await act(async () => { await vi.advanceTimersByTimeAsync(120_000); });
    expect(getBackendVersion).toHaveBeenCalledTimes(2);
  });
});
