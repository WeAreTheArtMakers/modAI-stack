import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LoginPage } from "./pages/LoginPage";
import { SourceCard } from "./pages/ChatPage";
import { UploadDropzone } from "./components/UploadDropzone";
import { connectIndexing, streamRag } from "./api/websocket";
import { ModelsPage } from "./pages/ModelsPage";
import type { ModelSystemStatus, Source, UserContext } from "./types";

const mocks = vi.hoisted(() => ({ login: vi.fn(), uploadDocuments: vi.fn(), user: null as UserContext | null, getModelStatus: vi.fn(), listManagedModels: vi.fn(), deleteManagedModel: vi.fn(), streamModelPull: vi.fn() }));
vi.mock("./auth/AuthContext", () => ({ useAuth: () => ({ user: mocks.user, loading: false, error: null, login: mocks.login, logout: vi.fn() }) }));
vi.mock("./api/documents", () => ({ uploadDocuments: mocks.uploadDocuments, reindexDocument: vi.fn(), deleteDocument: vi.fn() }));
vi.mock("./api/models", () => ({ getModelStatus: mocks.getModelStatus, listManagedModels: mocks.listManagedModels, deleteManagedModel: mocks.deleteManagedModel }));
vi.mock("./api/websocket", async (importOriginal) => ({ ...(await importOriginal<typeof import("./api/websocket")>()), streamModelPull: mocks.streamModelPull }));

const modelStatus: ModelSystemStatus = { providers: [{ provider: "ollama", endpoint: "http://localhost:11434", ready: true }], generation: { provider: "ollama", configured_model: "llama3.2:3b", ready: true, running: true }, embedding: { configured_model: "sentence-transformers/all-MiniLM-L6-v2", source: "huggingface_cache", download_allowed: false, cache_available: false, ready: false, status: "unavailable" } };
const admin: UserContext = { id: 1, email: "admin@example.com", role: "admin", organizations: [], workspaces: [] };
const member: UserContext = { ...admin, id: 2, email: "member@example.com", role: "user", organizations: [{ id: 1, name: "Tenant", slug: "tenant", membership_role: "admin" }], workspaces: [{ id: 1, organization_id: 1, name: "Workspace", slug: "workspace", membership_role: "admin" }] };
function renderModels() { const client = new QueryClient({ defaultOptions: { queries: { retry: false } } }); return render(<QueryClientProvider client={client}><ModelsPage /></QueryClientProvider>); }

describe("Web Console critical UI", () => {
  beforeEach(() => { vi.clearAllMocks(); mocks.user = null; });

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
    const onEvent = vi.fn(); const stop = connectIndexing(8, onEvent, vi.fn());
    const socket = FakeWebSocket.instances[0];
    expect(socket.url).toContain("/ws/indexing?workspace_id=8");
    socket.onmessage?.(new MessageEvent("message", { data: JSON.stringify({ type: "index_progress", workspace_id: 8, document_id: 2, status: "ready", stage: "ready" }) }));
    expect(onEvent).toHaveBeenCalledWith(expect.objectContaining({ workspace_id: 8, status: "ready" }));
    stop();
    vi.unstubAllGlobals();
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
    const promise = streamRag([4], "test", vi.fn());
    RagWebSocket.instances[0].onopen?.();
    RagWebSocket.instances[0].onclose?.();
    await expect(promise).rejects.toThrow("beklenmedik şekilde kapandı");
    vi.unstubAllGlobals();
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
});
