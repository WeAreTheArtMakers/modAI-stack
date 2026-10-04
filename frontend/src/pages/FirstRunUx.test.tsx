import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router";
import type { KnowledgeBase, UserContext, Workspace } from "../types";
import { ApiError } from "../api/client";
import { AdminPage } from "./AdminPage";
import { DashboardPage } from "./DashboardPage";
import { KnowledgeBasesPage } from "./KnowledgeBasesPage";
import { KnowledgeBaseDetailPage } from "./KnowledgeBaseDetailPage";
import { DocumentsPage } from "./DocumentsPage";
import { ChatPage } from "./ChatPage";

const mocks = vi.hoisted(() => ({
  user: null as UserContext | null,
  current: null as Workspace | null,
  refreshUser: vi.fn(),
  listAdminOrganizations: vi.fn(), listAdminWorkspaces: vi.fn(), createAdminWorkspace: vi.fn(),
  listMemberships: vi.fn(), createMembership: vi.fn(), updateMembership: vi.fn(), removeMembership: vi.fn(),
  listKnowledgeBases: vi.fn(), createKnowledgeBase: vi.fn(), listDocuments: vi.fn(), streamRag: vi.fn(),
}));
vi.mock("../auth/AuthContext", () => ({ useAuth: () => ({ user: mocks.user, refreshUser: mocks.refreshUser }) }));
vi.mock("../workspace/WorkspaceContext", () => ({ useWorkspace: () => ({ current: mocks.current, workspaces: mocks.current ? [mocks.current] : [], loading: false, setCurrentId: vi.fn() }) }));
vi.mock("../api/admin", () => ({
  listAdminOrganizations: mocks.listAdminOrganizations, listAdminWorkspaces: mocks.listAdminWorkspaces,
  createAdminWorkspace: mocks.createAdminWorkspace, listMemberships: mocks.listMemberships,
  createMembership: mocks.createMembership, updateMembership: mocks.updateMembership, removeMembership: mocks.removeMembership,
}));
vi.mock("../api/knowledgeBases", () => ({ listKnowledgeBases: mocks.listKnowledgeBases, createKnowledgeBase: mocks.createKnowledgeBase }));
vi.mock("../api/documents", () => ({ listDocuments: mocks.listDocuments }));
vi.mock("../api/websocket", () => ({ streamRag: mocks.streamRag }));

const admin: UserContext = { id: 1, email: " Admin@Example.com ", role: "admin", organizations: [], workspaces: [] };
const workspace: Workspace = { id: 7, organization_id: 2, name: "Engineering", slug: "engineering", membership_role: "admin" };
const kb: KnowledgeBase = { id: 13, workspace_id: 7, name: "Internal Docs", slug: "internal-docs", description: null, membership_role: "admin" };
const employee: UserContext = { id: 3, email: "employee@example.com", role: "user", organizations: [], workspaces: [] };

function page(node: ReactNode, path = "/") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}>{node}</MemoryRouter></QueryClientProvider>);
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.user = admin;
  mocks.current = null;
  mocks.refreshUser.mockResolvedValue(undefined);
  mocks.listAdminOrganizations.mockResolvedValue([{ id: 2, name: "WATAM", slug: "watam", workspace_count: 0, member_count: 0, knowledge_base_count: 0, document_count: 0 }]);
  mocks.listAdminWorkspaces.mockResolvedValue([]);
  mocks.listMemberships.mockResolvedValue([]);
  mocks.listKnowledgeBases.mockResolvedValue([]);
  mocks.listDocuments.mockResolvedValue({ items: [], total: 0, limit: 50, offset: 0 });
});

