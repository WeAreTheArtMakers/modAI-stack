import { afterEach, describe, expect, it, vi } from "vitest";
import { WebAudioPlayer } from "./audioPlayback";
import { measureAudio, MicrophoneError, MicrophoneRecorder, trimSilence } from "./microphone";
import type { WorkerRequest, WorkerResponse } from "./protocol";
import { SentenceBuffer, speakable } from "./sentenceBuffer";
import { classifyIntent, sentenceLanguage } from "./intent";
import { stageDurations } from "./timeline";
import { turnsFromConversation } from "./useVoiceAssistant";
import { turkishOrdinal } from "./speechText";
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
    const { emitted, rest } = stream(["Dr. Ayşe ", "3.5 gün ve v1.2 için ", "örn. 10. madde ", "geçerlidir. ", "Sonra geldi."]);
    expect(emitted.flat()).toEqual(["Dr. Ayşe 3.5 gün ve sürüm 1.2 için örneğin onuncu madde geçerlidir."]);
    expect(rest).toEqual(["Sonra geldi."]);
  });

  it("ends a sentence after a number when a capitalized sentence follows", () => {
    const { emitted, rest } = stream(["Toplam tutar 40. ", "Kalan izin 12 gündür."]);
    expect(emitted.flat()).toEqual(["Toplam tutar 40."]);
    expect(rest).toEqual(["Kalan izin 12 gündür."]);
  });

  it("starts speaking at the first comma once the opening phrase is long enough", () => {
    const words = "Güncel izin politikasına göre, başvurular en az 15 gün önce, sistem üzerinden yapılır. ".split(/(?<= )/);
    const { emitted } = stream(words);
    expect(emitted.flat()).toEqual(["Güncel izin politikasına göre,", "başvurular en az 15 gün önce, sistem üzerinden yapılır."]);
    // the phrase is ready with the token that brings the comma and its following space
    expect(emitted.findIndex((batch) => batch.length > 0)).toBe(words.indexOf("göre, "));
  });

  it("keeps a short opening clause together with the rest of the sentence", () => {
    const { emitted } = stream(["Evet, ", "izin ", "alınır. "]);
    expect(emitted.flat()).toEqual(["Evet, izin alınır."]);
  });

  it("cuts a long first sentence without punctuation at a word boundary", () => {
    const long = `${"uzun kelime ".repeat(10)}devam ediyor `;
    const { emitted } = stream([long]);
    expect(emitted[0]).toHaveLength(1);
    expect(emitted[0][0].length).toBeLessThanOrEqual(90);
    expect(long.startsWith(emitted[0][0])).toBe(true);
  });

  it("splits later overlong sentences at a clause boundary", () => {
    const long = `İlk cümle burada bitiyor. ${"kelime ".repeat(20)}ara, ${"devam ".repeat(30)}`;
    const { emitted } = stream([long]);
    expect(emitted[0]).toEqual(["İlk cümle burada bitiyor.", `${"kelime ".repeat(20)}ara,`.trim()]);
  });

  it("joins one-word fragments to the next phrase", () => {
    const { emitted, rest } = stream(["Evet. ", "Başvuru 15 gün önce yapılır. ", "Tamam."]);
    expect(emitted.flat()).toEqual(["Evet. Başvuru 15 gün önce yapılır."]);
    expect(rest).toEqual(["Tamam."]);
  });
});

