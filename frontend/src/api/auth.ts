import type { UserContext } from "../types";
import { request, tokenStore } from "./client";

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export async function login(email: string, password: string): Promise<UserContext> {
  const tokens = await request<LoginResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  }, false);
  tokenStore.set(tokens.access_token, tokens.refresh_token);
  return request<UserContext>("/auth/me");
}

export function getCurrentUser(): Promise<UserContext> {
  return request<UserContext>("/auth/me");
}

export function hasSession(): boolean {
  return Boolean(tokenStore.access || tokenStore.refresh);
}

export function logout(): void {
  tokenStore.clear();
}
