import { afterEach, describe, expect, it, vi } from "vitest";
import { WebAudioPlayer } from "./audioPlayback";
import { MicrophoneError, MicrophoneRecorder } from "./microphone";
import type { WorkerRequest, WorkerResponse } from "./protocol";
import { SentenceBuffer, speakable } from "./sentenceBuffer";
import { WorkerVoiceEngine, type LoadState } from "./voiceEngine";

function stream(tokens: string[]) {
  const buffer = new SentenceBuffer();
  const out: string[][] = tokens.map((token) => buffer.push(token));
  return { emitted: out, rest: buffer.flush() };
}

describe("SentenceBuffer", () => {
  it("emits a sentence only once the following whitespace has arrived", () => {
    const { emitted, rest } = stream(["İzin ", "15 gün önce ", "istenir.", " Onay ", "yöneticiden alınır."]);
    expect(emitted).toEqual([[], [], [], ["İzin 15 gün önce istenir."], []]);
    expect(rest).toEqual(["Onay yöneticiden alınır."]);
  });

  it("does not split decimals, versions, abbreviations or ordinals", () => {
    const { emitted, rest } = stream(["Dr. Ayşe ", "3.5 gün ve v1.2 için ", "örn. 10. madde ", "geçerlidir. ", "Sonra."]);
    expect(emitted.flat()).toEqual(["Dr. Ayşe 3.5 gün ve v1.2 için örn. 10. madde geçerlidir."]);
    expect(rest).toEqual(["Sonra."]);
  });

  it("ends a sentence after a number when a capitalized sentence follows", () => {
    const { emitted, rest } = stream(["Toplam tutar 40. ", "Kalan izin 12 gündür."]);
    expect(emitted.flat()).toEqual(["Toplam tutar 40."]);
    expect(rest).toEqual(["Kalan izin 12 gündür."]);
  });

  it("splits overlong text without punctuation at a clause boundary", () => {
    const long = `${"kelime ".repeat(30)}ara, ${"devam ".repeat(30)}`;
    const { emitted } = stream([long]);
    expect(emitted[0][0].endsWith("ara,")).toBe(true);
  });

  it("strips markdown, citation markers and links before speaking", () => {
    expect(speakable("**Önemli:** [1] Bkz. https://intra.example/izin #politika")).toBe("Önemli: Bkz. bağlantı politika");
    expect(speakable("- madde bir\n- madde iki")).toBe("madde bir madde iki");
  });
});

class FakeWorker {
  sent: { message: WorkerRequest; transfer: ArrayBuffer[] }[] = [];
  onmessage: ((event: MessageEvent<WorkerResponse>) => void) | null = null;
  onerror: ((event: ErrorEvent) => void) | null = null;
  terminated = false;
  postMessage(message: WorkerRequest, transfer: ArrayBuffer[] = []) { this.sent.push({ message, transfer }); }
  emit(message: WorkerResponse) { this.onmessage?.({ data: message } as MessageEvent<WorkerResponse>); }
  terminate() { this.terminated = true; }
}

describe("WorkerVoiceEngine", () => {
  function engine() {
    const worker = new FakeWorker();
    return { worker, voice: new WorkerVoiceEngine(() => worker as unknown as Worker) };
  }

  it("reports loading progress and readiness per component", async () => {
    const { worker, voice } = engine();
    const states: LoadState[] = [];
    const loaded = voice.load("tts", (state) => states.push(state));
    expect(worker.sent[0].message).toEqual({ type: "load", component: "tts" });
    worker.emit({ type: "progress", component: "tts", loaded: 50, total: 100, stage: "sound" });
    worker.emit({ type: "ready", component: "tts", backend: "webgpu", ms: 812 });
    await expect(loaded).resolves.toBe("webgpu");
    expect(states.map((state) => state.status)).toEqual(["loading", "loading", "ready"]);
    expect(states[1].loaded).toBe(50);
  });

  it("transfers audio to the worker and resolves the transcript", async () => {
    const { worker, voice } = engine();
    const audio = new Float32Array(16_000);
    const result = voice.transcribe(audio);
    expect(worker.sent[0].transfer).toEqual([audio.buffer]);
    worker.emit({ type: "transcript", id: 1, text: "merhaba", ms: 300, startedAt: 10, endedAt: 290 });
    await expect(result).resolves.toEqual({ text: "merhaba", ms: 300, startedAt: 10, endedAt: 290 });
  });

  it("routes audio chunks to their sentence and resolves cancelled sentences", async () => {
    const { worker, voice } = engine();
    const chunks: number[] = [];
    const first = voice.speak(4, 0, "Bir.", (samples) => chunks.push(samples.length));
    const second = voice.speak(4, 1, "İki.", () => chunks.push(-1));
    worker.emit({ type: "audio", id: 4, seq: 0, samples: new Float32Array(10), sampleRate: 48_000, synthStartedAt: 1, postedAt: 2 });
    worker.emit({ type: "spoken", id: 4, seq: 0, ms: 20 });
    await first;
    voice.cancel(4);
    await second; // resolved by the cancellation, not left hanging
    expect(worker.sent.at(-1)?.message).toEqual({ type: "cancel", upTo: 4 });
    worker.emit({ type: "audio", id: 4, seq: 1, samples: new Float32Array(10), sampleRate: 48_000, synthStartedAt: 1, postedAt: 2 });
    expect(chunks).toEqual([10]);
  });

  it("rejects pending work when the worker crashes, and allows a reload afterwards", async () => {
    const { worker, voice } = engine();
    const loading = voice.load("stt", () => undefined);
    worker.onerror?.({ message: "boom" } as ErrorEvent);
    await expect(loading).rejects.toThrow("boom");
    voice.load("stt", () => undefined).catch(() => undefined);
    expect(worker.sent.filter((item) => item.message.type === "load")).toHaveLength(2);
    voice.dispose();
    expect(worker.terminated).toBe(true);
  });
});

