import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LoginPage } from "./pages/LoginPage";
import { SourceCard } from "./pages/ChatPage";
import { UploadDropzone } from "./components/UploadDropzone";
import { connectIndexing, streamRag } from "./api/websocket";
import type { Source } from "./types";

const mocks = vi.hoisted(() => ({ login: vi.fn(), uploadDocuments: vi.fn() }));
vi.mock("./auth/AuthContext", () => ({ useAuth: () => ({ user: null, loading: false, error: null, login: mocks.login, logout: vi.fn() }) }));
vi.mock("./api/documents", () => ({ uploadDocuments: mocks.uploadDocuments, reindexDocument: vi.fn(), deleteDocument: vi.fn() }));

describe("Web Console critical UI", () => {
  beforeEach(() => { vi.clearAllMocks(); });

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
});
