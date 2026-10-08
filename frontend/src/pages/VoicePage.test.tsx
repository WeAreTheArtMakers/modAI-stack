import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { VoicePage } from "./VoicePage";
import { MicrophoneError, MICROPHONE_MESSAGES } from "../voice/microphone";
import type { VoiceDependencies } from "../voice/useVoiceAssistant";
import type { LoadState } from "../voice/voiceEngine";
import type { RagEvent, Source } from "../types";

const mocks = vi.hoisted(() => ({
  listKnowledgeBases: vi.fn(),
  current: { id: 3, name: "Destek", slug: "destek", organization_id: 2, membership_role: "user" } as Record<string, unknown> | null,
}));
vi.mock("../auth/AuthContext", () => ({ useAuth: () => ({ user: { email: "user@example.com", role: "user", organizations: [] } }) }));
vi.mock("../workspace/WorkspaceContext", () => ({ useWorkspace: () => ({ current: mocks.current, workspaces: [], loading: false, setCurrentId: vi.fn() }) }));
vi.mock("../api/knowledgeBases", () => ({ listKnowledgeBases: mocks.listKnowledgeBases }));

const QUESTION = "Yıllık izin politikası nedir?";
const SOURCE: Source = { document: "izin-politikasi.pdf", score: 0.82, document_id: 41, chunk_index: 2, text: "Başvurular 15 gün önce yapılır." };
const TOKENS = ["Güncel izin politikasına göre ", "başvurular 15 gün önce yapılmalıdır. ", "İlgili belgeyi gösterebilirim."];
const kb = { id: 7, workspace_id: 3, name: "İK Politikaları", slug: "ik", description: null, membership_role: "user" };

type Fakes = ReturnType<typeof createFakes>;

function createFakes() {
  const recorder = {
    recording: false,
    start: vi.fn(async () => { recorder.recording = true; }),
    stop: vi.fn(async () => { recorder.recording = false; return new Float32Array(16_000); }),
    cancel: vi.fn(() => { recorder.recording = false; }),
    level: () => 0.4,
  };
  const player = {
    generation: 0,
    unlock: vi.fn(),
    enqueue: vi.fn((_samples: Float32Array, _rate: number, generation: number) => (generation === player.generation ? performance.timeOrigin + performance.now() : null)),
    reset: vi.fn((generation: number) => { player.generation = generation; }),
    drained: vi.fn(async () => undefined),
    level: () => 0.5,
    dispose: vi.fn(),
  };
  const engine = {
    load: vi.fn((_component: "stt" | "tts", onState: (state: LoadState) => void) => {
      onState({ status: "ready", loaded: 1, total: 1, backend: "wasm" });
      return Promise.resolve("wasm" as const);
    }),
    transcribe: vi.fn(async () => ({ text: QUESTION, ms: 140 })),
    speak: vi.fn((_id: number, _seq: number, _text: string, onAudio: (samples: Float32Array, rate: number) => void) => {
      onAudio(new Float32Array(480), 48_000);
      return Promise.resolve();
    }),
    cancel: vi.fn(),
    dispose: vi.fn(),
  };
  const systemVoice = {
    available: vi.fn(() => true),
    voiceName: () => "Yelda",
    speak: vi.fn(async (_text: string, onStart: () => void) => { onStart(); }),
    cancel: vi.fn(),
  };
  const streamRag = vi.fn(async (_kbs: number[], _question: string, onEvent: (event: RagEvent) => void) => {
    onEvent({ type: "sources", data: [SOURCE] });
    for (const token of TOKENS) onEvent({ type: "token", data: token });
    onEvent({ type: "complete" });
  });
  return { recorder, player, engine, systemVoice, streamRag };
}

function renderVoice(fakes: Fakes) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><MemoryRouter><VoicePage dependencies={fakes as unknown as VoiceDependencies} /></MemoryRouter></QueryClientProvider>);
}

async function talkButton() {
  return screen.findByRole("button", { name: "Konuşmaya başla" });
}

const phase = () => screen.getByRole("img", { name: /modAI asistanı/ }).getAttribute("data-phase");

async function askBySpeaking() {
  fireEvent.pointerDown(await talkButton());
  fireEvent.pointerUp(screen.getByRole("button", { name: "Kaydı bitir" })); // a tap keeps recording
  expect(screen.getByRole("status")).toHaveTextContent("Mikrofon kaydediyor");
  fireEvent.pointerDown(screen.getByRole("button", { name: "Kaydı bitir" }));
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.current = { id: 3, name: "Destek", slug: "destek", organization_id: 2, membership_role: "user" };
  mocks.listKnowledgeBases.mockResolvedValue([kb]);
  window.localStorage.clear();
});

