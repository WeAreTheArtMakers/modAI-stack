import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AuthProvider, useAuth } from "./AuthContext";

const mocks = vi.hoisted(() => ({ getCurrentUser: vi.fn() }));
vi.mock("../api/auth", () => ({
  getCurrentUser: mocks.getCurrentUser,
  hasSession: () => false,
  login: vi.fn(),
  logout: vi.fn(),
}));
vi.mock("../api/client", () => ({ onAuthFailure: () => () => undefined }));

function Probe() {
  const { user, refreshUser } = useAuth();
  return <><span>{user?.organizations[0]?.name ?? "Üyelik yok"}</span><button onClick={() => void refreshUser()}>Kullanıcıyı yenile</button></>;
}

describe("AuthContext", () => {
  it("refreshes authorization-derived user context after a membership change", async () => {
    mocks.getCurrentUser.mockResolvedValue({ id: 1, email: "admin@example.com", role: "admin", organizations: [{ id: 2, name: "WATAM", slug: "watam", membership_role: "admin", organization_admin: true }], workspaces: [{ id: 7, organization_id: 2, name: "Engineering", slug: "engineering", membership_role: "admin" }] });
    render(<AuthProvider><Probe /></AuthProvider>);
    expect(screen.getByText("Üyelik yok")).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Kullanıcıyı yenile" }));
    await waitFor(() => expect(screen.getByText("WATAM")).toBeInTheDocument());
  });
});
