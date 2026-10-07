import { useCallback, useEffect, useState } from "react";
import { getBackendVersion } from "../api/version";
import { FRONTEND_BUILD_SHA, versionsMismatch } from "../version";

const VERSION_POLL_INTERVAL_MS = 60_000;

export function VersionSkewBanner({ frontendBuildSha = FRONTEND_BUILD_SHA }: { frontendBuildSha?: string }) {
  const [backendBuildSha, setBackendBuildSha] = useState<string | null>(null);
  const checkVersion = useCallback(async () => {
    try {
      const version = await getBackendVersion();
      setBackendBuildSha(version.build_sha);
    } catch {
      // Version observability is best-effort and must not affect the user session.
    }
  }, []);

  useEffect(() => {
    void checkVersion();
    const interval = window.setInterval(() => void checkVersion(), VERSION_POLL_INTERVAL_MS);
    const onFocus = () => void checkVersion();
    const onVisibilityChange = () => {
      if (document.visibilityState === "visible") void checkVersion();
    };
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      window.clearInterval(interval);
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [checkVersion]);

  if (!backendBuildSha || !versionsMismatch(frontendBuildSha, backendBuildSha)) return null;

  return (
    <div
      role="status"
      className="flex items-center justify-center gap-3 bg-amber-100 px-4 py-2 text-center text-sm font-medium text-amber-950 dark:bg-amber-950 dark:text-amber-100"
    >
      <span>New version available</span>
      <button
        type="button"
        className="rounded-md border border-current px-3 py-1 font-semibold underline underline-offset-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
        onClick={() => window.location.reload()}
      >
        Reload
      </button>
    </div>
  );
}
