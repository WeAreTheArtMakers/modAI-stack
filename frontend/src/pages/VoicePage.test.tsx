import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { VoicePage } from "./VoicePage";
import { MicrophoneError, MICROPHONE_MESSAGES } from "../voice/microphone";
import type { VoiceDependencies } from "../voice/useVoiceAssistant";
import type { LoadState } from "../voice/voiceEngine";
import type { AssistantConversationDetail, AssistantConversationSummary, RagEvent, Source } from "../types";

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
    stop: vi.fn(async () => {
      recorder.recording = false;
      return { samples: new Float32Array(16_000), diagnostics: { durationMs: 1000, rms: 0.05, peak: 0.4, clippedPercent: 0, finalizeMs: 30, decodeMs: 12, inputSampleRate: 48_000 } };
    }),
    cancel: vi.fn(() => { recorder.recording = false; }),
    level: () => 0.4,
  };
  const player = {
    generation: 0,
    unlock: vi.fn(),
    enqueue: vi.fn((_samples: Float32Array, _rate: number, generation: number) => (generation === player.generation ? performance.timeOrigin + performance.now() : null)),
    reset: vi.fn((generation: number) => { player.generation = generation; }),
    drained: vi.fn(async () => undefined),
    bufferedSeconds: vi.fn(() => 0),
    level: () => 0.5,
    dispose: vi.fn(),
  };
  const engine = {
    load: vi.fn((_component: "stt" | "tts", onState: (state: LoadState) => void) => {
      onState({ status: "ready", loaded: 1, total: 1, backend: "wasm" });
      return Promise.resolve("wasm" as const);
    }),
    transcribe: vi.fn(async (): Promise<{ text: string; ms: number; postedAt?: number; receivedAt?: number; startedAt?: number; endedAt?: number; warm?: boolean; backend?: "wasm" | "webgpu" }> => ({ text: QUESTION, ms: 140 })),
    speak: vi.fn((_id: number, _seq: number, _text: string, onAudio: (samples: Float32Array, rate: number) => void, _speed?: number) => {
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
  const streamRag = vi.fn(async (_kbs: number[], _question: string, onEvent: (event: RagEvent) => void, _signal?: AbortSignal, _options?: Record<string, unknown>) => {
    onEvent({ type: "sources", data: [SOURCE] });
    for (const token of TOKENS) onEvent({ type: "token", data: token });
    onEvent({ type: "complete" });
  });
  let nextConversation = 50;
  const conversations = {
    list: vi.fn(async (_workspaceId: number) => ({ items: [] as AssistantConversationSummary[], total: 0, limit: 100, offset: 0 })),
    create: vi.fn(async (workspaceId: number, title: string) => ({ id: nextConversation++, workspace_id: workspaceId, title, created_at: null, updated_at: null, archived_at: null })),
    get: vi.fn(async (_id: number): Promise<AssistantConversationDetail> => { throw new Error("not found"); }),
  };
  const warmup = vi.fn(async () => undefined);
  return { recorder, player, engine, systemVoice, streamRag, conversations, warmup };
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
  window.localStorage.setItem("modai.voice.review", "0"); // review-by-default is covered by its own test
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
    expect(await screen.findByText(/Durduruldu · tamamlanmayan yanıt görüşme geçmişine kaydedilmez/)).toBeInTheDocument();

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

  it("passes the selected speaking speed to synthesis and remembers it", async () => {
    const fakes = createFakes();
    renderVoice(fakes);
    fireEvent.click(await screen.findByLabelText("Konuşma hızı 1,15×"));
    expect(window.localStorage.getItem("modai.voice.speed")).toBe("1.15");
    await askBySpeaking();
    await waitFor(() => expect(fakes.engine.speak).toHaveBeenCalledTimes(2));
    expect(fakes.engine.speak.mock.calls.map((call) => call[4])).toEqual([1.15, 1.15]);
  });

  it("can show the recognized question for correction before sending it", async () => {
    const fakes = createFakes();
    renderVoice(fakes);
    fireEvent.click(await screen.findByLabelText("Göndermeden önce soruyu göster"));
    await askBySpeaking();
    const field = await screen.findByLabelText("Anladığım soru");
    expect(field).toHaveValue(QUESTION);
    expect(phase()).toBe("reviewing");
    expect(fakes.streamRag).not.toHaveBeenCalled();
    fireEvent.change(field, { target: { value: "Yıllık izin politikası ne?" } });
    fireEvent.click(screen.getByRole("button", { name: "Soruyu gönder" }));
    await waitFor(() => expect(fakes.streamRag).toHaveBeenCalledWith([7], "Yıllık izin politikası ne?", expect.any(Function), expect.any(AbortSignal), expect.any(Object)));
    expect(await screen.findByText(/Tanınan konuşma · düzeltildi/)).toBeInTheDocument();
  });

  it("re-asks a corrected transcript and stops the previous answer", async () => {
    const fakes = createFakes();
    renderVoice(fakes);
    await askBySpeaking();
    await waitFor(() => expect(phase()).toBe("idle"));
    fireEvent.click(screen.getByRole("button", { name: "Düzelt" }));
    fireEvent.change(screen.getByLabelText("Soruyu düzelt"), { target: { value: "Masraf onayını kim veriyor?" } });
    fireEvent.click(screen.getByRole("button", { name: "Düzeltilmiş soruyu sor" }));
    await waitFor(() => expect(fakes.streamRag).toHaveBeenCalledTimes(2));
    expect(fakes.streamRag.mock.calls[1][1]).toBe("Masraf onayını kim veriyor?");
    expect(fakes.engine.cancel).toHaveBeenCalledWith(1);
    expect(await screen.findByText(/düzeltildi/)).toBeInTheDocument();
  });

  it("shows searching, then answering, then speaking", async () => {
    const fakes = createFakes();
    let release!: () => void;
    fakes.streamRag.mockImplementationOnce(async (_kbs, _question, onEvent) => {
      await new Promise<void>((resolve) => { release = resolve; });
      onEvent({ type: "sources", data: [SOURCE] });
      await new Promise((resolve) => setTimeout(resolve, 20));
      onEvent({ type: "token", data: "Başvurular 15 gün önce yapılır. " });
      onEvent({ type: "complete" });
    });
    renderVoice(fakes);
    await askBySpeaking();
    await waitFor(() => expect(phase()).toBe("searching"));
    expect(screen.getByText("Belgelerde arıyorum…")).toBeInTheDocument();
    act(() => release());
    await waitFor(() => expect(phase()).toBe("answering"));
    await waitFor(() => expect(phase()).toBe("idle"));
    expect(screen.getByTestId("spoken-status")).toHaveTextContent("Seslendirilen: 1/1 bölüm");
  });

  it("keeps at most two phrases in the synthesizer and waits for buffered audio to play", async () => {
    const fakes = createFakes();
    const pendingSpeech: (() => void)[] = [];
    fakes.engine.speak.mockImplementation((_id, _seq, _text, onAudio) => {
      onAudio(new Float32Array(480), 48_000);
      return new Promise<void>((resolve) => pendingSpeech.push(resolve));
    });
    fakes.streamRag.mockImplementationOnce(async (_kbs, _question, onEvent) => {
      onEvent({ type: "token", data: "Bir iki üç dört. Beş altı yedi sekiz. Dokuz on on bir on iki. " });
      onEvent({ type: "complete" });
    });
    renderVoice(fakes);
    await askBySpeaking();
    await waitFor(() => expect(fakes.engine.speak).toHaveBeenCalledTimes(2));
    fakes.player.bufferedSeconds.mockReturnValue(20); // too much audio already waiting
    act(() => pendingSpeech.shift()?.());
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(fakes.engine.speak).toHaveBeenCalledTimes(2);
    fakes.player.bufferedSeconds.mockReturnValue(1);
    await waitFor(() => expect(fakes.engine.speak).toHaveBeenCalledTimes(3), { timeout: 1000 });
    expect(fakes.engine.speak.mock.calls.map(([, seq]) => seq)).toEqual([0, 1, 2]);
    act(() => pendingSpeech.splice(0).forEach((resolve) => resolve()));
    await waitFor(() => expect(phase()).toBe("idle"));
    expect(screen.getByTestId("spoken-status")).toHaveTextContent("Seslendirilen: 3/3 bölüm");
  });

  it("asks for a Turkish answer and never speaks an English sentence with the Turkish voice", async () => {
    const fakes = createFakes();
    fakes.streamRag.mockImplementationOnce(async (_kbs, _question, onEvent) => {
      onEvent({ type: "sources", data: [{ ...SOURCE, document: "vpn-guide-en.md" }] });
      onEvent({ type: "token", data: "VPN rehberine göre en fazla 2 cihazdan bağlanabilirsiniz. " });
      onEvent({ type: "token", data: "Every session ends after 12 hours and you must sign in again with the app. " });
      onEvent({ type: "complete" });
    });
    renderVoice(fakes);
    await askBySpeaking();
    await waitFor(() => expect(phase()).toBe("idle"));
    expect(fakes.streamRag.mock.calls[0][4]).toEqual(expect.objectContaining({ responseLanguage: "tr", diagnostics: true }));
    expect(fakes.engine.speak.mock.calls.map(([, , text]) => text)).toEqual(["vi pi en rehberine göre en fazla 2 cihazdan bağlanabilirsiniz."]);
    expect(screen.getByText(/1 bölüm Türkçe olmadığı için Türkçe sesle okunmadı/)).toBeInTheDocument();
    expect(screen.getByText(/Every session ends after 12 hours/)).toBeInTheDocument(); // still shown as text
  });

  it("answers a plain greeting locally in Turkish without searching documents", async () => {
    const fakes = createFakes();
    fakes.engine.transcribe.mockResolvedValueOnce({ text: "Merhaba, bana nasıl yardımcı olabilirsin?", ms: 90 });
    renderVoice(fakes);
    await askBySpeaking();
    await waitFor(() => expect(phase()).toBe("idle"));
    expect(fakes.streamRag).not.toHaveBeenCalled();
    expect(fakes.conversations.create).not.toHaveBeenCalled();
    expect(screen.getByText(/Seçtiğiniz Knowledge Base'lerdeki belgelerden yanıt verebilirim/)).toBeInTheDocument();
    expect(screen.getByText("Belgelerde arama yapılmadı · görüşme geçmişine kaydedilmez")).toBeInTheDocument();
    expect(fakes.engine.speak).toHaveBeenCalledTimes(1);
  });

  it("shows the recognized question for review by default for new users", async () => {
    window.localStorage.removeItem("modai.voice.review");
    const fakes = createFakes();
    fakes.engine.transcribe.mockResolvedValueOnce({ text: "Biberist neyar var?", ms: 90 });
    renderVoice(fakes);
    expect(await screen.findByLabelText("Göndermeden önce soruyu göster")).toBeChecked();
    await askBySpeaking();
    const field = await screen.findByLabelText("Anladığım soru");
    expect(field).toHaveValue("Biberist neyar var?"); // shown exactly as heard, never silently "fixed"
    expect(fakes.streamRag).not.toHaveBeenCalled();
    fireEvent.change(field, { target: { value: "Bugün hangi belgelerden bilgi verebilirsin?" } });
    fireEvent.click(screen.getByRole("button", { name: "Soruyu gönder" }));
    await waitFor(() => expect(fakes.streamRag).toHaveBeenCalledTimes(1));
    expect(fakes.streamRag.mock.calls[0][1]).toBe("Bugün hangi belgelerden bilgi verebilirsin?");
  });

  it("creates one voice conversation on the first question and reuses it for the next", async () => {
    const fakes = createFakes();
    renderVoice(fakes);
    await askBySpeaking();
    await waitFor(() => expect(fakes.streamRag).toHaveBeenCalledTimes(1));
    expect(fakes.conversations.list).toHaveBeenCalledWith(3);
    expect(fakes.conversations.create).toHaveBeenCalledWith(3, `Sesli görüşme: ${QUESTION}`);
    expect(fakes.streamRag.mock.calls[0][4]).toEqual(expect.objectContaining({ conversationId: 50 }));
    await waitFor(() => expect(phase()).toBe("idle"));
    fireEvent.change(screen.getByLabelText("Yazılı soru"), { target: { value: "Masraf onayını kim veriyor?" } });
    fireEvent.click(screen.getByRole("button", { name: "Gönder" }));
    await waitFor(() => expect(fakes.streamRag).toHaveBeenCalledTimes(2));
    expect(fakes.streamRag.mock.calls[1][4]).toEqual(expect.objectContaining({ conversationId: 50 }));
    expect(fakes.conversations.create).toHaveBeenCalledTimes(1);
    expect(screen.getByLabelText("Görüşme seç")).toHaveValue("50");
  });

  it("starts a new conversation on request", async () => {
    const fakes = createFakes();
    renderVoice(fakes);
    await askBySpeaking();
    await waitFor(() => expect(phase()).toBe("idle"));
    fireEvent.click(screen.getByRole("button", { name: /Yeni görüşme/ }));
    expect(screen.queryAllByTestId("voice-turn")).toHaveLength(0);
    fireEvent.change(screen.getByLabelText("Yazılı soru"), { target: { value: "Masraf onayını kim veriyor?" } });
    fireEvent.click(screen.getByRole("button", { name: "Gönder" }));
    await waitFor(() => expect(fakes.streamRag).toHaveBeenCalledTimes(2));
    expect(fakes.conversations.create).toHaveBeenCalledTimes(2);
    expect(fakes.streamRag.mock.calls[1][4]).toEqual(expect.objectContaining({ conversationId: 51 }));
  });

  it("restores the latest voice conversation after a remount without playing it", async () => {
    const fakes = createFakes();
    const saved: AssistantConversationSummary = { id: 77, workspace_id: 3, title: `Sesli görüşme: ${QUESTION}`, created_at: null, updated_at: null, archived_at: null };
    fakes.conversations.list.mockResolvedValue({ items: [{ ...saved, id: 76, title: null }, saved], total: 2, limit: 100, offset: 0 });
    fakes.conversations.get.mockResolvedValue({
      ...saved, message_total: 4, message_limit: 100, message_offset: 0,
      messages: [
        { id: 1, role: "user", content: QUESTION, sources: [], created_at: null },
        { id: 2, role: "assistant", content: "16 iş günü.", sources: [{ document: "izin.md", score: 0.7, document_id: 41, chunk_index: 0 }], created_at: null },
        { id: 3, role: "user", content: "Peki devir?", sources: [], created_at: null },
        { id: 4, role: "assistant", content: "En fazla 5 gün devreder.", sources: [], created_at: null },
      ],
    });
    const first = renderVoice(fakes);
    expect(await screen.findByText("En fazla 5 gün devreder.")).toBeInTheDocument();
    first.unmount();
    renderVoice(fakes);
    expect(await screen.findByText("16 iş günü.")).toBeInTheDocument();
    const turns = screen.getAllByTestId("voice-turn");
    expect(turns).toHaveLength(2);
    expect(turns[0]).toHaveTextContent(QUESTION);
    expect(turns[0]).toHaveTextContent("16 iş günü.");
    expect(turns[1]).toHaveTextContent("Peki devir?");
    expect(turns[1]).toHaveTextContent("En fazla 5 gün devreder.");
    expect(screen.getAllByText("Kayıtlı soru")).toHaveLength(2);
    expect(fakes.conversations.get).toHaveBeenLastCalledWith(77);
    expect(screen.getByLabelText("Görüşme seç")).toHaveValue("77");
    expect(within(screen.getByTestId("voice-sources")).getByText("Alıntı kayıtlı değil")).toBeInTheDocument();
    expect(fakes.engine.speak).not.toHaveBeenCalled();
    expect(fakes.streamRag).not.toHaveBeenCalled();
    expect(phase()).toBe("idle");
  });

  it("never shows a conversation that belongs to another workspace", async () => {
    const fakes = createFakes();
    const foreign: AssistantConversationSummary = { id: 90, workspace_id: 3, title: "Sesli görüşme: x", created_at: null, updated_at: null, archived_at: null };
    fakes.conversations.list.mockResolvedValue({ items: [foreign], total: 1, limit: 100, offset: 0 });
    fakes.conversations.get.mockResolvedValue({ ...foreign, workspace_id: 99, message_total: 1, message_limit: 100, message_offset: 0, messages: [{ id: 1, role: "user", content: "başka alan", sources: [], created_at: null }] });
    renderVoice(fakes);
    expect(await screen.findByRole("alert")).toHaveTextContent("Bu görüşme seçili Workspace'e ait değil.");
    expect(screen.queryByText("başka alan")).not.toBeInTheDocument();
  });

  it("separates speech-model queue wait from Whisper inference in the timings", async () => {
    const fakes = createFakes();
    const base = performance.timeOrigin + performance.now();
    fakes.engine.transcribe.mockResolvedValueOnce({ text: QUESTION, ms: 4200, postedAt: base, receivedAt: base + 5, startedAt: base + 3505, endedAt: base + 4205, warm: false, backend: "webgpu" });
    renderVoice(fakes);
    await askBySpeaking();
    await waitFor(() => expect(phase()).toBe("idle"));
    const details = screen.getByTestId("timing-details");
    expect(within(details).getByText("Model sırası / model hazırlığı").nextSibling).toHaveTextContent("3500 ms");
    expect(within(details).getByText("Whisper çıkarımı").nextSibling).toHaveTextContent("700 ms");
    expect(within(details).getByText("Konuşma modeli").nextSibling).toHaveTextContent("WebGPU · ilk yükleme sırasında");
    expect(within(details).getByText("Ses").nextSibling).toHaveTextContent("48000 Hz → 16000 Hz");
  });

  it("warms up the generation model when the page opens and when the user starts speaking", async () => {
    const fakes = createFakes();
    renderVoice(fakes);
    await talkButton();
    expect(fakes.warmup).toHaveBeenCalledTimes(1); // throttled to once a minute
    await askBySpeaking();
    await waitFor(() => expect(phase()).toBe("idle"));
    expect(fakes.warmup).toHaveBeenCalledTimes(1);
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
