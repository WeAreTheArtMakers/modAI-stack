import type { UserContext } from "../types";
import { request, tokenStore } from "./client";

export interface LoginResponse {
  access_token: string;
  token_type: string;
}

export async function login(email: string, password: string): Promise<UserContext> {
  const tokens = await request<LoginResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  }, false);
  tokenStore.set(tokens.access_token);
  return request<UserContext>("/auth/me");
}

export function getCurrentUser(): Promise<UserContext> {
  return request<UserContext>("/auth/me");
}

export function hasSession(): boolean {
  return Boolean(tokenStore.access);
}

export async function logout(): Promise<void> {
  try { await request<void>("/auth/logout", { method: "POST" }, false); } catch { /* Local logout still clears access state. */ }
  tokenStore.clear();
}