describe("speakable", () => {
  it("strips markdown, citation markers, links and source identifiers", () => {
    expect(speakable("**Önemli:** [1] Bkz. https://intra.example/izin #politika")).toBe("Önemli: bakınız bağlantı politika");
    expect(speakable("- madde bir\n- madde iki")).toBe("madde bir madde iki");
    expect(speakable("Bkz. izin-politikasi-v3.md [2] (Kaynak: belge.md) ve doc-12.")).toBe("bakınız izin politikasi sürüm 3 ve belge 12.");
    expect(speakable("[Portal](https://intra.example/portal) üzerinden")).toBe("Portal üzerinden");
  });

  it("rewrites times, ranges and currency suffixes the normalizer misreads", () => {
    expect(speakable("Destek 08.00-17.00 arası, saat 9.30'da toplantı; 09:30'a kadar.")).toBe("Destek 8:00 ile 17:00 arası, saat 9:30'da toplantı; 9:30'a kadar.");
    expect(speakable("3-5 iş günü, 2025-2026 dönemi, 2026-10-07 tarihli")).toBe("3 ile 5 iş günü, 2025 ile 2026 dönemi, 2026-10-07 tarihli");
    expect(speakable("10.000 TL'lik bütçe")).toBe("10.000 liralık bütçe");
  });

  it("reads ordinals, acronyms and common abbreviations", () => {
    expect(speakable("3. kat ve 12. madde")).toBe("üçüncü kat ve on ikinci madde");
    expect(speakable("Toplam 40. Kalan")).toBe("Toplam 40. Kalan");
    expect(speakable("IT ekibi SLA'ya göre VPN ve 2FA kullanır.")).toBe("ay ti ekibi es el ey ya göre vi pi en ve iki adımlı doğrulama kullanır.");
    expect(speakable("24/7 destek, Q3 hedefi, v2.1 ve/veya maks. 5 gün")).toBe("yedi gün yirmi dört saat destek, üçüncü çeyrek hedefi, sürüm 2.1 ve veya en fazla 5 gün");
  });

  it("preserves every fact-bearing number", () => {
    expect(speakable("Limit 25.000 TL, %15 indirim, 14:30, 15.03.2026, 0850 123 45 67.")).toBe("Limit 25.000 TL, %15 indirim, 14:30, 15.03.2026, 0850 123 45 67.");
  });

  it("names Turkish ordinals", () => {
    expect([1, 9, 10, 12, 40, 99].map(turkishOrdinal)).toEqual(["birinci", "dokuzuncu", "onuncu", "on ikinci", "kırkıncı", "doksan dokuzuncu"]);
    expect([0, 100, 2.5].map(turkishOrdinal)).toEqual([null, null, null]);
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
    worker.emit({ type: "transcript", id: 1, text: "merhaba", ms: 300, receivedAt: 5, startedAt: 10, endedAt: 290, warm: true, backend: "webgpu", audioSeconds: 1 });
    await expect(result).resolves.toEqual(expect.objectContaining({ text: "merhaba", ms: 300, receivedAt: 5, startedAt: 10, endedAt: 290, warm: true, backend: "webgpu" }));
    expect((await result).postedAt).toEqual(expect.any(Number));
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

    expect(player.bufferedSeconds()).toBeCloseTo(1.53);
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

describe("trimSilence", () => {
  function signal(parts: [seconds: number, amplitude: number][]) {
    const out: number[] = [];
    for (const [seconds, amplitude] of parts) {
      for (let i = 0; i < seconds * 16_000; i++) out.push(amplitude * Math.sin(i / 3) + 0.001 * Math.sin(i * 7.1));
    }
    return Float32Array.from(out);
  }

  it("keeps the speech plus a 300 ms margin on each side and reports what it removed", () => {
    const trimmed = trimSilence(signal([[1, 0], [0.6, 0.3], [1.5, 0]]));
    expect(trimmed.samples.length / 16_000).toBeGreaterThan(1.15);
    expect(trimmed.samples.length / 16_000).toBeLessThan(1.25);
    expect(trimmed.leadingMs).toBeGreaterThan(650);
    expect(trimmed.leadingMs).toBeLessThan(720);
    expect(trimmed.trailingMs).toBeGreaterThan(1150);
  });

  it("keeps quiet speech instead of trimming it away", () => {
    const quiet = signal([[0.5, 0], [0.6, 0.012], [0.5, 0]]);
    const trimmed = trimSilence(quiet);
    expect(trimmed.samples.length / 16_000).toBeGreaterThan(1.1);
  });

  it("leaves audio alone when there is nothing to trim or no speech at all", () => {
    const speech = signal([[0.8, 0.3]]);
    expect(trimSilence(speech).samples).toBe(speech);
    const silence = signal([[2, 0]]);
    expect(trimSilence(silence)).toEqual({ samples: silence, leadingMs: 0, trailingMs: 0 });
  });

  it("measures level and clipping without keeping the audio", () => {
    const measured = measureAudio(Float32Array.from([0, 0.5, -1, 1, 0.5]));
    expect(measured.peak).toBe(1);
    expect(measured.clippedPercent).toBeCloseTo(40);
    expect(measured.durationMs).toBeCloseTo(0.3125);
  });
});

describe("intent and language", () => {
  it.each([
    ["Merhaba", "greeting"],
    ["Selam, günaydın!", "greeting"],
    ["Teşekkürler", "thanks"],
    ["Merhaba, bana nasıl yardımcı olabilirsin?", "capability"],
    ["Merhaba, benden sürü yardımcı olabilirsin.", "capability"], // what Whisper heard in the owner's test
    ["Neler yapabilirsin?", "capability"],
    ["Merhaba, yıllık izin kaç gün?", "question"],
    ["Masraf iadesinde bana nasıl yardımcı olabilirsin?", "question"],
    ["Biberist neyar var? Biberist'in de bana hangi belgelardan bir görebilirsin?", "question"],
  ])("classifies %s as %s", (text, intent) => {
    expect(classifyIntent(text)).toBe(intent);
  });

  it.each([
    ["Every session ends after 12 hours and you must sign in again.", "en"],
    ["VPN rehberine göre en fazla 2 cihazdan bağlanabilirsiniz.", "tr"],
    ["Customer Support Service Level Agreement belgesine göre ilk yanıt 30 dakikadır.", "tr"],
    ["Dokuz on on bir on iki.", "tr"],
    ["Tamam.", "unknown"],
  ])("detects the language of %s", (text, language) => {
    expect(sentenceLanguage(text)).toBe(language);
  });
});

describe("restored conversations", () => {
  it("pairs saved messages into turns in order and keeps only the stored source metadata", () => {
    const turns = turnsFromConversation({
      id: 5, workspace_id: 3, title: "Sesli görüşme: x", created_at: null, updated_at: null, archived_at: null,
      message_total: 3, message_limit: 100, message_offset: 0,
      messages: [
        { id: 10, role: "user", content: "Soru 1", sources: [], created_at: null },
        { id: 11, role: "assistant", content: "Yanıt 1", sources: [{ document: "a.md", score: 0.5, document_id: 1, chunk_index: 0 }], created_at: null },
        { id: 12, role: "user", content: "Soru 2", sources: [], created_at: null },
      ],
    });
    expect(turns.map((turn) => [turn.question, turn.answer, turn.restored, turn.streaming])).toEqual([["Soru 1", "Yanıt 1", true, false], ["Soru 2", "", true, false]]);
    expect(turns[0].sources).toEqual([{ document: "a.md", score: 0.5, document_id: 1, chunk_index: 0, text: null }]);
    expect(new Set(turns.map((turn) => turn.id)).size).toBe(2);
  });
});

describe("stage timings", () => {
  it("separates transfer, queue wait and inference for speech recognition", () => {
    expect(stageDurations({ recordStop: 0, audioReady: 40, sttPosted: 41, sttReceived: 43, sttStart: 3043, sttEnd: 3743, transcriptReceived: 3745 })).toEqual(
      expect.objectContaining({ sttCapture: 40, sttTransferIn: 2, sttQueueWait: 3000, sttInference: 700, sttTransferBack: 2 }),
    );
  });
});
