import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { getCurrentUser, hasSession, login as loginRequest, logout as clearSession } from "../api/auth";
import { onAuthFailure } from "../api/client";
import type { UserContext } from "../types";

interface AuthContextValue {
  user: UserContext | null;
  loading: boolean;
  error: string | null;
  login: (email: string, password: string) => Promise<void>;
  refreshUser: () => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [user, setUser] = useState<UserContext | null>(null);
  const [loading, setLoading] = useState(hasSession());
  const [error, setError] = useState<string | null>(null);

  useEffect(() => onAuthFailure(() => {
    queryClient.clear();
    setUser(null);
    setError("Oturumunuz sona erdi. Lütfen yeniden giriş yapın.");
  }), [queryClient]);

  useEffect(() => {
    function handleSessionChange(event: StorageEvent) {
      if (event.key !== "modai.access_token") return;
      queryClient.clear();
      setUser(null);
      if (!event.newValue) { setLoading(false); return; }
      setLoading(true);
      getCurrentUser()
        .then(setUser)
        .catch(() => { void clearSession(); })
        .finally(() => setLoading(false));
    }
    window.addEventListener("storage", handleSessionChange);
    return () => window.removeEventListener("storage", handleSessionChange);
  }, [queryClient]);

  useEffect(() => {
    if (!hasSession()) { setLoading(false); return; }
    getCurrentUser()
      .then(setUser)
      .catch(() => { void clearSession(); })
      .finally(() => setLoading(false));
  }, []);

  const value = useMemo<AuthContextValue>(() => ({
    user,
    loading,
    error,
    async login(email, password) {
      setError(null);
      try { const nextUser = await loginRequest(email, password); queryClient.clear(); setUser(nextUser); }
      catch (reason) { const message = reason instanceof Error ? reason.message : "Giriş başarısız."; setError(message); throw reason; }
    },
    async refreshUser() { setUser(await getCurrentUser()); },
    logout() { queryClient.clear(); void clearSession(); setUser(null); setError(null); },
  }), [user, loading, error, queryClient]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used within AuthProvider");
  return value;
}