describe("first-run enterprise flows", () => {
  it("guides a platform admin without granting implicit tenant access", async () => {
    page(<DashboardPage />);
    expect(await screen.findByText("Kurumsal alanınızı hazırlayın")).toBeInTheDocument();
    expect(screen.getByText(/Platform yöneticiliği tenant belgelerine otomatik erişim vermez/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Organization Admin erişimi adımına git" })).toHaveAttribute("href", "/admin/memberships");
  });

  it("does not offer tenant administration to a user without a workspace", async () => {
    mocks.user = employee;
    page(<KnowledgeBasesPage />);
    expect(await screen.findByText("Workspace gerekli")).toBeInTheDocument();
    expect(screen.getByText(/Organization yöneticinizden erişim isteyin/)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Workspace oluştur" })).not.toBeInTheDocument();
  });

  it("self-assigns the authenticated platform admin to the selected organization", async () => {
    mocks.createMembership.mockResolvedValue({ id: 9 });
    page(<AdminPage section="memberships" />);
    await userEvent.setup().click(await screen.findByRole("button", { name: "Kendimi Organization Admin yap" }));
    await waitFor(() => expect(mocks.createMembership).toHaveBeenCalledWith({ user_email: "Admin@Example.com", organization_id: 2, role: "admin" }));
    expect(mocks.refreshUser).toHaveBeenCalled();
  });

  it("upgrades an existing organization-wide user or manager instead of duplicating", async () => {
    mocks.listMemberships.mockResolvedValue([{ id: 8, user_id: 1, user_email: "admin@example.com", organization_id: 2, workspace_id: null, role: "manager" }]);
    mocks.updateMembership.mockResolvedValue({ id: 8 });
    page(<AdminPage section="memberships" />);
    await userEvent.setup().click(await screen.findByRole("button", { name: "Kendimi Organization Admin yap" }));
    await waitFor(() => expect(mocks.updateMembership).toHaveBeenCalledWith(8, "admin"));
    expect(mocks.createMembership).not.toHaveBeenCalled();
  });

  it("does not treat workspace-only membership as organization-wide or duplicate an existing admin", async () => {
    mocks.listMemberships.mockResolvedValue([{ id: 8, user_id: 1, user_email: "admin@example.com", organization_id: 2, workspace_id: 7, role: "admin" }]);
    mocks.createMembership.mockResolvedValue({ id: 9 });
    const view = page(<AdminPage section="memberships" />);
    await userEvent.setup().click(await screen.findByRole("button", { name: "Kendimi Organization Admin yap" }));
    await waitFor(() => expect(mocks.createMembership).toHaveBeenCalledWith({ user_email: "Admin@Example.com", organization_id: 2, role: "admin" }));
    view.unmount();
    mocks.listMemberships.mockResolvedValue([{ id: 9, user_id: 1, user_email: "admin@example.com", organization_id: 2, workspace_id: null, role: "admin" }]);
    page(<AdminPage section="memberships" />);
    expect(await screen.findByText("Organization Admin")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Kendimi Organization Admin yap" })).not.toBeInTheDocument();
  });

  it("distinguishes existing accounts from invitations and explains user-not-found", async () => {
    mocks.createMembership.mockRejectedValue(new ApiError(404, "User not found"));
    page(<AdminPage section="memberships" />);
    expect(await screen.findByRole("link", { name: "Yeni çalışan davet et" })).toHaveAttribute("href", "/admin/invitations");
    await userEvent.setup().click(screen.getByRole("button", { name: "Mevcut hesabı ekle" }));
    fireEvent.change(screen.getByLabelText("Kullanıcı e-postası"), { target: { value: "unknown@example.com" } });
    await userEvent.setup().click(screen.getByRole("button", { name: "Ekle" }));
    expect(await screen.findByText(/Bu e-posta ile kayıtlı bir hesap bulunamadı/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Davet oluştur" })).toHaveAttribute("href", "/admin/invitations");
  });

  it("refreshes workspace navigation after workspace creation", async () => {
    mocks.createAdminWorkspace.mockResolvedValue({ id: 7 });
    page(<AdminPage section="workspaces" />);
    await userEvent.setup().click(await screen.findByRole("button", { name: "Yeni Workspace" }));
    fireEvent.change(screen.getByPlaceholderText("Ad"), { target: { value: "Engineering" } });
    fireEvent.change(screen.getByPlaceholderText("slug"), { target: { value: "engineering" } });
    await userEvent.setup().click(screen.getByRole("button", { name: "Oluştur" }));
    await waitFor(() => expect(mocks.createAdminWorkspace).toHaveBeenCalledWith({ organization_id: 2, name: "Engineering", slug: "engineering" }));
    expect(mocks.refreshUser).toHaveBeenCalled();
  });

  it("offers KB creation to managers/admins but not read-only users", async () => {
    mocks.current = workspace;
    const view = page(<KnowledgeBasesPage />);
    expect(await screen.findByText("Bu Workspace'te henüz bir Knowledge Base yok")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Yeni Knowledge Base" }).length).toBeGreaterThan(0);
    view.unmount();
    mocks.current = { ...workspace, membership_role: "user" };
    page(<KnowledgeBasesPage />);
    expect(await screen.findByText("Bu Workspace'te henüz bir Knowledge Base yok")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Yeni Knowledge Base" })).not.toBeInTheDocument();
    expect(screen.getByText(/manager veya admin yetkisi gerekir/)).toBeInTheDocument();
  });

  it("shows a newly created KB without a reload", async () => {
    mocks.current = workspace;
    mocks.createKnowledgeBase.mockResolvedValue(kb);
    mocks.listKnowledgeBases.mockResolvedValueOnce([]).mockResolvedValue([kb]);
    page(<KnowledgeBasesPage />);
    await userEvent.setup().click(await screen.findAllByRole("button", { name: "Yeni Knowledge Base" }).then((items) => items[0]));
    fireEvent.change(screen.getByPlaceholderText("Engineering"), { target: { value: "Internal Docs" } });
    await userEvent.setup().click(screen.getByRole("button", { name: "Oluştur" }));
    expect(await screen.findByRole("link", { name: /Internal Docs/ })).toHaveAttribute("href", "/knowledge-bases/13");
  });

  it("guides document setup and never offers upload without a KB", async () => {
    mocks.current = workspace;
    page(<DocumentsPage />);
    expect(await screen.findByText("Belge yüklemek için Knowledge Base gerekli")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Knowledge Base oluştur" })).toHaveAttribute("href", "/knowledge-bases");
    expect(screen.queryByText(/Dosyaları buraya/)).not.toBeInTheDocument();
  });

  it("explains the zero-KB chat state and selects the only authorized KB", async () => {
    mocks.current = workspace;
    const view = page(<ChatPage />);
    expect(await screen.findByText("Bu Workspace'te henüz RAG kaynağı yok")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Knowledge Base oluştur" })).toHaveAttribute("href", "/knowledge-bases");
    view.unmount();
    mocks.listKnowledgeBases.mockResolvedValue([kb]);
    page(<ChatPage />);
    expect(await screen.findByRole("checkbox", { name: /Internal Docs/ })).toBeChecked();
  });

  it("preselects only a requested KB authorized in the current workspace", async () => {
    mocks.current = workspace;
    mocks.listKnowledgeBases.mockResolvedValue([kb, { ...kb, id: 14, name: "HR" }, { ...kb, id: 99, name: "Other tenant", workspace_id: 99 }]);
    const view = page(<ChatPage />, "/chat?kb=14");
    expect(await screen.findByRole("checkbox", { name: /HR/ })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: /Internal Docs/ })).not.toBeChecked();
    view.unmount();
    page(<ChatPage />, "/chat?kb=99");
    expect(await screen.findByRole("checkbox", { name: /Internal Docs/ })).not.toBeChecked();
    expect(screen.queryByRole("checkbox", { name: /Other tenant/ })).not.toBeInTheDocument();
  });

  it("ignores a malformed KB query parameter without selecting unrelated sources", async () => {
    mocks.current = workspace;
    mocks.listKnowledgeBases.mockResolvedValue([kb, { ...kb, id: 14, name: "HR" }]);
    page(<ChatPage />, "/chat?kb=14oops");
    expect(await screen.findByRole("checkbox", { name: /Internal Docs/ })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: /HR/ })).not.toBeChecked();
  });

  it("links KB detail to chat with that KB selected", async () => {
    mocks.current = workspace;
    mocks.listKnowledgeBases.mockResolvedValue([kb]);
    page(<Routes><Route path="/knowledge-bases/:id" element={<KnowledgeBaseDetailPage />} /></Routes>, "/knowledge-bases/13");
    expect(await screen.findByRole("link", { name: "Bu kaynaklarla chat" })).toHaveAttribute("href", "/chat?kb=13");
  });
});
