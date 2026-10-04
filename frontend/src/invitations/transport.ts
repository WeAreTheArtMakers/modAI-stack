/** Browser-only transport for a one-time invitation bearer token. */
const PENDING_KEY = "modai.pending_invitation";
const LOGIN_WINDOW_MS = 15 * 60 * 1000;

function validToken(value: unknown): value is string {
  return typeof value === "string" && value.length >= 32 && value.length <= 512;
}

export function tokenFromFragment(hash: string): string | null {
  if (!hash.startsWith("#")) return null;
  const values = new URLSearchParams(hash.slice(1)).getAll("token");
  return values.length === 1 && validToken(values[0]) ? values[0] : null;
}

export function scrubInvitationFragment(): void {
  if (!window.location.hash && !new URLSearchParams(window.location.search).has("token")) return;
  const url = new URL(window.location.href);
  url.hash = "";
  // An old query-string link must not be reused or remain visible. We do not
  // accept it as an invitation credential: its first HTTP request already leaked.
  url.searchParams.delete("token");
  window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}`);
}

export function savePendingInvitation(token: string): boolean {
  if (!validToken(token)) return false;
  try {
    sessionStorage.setItem(PENDING_KEY, JSON.stringify({ token, expiresAt: Date.now() + LOGIN_WINDOW_MS }));
    return true;
  } catch {
    return false;
  }
}

export function pendingInvitation(): string | null {
  try {
    const raw = sessionStorage.getItem(PENDING_KEY);
    if (!raw) return null;
    const stored: unknown = JSON.parse(raw);
    if (stored && typeof stored === "object" && "token" in stored && "expiresAt" in stored
        && validToken(stored.token) && typeof stored.expiresAt === "number" && stored.expiresAt > Date.now()) {
      return stored.token;
    }
  } catch {
    // Storage may be unavailable or malformed. Treat the invitation as absent.
  }
  clearPendingInvitation();
  return null;
}

export function clearPendingInvitation(): void {
  try { sessionStorage.removeItem(PENDING_KEY); } catch { /* Storage may be disabled. */ }
}