describe("MicrophoneRecorder", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("refuses to record outside a secure context", async () => {
    vi.stubGlobal("isSecureContext", false);
    await expect(new MicrophoneRecorder().start(() => undefined)).rejects.toMatchObject({ code: "insecure_context" });
  });

  it.each([
    ["NotAllowedError", "permission_denied"],
    ["SecurityError", "permission_denied"],
    ["NotFoundError", "no_microphone"],
    ["NotReadableError", "microphone_busy"],
  ])("maps %s to %s", async (name, code) => {
    vi.stubGlobal("isSecureContext", true);
    vi.stubGlobal("MediaRecorder", class {});
    vi.stubGlobal("navigator", { mediaDevices: { getUserMedia: vi.fn().mockRejectedValue(new DOMException("denied", name)) } });
    const error = await new MicrophoneRecorder().start(() => undefined).catch((reason: unknown) => reason);
    expect(error).toBeInstanceOf(MicrophoneError);
    expect(error).toMatchObject({ code });
  });

  it("reports browsers without recording support", async () => {
    vi.stubGlobal("isSecureContext", true);
    vi.stubGlobal("navigator", {});
    await expect(new MicrophoneRecorder().start(() => undefined)).rejects.toMatchObject({ code: "unsupported" });
  });
});

describe("WebAudioPlayer", () => {
  afterEach(() => vi.unstubAllGlobals());

  function fakeAudio() {
    const sources: { started: number; stopped: boolean; onended: (() => void) | null }[] = [];
    class FakeContext {
      currentTime = 0;
      destination = {};
      createAnalyser() { return { fftSize: 0, connect: vi.fn(), getFloatTimeDomainData: (buffer: Float32Array) => buffer.fill(0.1) }; }
      createBuffer(_channels: number, length: number, rate: number) { return { duration: length / rate, copyToChannel: vi.fn() }; }
      createBufferSource() {
        const source = { buffer: null, connect: vi.fn(), onended: null as (() => void) | null, started: -1, stopped: false,
          start(at: number) { source.started = at; }, stop() { source.stopped = true; } };
        sources.push(source);
        return source;
      }
      resume() { return Promise.resolve(); }
      close() { return Promise.resolve(); }
    }
    vi.stubGlobal("AudioContext", FakeContext);
    return sources;
  }

  it("plays chunks back to back and drops audio from stale generations", async () => {
    const sources = fakeAudio();
    const player = new WebAudioPlayer();
    player.reset(1);
    expect(player.enqueue(new Float32Array(48_000), 48_000, 1)).not.toBeNull();
    expect(player.enqueue(new Float32Array(24_000), 48_000, 1)).not.toBeNull();
    expect(sources.map((source) => source.started)).toEqual([0.03, 1.03]);
    expect(player.level()).toBeGreaterThan(0);

    player.reset(2); // stop: the old answer must not continue
    expect(sources.every((source) => source.stopped)).toBe(true);
    expect(player.enqueue(new Float32Array(48_000), 48_000, 1)).toBeNull();
    expect(sources).toHaveLength(2);
    await expect(player.drained()).resolves.toBeUndefined();
  });

  it("resolves drained() after the last buffer ends", async () => {
    const sources = fakeAudio();
    const player = new WebAudioPlayer();
    player.reset(5);
    player.enqueue(new Float32Array(480), 48_000, 5);
    let done = false;
    const drained = player.drained().then(() => { done = true; });
    await Promise.resolve();
    expect(done).toBe(false);
    sources[0].onended?.();
    await drained;
    expect(done).toBe(true);
  });
});
