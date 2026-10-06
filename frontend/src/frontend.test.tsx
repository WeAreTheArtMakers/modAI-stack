import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LoginPage } from "./pages/LoginPage";
import { SourceCard } from "./pages/ChatPage";
import { UploadDropzone } from "./components/UploadDropzone";
import { connectIndexing, streamRag } from "./api/websocket";
import { ModelsPage } from "./pages/ModelsPage";
import { AdminPage } from "./pages/AdminPage";
import { InviteAcceptPage } from "./pages/InviteAcceptPage";
import type { ModelSystemStatus, Source, UserContext } from "./types";
import { pendingInvitation, savePendingInvitation } from "./invitations/transport";
import { ApiError } from "./api/client";

const mocks = vi.hoisted(() => ({ login: vi.fn(), logout: vi.fn(), refreshUser: vi.fn(), uploadDocuments: vi.fn(), user: null as UserContext | null, getModelStatus: vi.fn(), listManagedModels: vi.fn(), deleteManagedModel: vi.fn(), streamModelPull: vi.fn(), listAdminUsers: vi.fn(), updatePlatformRole: vi.fn(), acceptInvitation: vi.fn(), inspectInvitation: vi.fn(), setupInvitedAccount: vi.fn(), listAdminOrganizations: vi.fn(), createAdminOrganization: vi.fn(), listAdminWorkspaces: vi.fn(), listInvitations: vi.fn(), createInvitation: vi.fn() }));
vi.mock("./auth/AuthContext", () => ({ useAuth: () => ({ user: mocks.user, loading: false, error: null, login: mocks.login, logout: mocks.logout, refreshUser: mocks.refreshUser }) }));
vi.mock("./api/documents", () => ({ uploadDocuments: mocks.uploadDocuments, reindexDocument: vi.fn(), deleteDocument: vi.fn() }));
vi.mock("./api/auth", () => ({ inspectInvitation: mocks.inspectInvitation, setupInvitedAccount: mocks.setupInvitedAccount }));
vi.mock("./api/models", () => ({ getModelStatus: mocks.getModelStatus, listManagedModels: mocks.listManagedModels, deleteManagedModel: mocks.deleteManagedModel }));
vi.mock("./api/admin", () => ({ listAdminUsers: mocks.listAdminUsers, updatePlatformRole: mocks.updatePlatformRole, listAdminOrganizations: mocks.listAdminOrganizations, createAdminOrganization: mocks.createAdminOrganization, listAdminWorkspaces: mocks.listAdminWorkspaces, createAdminWorkspace: vi.fn(), listMemberships: vi.fn(), createMembership: vi.fn(), updateMembership: vi.fn(), removeMembership: vi.fn(), listInvitations: mocks.listInvitations, createInvitation: mocks.createInvitation, revokeInvitation: vi.fn(), acceptInvitation: mocks.acceptInvitation, listAuditEvents: vi.fn(), getPlatformStatus: vi.fn() }));
vi.mock("./api/websocket", async (importOriginal) => ({ ...(await importOriginal<typeof import("./api/websocket")>()), streamModelPull: mocks.streamModelPull }));

const modelStatus: ModelSystemStatus = { providers: [{ provider: "ollama", endpoint: "http://localhost:11434", ready: true }], generation: { provider: "ollama", configured_model: "llama3.2:3b", ready: true, running: true }, embedding: { configured_model: "sentence-transformers/all-MiniLM-L6-v2", source: "huggingface_cache", download_allowed: false, cache_available: false, ready: false, status: "unavailable" } };
const admin: UserContext = { id: 1, email: "admin@example.com", role: "admin", organizations: [], workspaces: [] };
const member: UserContext = { ...admin, id: 2, email: "member@example.com", role: "user", organizations: [{ id: 1, name: "Tenant", slug: "tenant", membership_role: "admin", organization_admin: true }], workspaces: [{ id: 1, organization_id: 1, name: "Workspace", slug: "workspace", membership_role: "admin" }] };
function renderModels() { const client = new QueryClient({ defaultOptions: { queries: { retry: false } } }); return render(<QueryClientProvider client={client}><ModelsPage /></QueryClientProvider>); }
function renderAdmin(section: "users" | "organizations" | "workspaces" | "memberships" | "invitations" | "audit" | "platform") { const client = new QueryClient({ defaultOptions: { queries: { retry: false } } }); return render(<QueryClientProvider client={client}><AdminPage section={section} /></QueryClientProvider>); }

