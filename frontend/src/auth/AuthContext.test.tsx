import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AuthProvider, useAuth } from "./AuthContext";
import { WorkspaceProvider, useWorkspace } from "../workspace/WorkspaceContext";

const mocks = vi.hoisted(() => ({ getCurrentUser: vi.fn(), login: vi.fn(), logout: vi.fn(), listWorkspaces: vi.fn() }));
vi.mock("../api/auth", () => ({
  getCurrentUser: mocks.getCurrentUser,
  hasSession: () => false,
  login: mocks.login,
  logout: mocks.logout,
}));
vi.mock("../api/client", () => ({ onAuthFailure: () => () => undefined }));
vi.mock("../api/workspaces", () => ({ listWorkspaces: mocks.listWorkspaces }));

function withClient(children: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 60_000 } } });
  return { client, ...render(<QueryClientProvider client={client}><AuthProvider>{children}</AuthProvider></QueryClientProvider>) };
}

function Probe() {
  const { user, refreshUser } = useAuth();
  return <><span>{user?.organizations[0]?.name ?? "Üyelik yok"}</span><button onClick={() => void refreshUser()}>Kullanıcıyı yenile</button></>;
}

describe("AuthContext", () => {
  it("refreshes authorization-derived user context after a membership change", async () => {
    mocks.getCurrentUser.mockResolvedValue({ id: 1, email: "admin@example.com", role: "admin", organizations: [{ id: 2, name: "WATAM", slug: "watam", membership_role: "admin", organization_admin: true }], workspaces: [{ id: 7, organization_id: 2, name: "Engineering", slug: "engineering", membership_role: "admin" }] });
    withClient(<Probe />);
    expect(screen.getByText("Üyelik yok")).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Kullanıcıyı yenile" }));
    await waitFor(() => expect(screen.getByText("WATAM")).toBeInTheDocument());
  });

  it("drops previous-account workspace data when a different user logs in", async () => {
    const admin = { id: 1, email: "admin@example.com", role: "admin", organizations: [], workspaces: [] };
    const employee = { id: 2, email: "employee@example.com", role: "user", organizations: [], workspaces: [] };
    let activeId = 0;
    mocks.login.mockImplementation(async (email: string) => {
      activeId = email === admin.email ? 1 : 2;
      return activeId === 1 ? admin : employee;
    });
    mocks.listWorkspaces.mockImplementation(async () => [
      { id: 7, organization_id: 3, name: "Engineering", slug: "engineering", membership_role: activeId === 1 ? "admin" : "user" },
      ...(activeId === 1 ? [{ id: 8, organization_id: 4, name: "QA Private", slug: "qa-private", membership_role: "admin" }] : []),
    ]);

    function SwitchProbe() {
      const { user, login, logout } = useAuth();
      return <>
        <button onClick={() => void login(admin.email, "unused")}>Admin girişi</button>
        <button onClick={() => void login(employee.email, "unused")}>Çalışan girişi</button>
        <button onClick={logout}>Çıkış</button>
        <span>{user?.email ?? "Oturum yok"}</span>
        <WorkspaceRole />
      </>;
    }
    function WorkspaceRole() {
      const { current, workspaces } = useWorkspace();
      return <><span>{current?.membership_role ?? "Workspace yok"}</span><span>{workspaces.map((workspace) => workspace.name).join(", ")}</span></>;
    }

    const { client } = withClient(<WorkspaceProvider><SwitchProbe /></WorkspaceProvider>);
    const actor = userEvent.setup();
    await actor.click(screen.getByRole("button", { name: "Admin girişi" }));
    await waitFor(() => expect(screen.getByText("admin", { exact: true })).toBeInTheDocument());
    expect(screen.getByText("Engineering, QA Private")).toBeInTheDocument();
    expect(client.getQueryData(["workspaces", 1])).toBeDefined();

    await actor.click(screen.getByRole("button", { name: "Çalışan girişi" }));
    await waitFor(() => expect(screen.getByText("employee@example.com")).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText("user", { exact: true })).toBeInTheDocument());
    expect(screen.getByText("Engineering")).toBeInTheDocument();
    expect(screen.queryByText("Engineering, QA Private")).not.toBeInTheDocument();
    expect(client.getQueryData(["workspaces", 1])).toBeUndefined();

    await actor.click(screen.getByRole("button", { name: "Çıkış" }));
    await waitFor(() => expect(screen.getByText("Oturum yok")).toBeInTheDocument());
    expect(client.getQueryData(["workspaces", 2])).toBeUndefined();
  });
});
