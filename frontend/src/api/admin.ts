import type { AdminMembership, AdminOrganization, AdminUser, AdminWorkspace, AuditEvent, CreatedInvitation, Invitation, PlatformStatus, Role } from "../types";
import { request } from "./client";

export function listAdminUsers(search = ""): Promise<AdminUser[]> {
  return request<AdminUser[]>(`/admin/users?limit=100${search ? `&search=${encodeURIComponent(search)}` : ""}`);
}

export function updatePlatformRole(id: number, role: "admin" | "user"): Promise<AdminUser> {
  return request<AdminUser>(`/admin/users/${id}/platform-role`, { method: "PATCH", body: JSON.stringify({ role }) });
}

export function listAdminOrganizations(): Promise<AdminOrganization[]> { return request<AdminOrganization[]>("/admin/organizations"); }
export function createAdminOrganization(payload: { name: string; slug: string }): Promise<AdminOrganization> { return request<AdminOrganization>("/admin/organizations", { method: "POST", body: JSON.stringify(payload) }); }
export function listAdminWorkspaces(organizationId?: number): Promise<AdminWorkspace[]> { return request<AdminWorkspace[]>(`/admin/workspaces${organizationId ? `?organization_id=${organizationId}` : ""}`); }
export function createAdminWorkspace(payload: { organization_id: number; name: string; slug: string }): Promise<AdminWorkspace> { return request<AdminWorkspace>("/admin/workspaces", { method: "POST", body: JSON.stringify(payload) }); }
export function updateAdminWorkspace(id: number, payload: { name?: string; slug?: string }): Promise<AdminWorkspace> { return request<AdminWorkspace>(`/admin/workspaces/${id}`, { method: "PATCH", body: JSON.stringify(payload) }); }

export function listMemberships(organizationId: number): Promise<AdminMembership[]> { return request<AdminMembership[]>(`/admin/memberships?organization_id=${organizationId}`); }
export function createMembership(payload: { user_email: string; organization_id: number; workspace_id?: number; role: Role }): Promise<AdminMembership> { return request<AdminMembership>("/admin/memberships", { method: "POST", body: JSON.stringify(payload) }); }
export function updateMembership(id: number, role: Role): Promise<AdminMembership> { return request<AdminMembership>(`/admin/memberships/${id}`, { method: "PATCH", body: JSON.stringify({ role }) }); }
export function removeMembership(id: number): Promise<void> { return request<void>(`/admin/memberships/${id}`, { method: "DELETE" }); }

export function listInvitations(organizationId: number): Promise<Invitation[]> { return request<Invitation[]>(`/admin/invitations?organization_id=${organizationId}`); }
export function createInvitation(payload: { email: string; organization_id: number; workspace_id?: number; role: Role; expires_in_hours?: number }): Promise<CreatedInvitation> { return request<CreatedInvitation>("/admin/invitations", { method: "POST", body: JSON.stringify(payload) }); }
export function revokeInvitation(id: number): Promise<void> { return request<void>(`/admin/invitations/${id}`, { method: "DELETE" }); }
export function acceptInvitation(token: string): Promise<Invitation> { return request<Invitation>("/admin/invitations/accept", { method: "POST", body: JSON.stringify({ token }) }); }

export function listAuditEvents(): Promise<AuditEvent[]> { return request<AuditEvent[]>("/audit?limit=100"); }
export function getPlatformStatus(): Promise<PlatformStatus> { return request<PlatformStatus>("/admin/platform"); }
