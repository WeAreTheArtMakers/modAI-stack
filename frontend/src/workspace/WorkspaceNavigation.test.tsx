import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AppShell from "../components/AppShell";
import { ThemeProvider } from "../theme/ThemeProvider";
import { AdminPage } from "../pages/AdminPage";
import type { UserContext } from "../types";

const mocks = vi.hoisted(() => ({
  user: null as UserContext | null,
  refreshUser: vi.fn(),
  listWorkspaces: vi.fn(),
  listAdminOrganizations: vi.fn(), listMemberships: vi.fn(), createMembership: vi.fn(),
}));
vi.mock("../auth/AuthContext", () => ({ useAuth: () => ({ user: mocks.user, refreshUser: mocks.refreshUser, logout: vi.fn() }) }));
vi.mock("../api/workspaces", () => ({ listWorkspaces: mocks.listWorkspaces }));
vi.mock("../api/admin", () => ({ listAdminOrganizations: mocks.listAdminOrganizations, listMemberships: mocks.listMemberships, createMembership: mocks.createMembership, updateMembership: vi.fn(), removeMembership: vi.fn() }));
vi.mock("../api/websocket", () => ({ connectIndexing: () => vi.fn() }));

function renderShell(route = "/") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<ThemeProvider><QueryClientProvider client={client}><MemoryRouter initialEntries={[route]}><Routes><Route element={<AppShell />}><Route path="/" element={<p>Dashboard</p>} /><Route path="/admin/memberships" element={<AdminPage section="memberships" />} /></Route></Routes></MemoryRouter></QueryClientProvider></ThemeProvider>);
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  mocks.refreshUser.mockResolvedValue(undefined);
  mocks.listWorkspaces.mockResolvedValue([]);
  mocks.listAdminOrganizations.mockResolvedValue([{ id: 2, name: "WATAM", slug: "watam" }]);
  mocks.listMemberships.mockResolvedValue([]);
});

describe("workspace navigation", () => {
  it("does not render a blank picker and gives the platform admin setup links", async () => {
    mocks.user = { id: 1, email: "admin@example.com", role: "admin", organizations: [], workspaces: [] };
    renderShell();
    expect(await screen.findByText("Henüz erişilebilir Workspace yok.")).toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "Workspace seç" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Üyeliklere git" })).toHaveAttribute("href", "/admin/memberships");
  });

  it("explains missing access to a normal user without admin actions", async () => {
    mocks.user = { id: 3, email: "employee@example.com", role: "user", organizations: [], workspaces: [] };
    renderShell();
    expect(await screen.findByText(/Erişim için Organization yöneticinizle iletişime geçin/)).toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "Workspace seç" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Üyeliklere git" })).not.toBeInTheDocument();
  });

  it("populates the picker without relogin after explicit self-membership", async () => {
    mocks.user = { id: 1, email: "admin@example.com", role: "admin", organizations: [], workspaces: [] };
    let member = false;
    mocks.listWorkspaces.mockImplementation(async () => member ? [{ id: 7, organization_id: 2, name: "Engineering", slug: "engineering", membership_role: "admin" }] : []);
    mocks.createMembership.mockImplementation(async () => { member = true; return { id: 5 }; });
    renderShell("/admin/memberships");
    expect(await screen.findByText("Henüz erişilebilir Workspace yok.")).toBeInTheDocument();
    await userEvent.setup().click(await screen.findByRole("button", { name: "Kendimi Organization Admin yap" }));
    await waitFor(() => expect(screen.getByRole("combobox", { name: "Workspace seç" })).toHaveValue("7"));
    expect(mocks.listWorkspaces.mock.calls.length).toBeGreaterThan(1);
    expect(mocks.refreshUser).toHaveBeenCalled();
  });
});