describe("Web Console critical UI", () => {
  beforeEach(() => { vi.clearAllMocks(); mocks.user = null; mocks.refreshUser.mockResolvedValue(undefined); sessionStorage.clear(); window.history.replaceState(null, "", "/"); });

  it("renders and submits the login form", async () => {
    mocks.login.mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(<MemoryRouter><LoginPage /></MemoryRouter>);
    await user.type(screen.getByLabelText("E-posta"), "person@example.com");
    await user.type(screen.getByLabelText("Şifre"), "correct-password");
    await user.click(screen.getByRole("button", { name: /console'a gir/i }));
    await waitFor(() => expect(mocks.login).toHaveBeenCalledWith("person@example.com", "correct-password"));
  });

  it("uploads selected documents through the batch UI", async () => {
    mocks.uploadDocuments.mockResolvedValue([]);
    const user = userEvent.setup();
    render(<UploadDropzone knowledgeBaseId={4} onUploaded={vi.fn()} />);
    const input = document.querySelector("input[type=file]") as HTMLInputElement;
    const file = new File(["hello"], "handbook.txt", { type: "text/plain" });
    await user.upload(input, file);
    await waitFor(() => expect(mocks.uploadDocuments).toHaveBeenCalledWith([file], 4));
  });

  it("renders source evidence separately with expandable excerpt", async () => {
    const excerpt = "Güvenlik politikası özeti.";
    const source: Source = { document: "handbook.pdf", document_id: 12, chunk_index: 3, score: 0.9123, text: excerpt };
    const user = userEvent.setup();
    render(<SourceCard source={source} />);
    expect(screen.getByText("handbook.pdf")).toBeInTheDocument();
    expect(screen.queryByText(excerpt)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /alıntıyı gör/i }));
    expect(screen.getByText(excerpt)).toBeInTheDocument();
  });

  it("handles workspace-scoped indexing events", () => {
    class FakeWebSocket {
      static instances: FakeWebSocket[] = [];
      onopen: (() => void) | null = null;
      onmessage: ((event: MessageEvent<string>) => void) | null = null;
      onclose: (() => void) | null = null;
      onerror: (() => void) | null = null;
      url: string;
      constructor(url: string) { this.url = url; FakeWebSocket.instances.push(this); }
      close() { this.onclose?.(); }
    }
    vi.stubGlobal("WebSocket", FakeWebSocket);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ ticket: "short-lived-ticket" }), { status: 200 })));
    const onEvent = vi.fn(); const stop = connectIndexing(8, onEvent, vi.fn());
    return waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1)).then(() => {
      const socket = FakeWebSocket.instances[0];
      expect(socket.url).toContain("/ws/indexing?ticket=short-lived-ticket");
      socket.onmessage?.(new MessageEvent("message", { data: JSON.stringify({ type: "index_progress", workspace_id: 8, document_id: 2, status: "ready", stage: "ready" }) }));
      expect(onEvent).toHaveBeenCalledWith(expect.objectContaining({ workspace_id: 8, status: "ready" }));
      stop();
      vi.unstubAllGlobals();
    });
  });

  it("reports an unexpected RAG WebSocket close instead of resolving as success", async () => {
    class RagWebSocket {
      static instances: RagWebSocket[] = [];
      onopen: (() => void) | null = null;
      onmessage: ((event: MessageEvent<string>) => void) | null = null;
      onclose: (() => void) | null = null;
      onerror: (() => void) | null = null;
      constructor() { RagWebSocket.instances.push(this); }
      send() {}
      close() {}
    }
    vi.stubGlobal("WebSocket", RagWebSocket);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ ticket: "short-lived-ticket" }), { status: 200 })));
    const promise = streamRag([4], "test", vi.fn());
    await waitFor(() => expect(RagWebSocket.instances).toHaveLength(1));
    RagWebSocket.instances[0].onopen?.();
    RagWebSocket.instances[0].onclose?.();
    await expect(promise).rejects.toThrow("beklenmedik şekilde kapandı");
    vi.unstubAllGlobals();
  });

  it("aborts an in-flight RAG WebSocket and rejects with AbortError", async () => {
    class RagWebSocket {
      static instances: RagWebSocket[] = [];
      onopen: (() => void) | null = null;
      onmessage: ((event: MessageEvent<string>) => void) | null = null;
      onclose: (() => void) | null = null;
      onerror: (() => void) | null = null;
      closed = false;

      constructor() {
        RagWebSocket.instances.push(this);
      }

      send() {}

      close() {
        this.closed = true;
        this.onclose?.();
      }
    }

    vi.stubGlobal("WebSocket", RagWebSocket);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            ticket: "short-lived-ticket",
          }),
          { status: 200 },
        ),
      ),
    );

    try {
      const controller = new AbortController();

      const promise = streamRag(
        [4],
        "test",
        vi.fn(),
        controller.signal,
      );

      await waitFor(() =>
        expect(
          RagWebSocket.instances,
        ).toHaveLength(1),
      );

      const socket =
        RagWebSocket.instances[0];

      socket.onopen?.();

      const rejection = expect(
        promise,
      ).rejects.toMatchObject({
        name: "AbortError",
        message: "RAG isteği iptal edildi.",
      });

      controller.abort();

      await rejection;

      expect(socket.closed).toBe(true);
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("shows provider-offline and embedding-unavailable states to regular users", async () => {
    mocks.user = member;
    mocks.getModelStatus.mockResolvedValue({ ...modelStatus, providers: [{ ...modelStatus.providers[0], ready: false }], generation: { ...modelStatus.generation, ready: false, running: false } });
    mocks.listManagedModels.mockResolvedValue([{ provider: "ollama", name: "llama3.2:3b", size: 1024, modified_at: null, family: "llama", parameter_size: null, quantization: null, context_length: null, capabilities: null }]);
    renderModels();
    expect(await screen.findByText("Yerel modeller")).toBeInTheDocument();
    expect(screen.getByText(/Model çekme ve silme yalnızca/)).toBeInTheDocument();
    expect(screen.getAllByText("llama3.2:3b")).toHaveLength(2);
    expect(screen.queryByRole("button", { name: "Sil" })).not.toBeInTheDocument();
    expect(screen.getByText(/Model önbellekte bulunmuyor/)).toBeInTheDocument();
  });

  it("lets admins view pull progress and explicitly confirm deletion", async () => {
    mocks.user = admin;
    mocks.getModelStatus.mockResolvedValue(modelStatus);
    mocks.listManagedModels.mockResolvedValue([{ provider: "ollama", name: "qwen2.5:7b", size: 1024, modified_at: null, family: "qwen", parameter_size: null, quantization: null, context_length: null, capabilities: null }]);
    let finishPull: (() => void) | undefined;
    mocks.streamModelPull.mockImplementation((_model: string, onEvent: (event: { type: "model_pull_progress"; model: string; status: string; completed: number; total: number }) => void) => { onEvent({ type: "model_pull_progress", model: "new-model:latest", status: "downloading", completed: 50, total: 100 }); return new Promise<void>((resolve) => { finishPull = resolve; }); });
    const user = userEvent.setup();
    renderModels();
    await screen.findByText("qwen2.5:7b");
    await user.type(screen.getByLabelText("Ollama modeli çek"), "new-model:latest");
    await user.click(screen.getByRole("button", { name: "Modeli çek" }));
    expect(await screen.findByText("downloading")).toBeInTheDocument();
    expect(screen.getByText(/50%/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Sil" }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("Model silinsin mi?")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Vazgeç" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await act(async () => { finishPull?.(); });
  });

  it("keeps platform user management out of tenant administrator views", async () => {
    mocks.user = member;
    renderAdmin("users");
    expect(screen.getByText("Platform yetkisi gerekli")).toBeInTheDocument();
    expect(mocks.listAdminUsers).not.toHaveBeenCalled();
  });

  it("lets a platform admin review users and change only platform roles", async () => {
    mocks.user = admin;
    mocks.listAdminUsers.mockResolvedValue([{ id: 8, email: "person@example.com", role: "user", created_at: null }]);
    mocks.updatePlatformRole.mockResolvedValue({ id: 8, email: "person@example.com", role: "admin", created_at: null });
    const user = userEvent.setup();
    renderAdmin("users");
    await screen.findByText("person@example.com");
    await user.selectOptions(screen.getByLabelText("person@example.com platform rolü"), "admin");
    await waitFor(() => expect(mocks.updatePlatformRole).toHaveBeenCalledWith(8, "admin"));
  });

  it("lets only a platform admin seed the first organization", async () => {
    mocks.user = admin;
    mocks.listAdminOrganizations.mockResolvedValue([]);
    mocks.createAdminOrganization.mockResolvedValue({ id: 1, name: "Company", slug: "company", workspace_count: 0, member_count: 0, knowledge_base_count: 0, document_count: 0 });
    const user = userEvent.setup();
    renderAdmin("organizations");
    await user.click(await screen.findByRole("button", { name: "Yeni organization" }));
    await user.type(screen.getByLabelText("Organization adı"), "Company");
    await user.type(screen.getByLabelText("Organization slug"), "company");
    await user.click(screen.getByRole("button", { name: "Oluştur" }));
    await waitFor(() => expect(mocks.createAdminOrganization).toHaveBeenCalledWith({ name: "Company", slug: "company" }));
  });

  it("shows an existing-account invitation and accepts only through the signed-in matching account", async () => {
    mocks.user = member;
    mocks.inspectInvitation.mockResolvedValue({ status: "pending", email: "member@example.com", organization_name: "Tenant", workspace_name: "Workspace", role: "user", expires_at: "2030-01-01T00:00:00Z", account_exists: true });
    mocks.acceptInvitation.mockResolvedValue({ id: 1, email: "member@example.com" });
    const user = userEvent.setup();
    window.history.replaceState(null, "", "/invite/accept#token=single-use-token-that-is-long-enough");
    render(<BrowserRouter><QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><InviteAcceptPage /></QueryClientProvider></BrowserRouter>);
    expect(window.location.hash).toBe("");
    expect(window.location.search).toBe("");
    await user.click(await screen.findByRole("button", { name: "Daveti kabul et" }));
    await waitFor(() => expect(mocks.acceptInvitation).toHaveBeenCalledWith("single-use-token-that-is-long-enough"));
    expect(await screen.findByText(/Davet kabul edildi/)).toBeInTheDocument();
    expect(mocks.refreshUser).toHaveBeenCalled();
  });

  it("lets a new invited employee choose and confirm a password without login", async () => {
    mocks.inspectInvitation.mockResolvedValue({ status: "pending", email: "new@example.com", organization_name: "Company", workspace_name: "Engineering", role: "manager", expires_at: "2030-01-01T00:00:00Z", account_exists: false });
    mocks.setupInvitedAccount.mockResolvedValue({ email: "new@example.com" });
    const user = userEvent.setup();
    render(<MemoryRouter initialEntries={["/invite/accept#token=single-use-token-that-is-long-enough"]}><QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><InviteAcceptPage /></QueryClientProvider></MemoryRouter>);
    expect(await screen.findByText("Company")).toBeInTheDocument();
    expect(screen.getByText("Engineering")).toBeInTheDocument();
    savePendingInvitation("single-use-token-that-is-long-enough");
    await user.type(screen.getByLabelText("Yeni şifre"), "employee-chosen-password");
    await user.type(screen.getByLabelText("Şifreyi doğrula"), "employee-chosen-password");
    await user.click(screen.getByRole("button", { name: "Hesap oluştur ve katıl" }));
    await waitFor(() => expect(mocks.setupInvitedAccount).toHaveBeenCalledWith("single-use-token-that-is-long-enough", "employee-chosen-password"));
    await waitFor(() => expect(pendingInvitation()).toBeNull());
  });

  it("keeps an existing-account invite only in sessionStorage during login and clears it after acceptance", async () => {
    const token = "single-use-token-that-is-long-enough";
    mocks.inspectInvitation.mockResolvedValue({ status: "pending", email: "member@example.com", organization_name: "Tenant", workspace_name: null, role: "user", expires_at: "2030-01-01T00:00:00Z", account_exists: true });
    mocks.login.mockImplementation(async () => { mocks.user = member; });
    mocks.acceptInvitation.mockResolvedValue({ id: 1, email: "member@example.com" });
    window.history.replaceState(null, "", `/invite/accept#token=${token}`);
    const user = userEvent.setup();
    render(<MemoryRouter initialEntries={[`/invite/accept#token=${token}`]}><QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><Routes><Route path="/invite/accept" element={<InviteAcceptPage />} /><Route path="/login" element={<LoginPage />} /></Routes></QueryClientProvider></MemoryRouter>);
    await user.click(await screen.findByRole("link", { name: "Giriş yap" }));
    expect(pendingInvitation()).toBe(token);
    expect(window.location.hash).toBe("");
    expect(window.location.search).toBe("");
    const localValues = Array.from({ length: localStorage.length }, (_, index) => localStorage.getItem(localStorage.key(index) ?? ""));
    expect(localValues.join("")).not.toContain(token);
    await user.type(screen.getByLabelText("E-posta"), "member@example.com");
    await user.type(screen.getByLabelText("Şifre"), "account-password");
    await user.click(screen.getByRole("button", { name: /console'a gir/i }));
    await user.click(await screen.findByRole("button", { name: "Daveti kabul et" }));
    await waitFor(() => expect(mocks.acceptInvitation).toHaveBeenCalledWith(token));
    await waitFor(() => expect(pendingInvitation()).toBeNull());
  });

  it("clears an invalid or revoked pending invitation without replaying its token", async () => {
    const token = "single-use-token-that-is-long-enough";
    savePendingInvitation(token);
    mocks.inspectInvitation.mockRejectedValue(new ApiError(404, "Invitation is invalid"));
    render(<MemoryRouter initialEntries={["/invite/accept"]}><QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><InviteAcceptPage /></QueryClientProvider></MemoryRouter>);
    expect(await screen.findByText(/Davet geçersiz veya iptal edilmiş/)).toBeInTheDocument();
    await waitFor(() => expect(pendingInvitation()).toBeNull());
  });

  it("does not accept legacy query-string invitation credentials", () => {
    const token = "single-use-token-that-is-long-enough";
    window.history.replaceState(null, "", `/invite/accept?token=${token}`);
    render(<MemoryRouter initialEntries={[`/invite/accept?token=${token}`]}><QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><InviteAcceptPage /></QueryClientProvider></MemoryRouter>);
    expect(screen.getByText("Geçerli bir davet bağlantısı gerekli.")).toBeInTheDocument();
    expect(window.location.search).toBe("");
    expect(mocks.inspectInvitation).not.toHaveBeenCalled();
  });

  it("requires an existing session to sign out before creating a different invited account", async () => {
    mocks.user = member;
    mocks.inspectInvitation.mockResolvedValue({ status: "pending", email: "new@example.com", organization_name: "Company", workspace_name: null, role: "user", expires_at: "2030-01-01T00:00:00Z", account_exists: false });
    const user = userEvent.setup();
    render(<MemoryRouter initialEntries={["/invite/accept#token=single-use-token-that-is-long-enough"]}><QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><InviteAcceptPage /></QueryClientProvider></MemoryRouter>);
    await screen.findByText("Company");
    expect(screen.queryByLabelText("Yeni şifre")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Mevcut hesaptan çık" }));
    expect(mocks.logout).toHaveBeenCalledOnce();
    expect(mocks.setupInvitedAccount).not.toHaveBeenCalled();
  });

  it.each(["expired", "accepted"] as const)("shows the %s invitation state without a password form", async (status) => {
    mocks.inspectInvitation.mockResolvedValue({ status, email: "new@example.com", organization_name: "Company", workspace_name: null, role: "user", expires_at: "2020-01-01T00:00:00Z", account_exists: false });
    savePendingInvitation("single-use-token-that-is-long-enough");
    render(<MemoryRouter initialEntries={["/invite/accept"]}><QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><InviteAcceptPage /></QueryClientProvider></MemoryRouter>);
    expect(await screen.findByText(status === "expired" ? /süresi dolmuş/ : /daha önce kabul edilmiş/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Yeni şifre")).not.toBeInTheDocument();
    await waitFor(() => expect(pendingInvitation()).toBeNull());
  });

  it("constructs and copies a scoped one-time invitation link on the admin screen", async () => {
    mocks.user = member;
    mocks.listAdminOrganizations.mockResolvedValue([{ id: 1, name: "Tenant", slug: "tenant", workspace_count: 1, member_count: 1, knowledge_base_count: 0, document_count: 0 }]);
    mocks.listAdminWorkspaces.mockResolvedValue([{ id: 7, organization_id: 1, name: "Engineering", slug: "engineering" }]);
    mocks.listInvitations.mockResolvedValue([]);
    mocks.createInvitation.mockResolvedValue({ id: 9, email: "new@example.com", organization_id: 1, workspace_id: 7, role: "manager", expires_at: "2030-01-01T00:00:00Z", accepted_at: null, created_by_user_id: 2, created_at: null, delivery_token: "only-shown-once" });
    const user = userEvent.setup();
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    renderAdmin("invitations");
    await user.click(await screen.findByRole("button", { name: "Yeni kullanıcı davet et" }));
    await user.type(screen.getByLabelText("Davet e-postası"), "new@example.com");
    await user.selectOptions(screen.getByLabelText("Tenant rolü"), "manager");
    await user.selectOptions(screen.getByLabelText("Davet workspace kapsamı"), "7");
    await user.click(screen.getByRole("button", { name: "Davet bağlantısı oluştur" }));
    await waitFor(() => expect(mocks.createInvitation).toHaveBeenCalledWith({ email: "new@example.com", organization_id: 1, workspace_id: 7, role: "manager" }));
    await user.click(await screen.findByRole("button", { name: "Davet bağlantısını kopyala" }));
    const link = `${window.location.origin}/invite/accept#token=only-shown-once`;
    expect(writeText).toHaveBeenCalledWith(link);
    expect(link).not.toContain("?token=");
  });
});
