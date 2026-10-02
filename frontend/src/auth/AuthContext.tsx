import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { getCurrentUser, hasSession, login as loginRequest, logout as clearSession } from "../api/auth";
import type { UserContext } from "../types";

interface AuthContextValue {
  user: UserContext | null;
  loading: boolean;
  error: string | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserContext | null>(null);
  const [loading, setLoading] = useState(hasSession());
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!hasSession()) { setLoading(false); return; }
    getCurrentUser()
      .then(setUser)
      .catch(() => clearSession())
      .finally(() => setLoading(false));
  }, []);

  const value = useMemo<AuthContextValue>(() => ({
    user,
    loading,
    error,
    async login(email, password) {
      setError(null);
      try { setUser(await loginRequest(email, password)); }
      catch (reason) { const message = reason instanceof Error ? reason.message : "Giriş başarısız."; setError(message); throw reason; }
    },
    logout() { clearSession(); setUser(null); setError(null); },
  }), [user, loading, error]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used within AuthProvider");
  return value;
}
