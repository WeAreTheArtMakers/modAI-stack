import type { Role, UserContext } from "../types";
import { request, tokenStore } from "./client";

export interface LoginResponse {
  access_token: string;
  token_type: string;
}

export interface InvitationSetupInfo {
  status: "pending" | "accepted" | "expired";
  email: string;
  organization_name: string;
  workspace_name: string | null;
  role: Role;
  expires_at: string;
  account_exists: boolean;
}

export function inspectInvitation(token: string): Promise<InvitationSetupInfo> {
  return request<InvitationSetupInfo>("/auth/invitations/info", {
    method: "POST", body: JSON.stringify({ token }),
  }, false);
}

export function setupInvitedAccount(token: string, password: string): Promise<{ email: string }> {
  return request<{ email: string }>("/auth/invitations/setup", {
    method: "POST", body: JSON.stringify({ token, password }),
  }, false);
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