describe("modAI Voice", () => {
  it("records, transcribes locally, sends only text and speaks the cited answer sentence by sentence", async () => {
    const fakes = createFakes();
    renderVoice(fakes);
    fireEvent.click(await screen.findByRole("button", { name: /Modelleri hazırla/ }));
    await askBySpeaking();

    await waitFor(() => expect(fakes.streamRag).toHaveBeenCalledTimes(1));
    expect(fakes.recorder.start).toHaveBeenCalledTimes(1);
    expect(fakes.engine.transcribe).toHaveBeenCalledWith(expect.any(Float32Array));
    expect(fakes.streamRag).toHaveBeenCalledWith([7], QUESTION, expect.any(Function), expect.any(AbortSignal), expect.objectContaining({ onSent: expect.any(Function) }));
    // Raw audio goes to the local engine only; RAG receives plain text.
    expect(fakes.streamRag.mock.calls[0].some((argument) => argument instanceof Float32Array)).toBe(false);

    expect(await screen.findByText("Tanınan konuşma")).toBeInTheDocument();
    expect(screen.getByText(QUESTION)).toBeInTheDocument();
    expect(await screen.findByText(TOKENS.join(""))).toBeInTheDocument();
    expect(within(screen.getByTestId("voice-sources")).getByText("izin-politikasi.pdf")).toBeInTheDocument();
    expect(fakes.engine.speak.mock.calls.map(([id, seq, text]) => [id, seq, text])).toEqual([
      [1, 0, "Güncel izin politikasına göre başvurular 15 gün önce yapılmalıdır."],
      [1, 1, "İlgili belgeyi gösterebilirim."],
    ]);
    expect(fakes.player.enqueue).toHaveBeenCalledWith(expect.any(Float32Array), 48_000, 1);
    await waitFor(() => expect(phase()).toBe("idle"));
    expect(screen.getByTestId("turn-metrics")).toHaveTextContent(/yazıya çevirme .* sn · ilk kelime .* sn · ilk ses .* sn · tamamı .* sn/);
    expect(fakes.recorder.recording).toBe(false);
  });

  it("supports press-and-hold: releasing after a hold ends the recording", async () => {
    const fakes = createFakes();
    renderVoice(fakes);
    let now = 1_000;
    const clock = vi.spyOn(performance, "now").mockImplementation(() => now);
    fireEvent.pointerDown(await talkButton());
    await waitFor(() => expect(phase()).toBe("listening"));
    now += 900;
    fireEvent.pointerUp(screen.getByRole("button", { name: "Kaydı bitir" }));
    await waitFor(() => expect(fakes.streamRag).toHaveBeenCalledTimes(1));
    expect(fakes.recorder.stop).toHaveBeenCalledTimes(1);
    clock.mockRestore();
  });

  it("explains a denied microphone permission and sends nothing", async () => {
    const fakes = createFakes();
    fakes.recorder.start.mockRejectedValueOnce(new MicrophoneError("permission_denied", MICROPHONE_MESSAGES.permission_denied));
    renderVoice(fakes);
    fireEvent.pointerDown(await talkButton());
    expect(await screen.findByRole("alert")).toHaveTextContent("Mikrofon izni verilmedi");
    expect(phase()).toBe("error");
    expect(fakes.streamRag).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Uyarıyı kapat" }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("reports transcription failures and empty transcripts without querying RAG", async () => {
    const fakes = createFakes();
    fakes.engine.transcribe.mockRejectedValueOnce(new Error("model missing")).mockResolvedValueOnce({ text: "", ms: 90 });
    renderVoice(fakes);
    await askBySpeaking();
    expect(await screen.findByRole("alert")).toHaveTextContent("Konuşma yazıya çevrilemedi: model missing");
    await askBySpeaking();
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Konuşma anlaşılamadı"));
    expect(fakes.streamRag).not.toHaveBeenCalled();
  });

  it("stops speech and generation, and never plays stale audio afterwards", async () => {
    const fakes = createFakes();
    let lateAudio: ((samples: Float32Array, rate: number) => void) | null = null;
    fakes.engine.speak.mockImplementationOnce((_id, _seq, _text, onAudio) => {
      onAudio(new Float32Array(480), 48_000);
      lateAudio = onAudio;
      return new Promise(() => undefined); // still synthesizing
    });
    let signal: AbortSignal | undefined;
    fakes.streamRag.mockImplementationOnce(async (_kbs, _question, onEvent, abort?: AbortSignal) => {
      signal = abort;
      onEvent({ type: "token", data: "İlk cümle burada bitiyor. " });
      onEvent({ type: "token", data: "İkinci" });
      await new Promise((_resolve, reject) => abort?.addEventListener("abort", () => reject(new Error("aborted"))));
    });
    renderVoice(fakes);
    await askBySpeaking();
    await waitFor(() => expect(phase()).toBe("speaking"));

    fireEvent.click(screen.getByRole("button", { name: "Durdur" }));
    expect(fakes.engine.cancel).toHaveBeenCalledWith(1);
    expect(fakes.player.reset).toHaveBeenLastCalledWith(-1);
    expect(signal?.aborted).toBe(true);
    await waitFor(() => expect(phase()).toBe("idle"));
    expect(await screen.findByText("Durduruldu")).toBeInTheDocument();

    const enqueued = fakes.player.enqueue.mock.calls.length;
    act(() => lateAudio?.(new Float32Array(480), 48_000));
    expect(fakes.player.enqueue.mock.results.at(-1)?.value).toBeNull(); // generation 1 is gone
    expect(fakes.player.enqueue).toHaveBeenCalledTimes(enqueued + 1);
    expect(phase()).toBe("idle");
    expect(fakes.recorder.recording).toBe(false); // the microphone stayed off during playback
  });

  it("supersedes an unfinished answer when a new question is asked", async () => {
    const fakes = createFakes();
    fakes.streamRag.mockImplementationOnce(async (_kbs, _question, onEvent, abort?: AbortSignal) => {
      onEvent({ type: "token", data: "Eski yanıt" });
      await new Promise((_resolve, reject) => abort?.addEventListener("abort", () => reject(new Error("aborted"))));
    });
    renderVoice(fakes);
    fireEvent.change(await screen.findByLabelText("Yazılı soru"), { target: { value: "İlk soru" } });
    fireEvent.click(screen.getByRole("button", { name: "Gönder" }));
    await screen.findByText("Eski yanıt");
    fireEvent.change(screen.getByLabelText("Yazılı soru"), { target: { value: "İkinci soru" } });
    fireEvent.click(screen.getByRole("button", { name: "Gönder" }));
    await waitFor(() => expect(fakes.streamRag).toHaveBeenCalledTimes(2));
    expect(fakes.engine.cancel).toHaveBeenCalledWith(1);
    expect(fakes.player.reset).toHaveBeenCalledWith(2);
    await waitFor(() => expect(fakes.engine.speak.mock.calls.every(([id]) => id === 2)).toBe(true));
    expect(screen.getAllByText("Yazılı soru")).toHaveLength(2);
  });

  it("falls back to a labeled Turkish system voice when neural TTS cannot load", async () => {
    const fakes = createFakes();
    fakes.engine.load.mockImplementation((component, onState) => {
      if (component === "tts") {
        onState({ status: "error", loaded: 0, total: 1, message: "no backend" });
        return Promise.reject(new Error("no backend"));
      }
      onState({ status: "ready", loaded: 1, total: 1, backend: "wasm" });
      return Promise.resolve("wasm");
    });
    renderVoice(fakes);
    fireEvent.click(await screen.findByRole("button", { name: /Modelleri hazırla/ }));
    await waitFor(() => expect(screen.getByTestId("speech-engine")).toHaveTextContent("Sistem sesi (yedek) · Yelda"));
    await askBySpeaking();
    await waitFor(() => expect(fakes.systemVoice.speak).toHaveBeenCalledTimes(2));
    expect(fakes.systemVoice.speak.mock.calls.map(([text]) => text)).toEqual([
      "Güncel izin politikasına göre başvurular 15 gün önce yapılmalıdır.",
      "İlgili belgeyi gösterebilirim.",
    ]);
    expect(fakes.engine.speak).not.toHaveBeenCalled();
  });

  it("keeps answering in text when no voice is available or speech is muted", async () => {
    const fakes = createFakes();
    fakes.systemVoice.available.mockReturnValue(false);
    fakes.engine.load.mockImplementation((component, onState) => {
      onState(component === "tts" ? { status: "error", loaded: 0, total: 1 } : { status: "ready", loaded: 1, total: 1 });
      return component === "tts" ? Promise.reject(new Error("unsupported")) : Promise.resolve("wasm");
    });
    renderVoice(fakes);
    fireEvent.click(await screen.findByRole("button", { name: /Modelleri hazırla/ }));
    await waitFor(() => expect(screen.getByTestId("speech-engine")).toHaveTextContent("Sesli yanıt kullanılamıyor"));
    fireEvent.click(screen.getByRole("button", { name: "Sesli yanıtı kapat" }));
    await askBySpeaking();
    expect(await screen.findByText(TOKENS.join(""))).toBeInTheDocument();
    expect(fakes.systemVoice.speak).not.toHaveBeenCalled();
    expect(fakes.engine.speak).not.toHaveBeenCalled();
  });

  it("requires an authorized Knowledge Base before listening", async () => {
    mocks.listKnowledgeBases.mockResolvedValue([kb, { ...kb, id: 8, name: "Finans" }, { ...kb, id: 99, name: "Başka workspace", workspace_id: 99 }]);
    const fakes = createFakes();
    renderVoice(fakes);
    expect(await talkButton()).toBeDisabled();
    expect(screen.queryByText("Başka workspace")).not.toBeInTheDocument();
    fireEvent.click(screen.getByLabelText(/Finans/));
    expect(await talkButton()).toBeEnabled();
  });
});
