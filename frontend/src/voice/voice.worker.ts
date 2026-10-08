/// <reference lib="webworker" />
// Speech recognition (Whisper tiny or base via Transformers.js) and Turkish speech synthesis
// (EMA Lightning) off the React main thread. Both share one onnxruntime-web instance.
import { env, pipeline, type AutomaticSpeechRecognitionPipeline, type ProgressInfo } from "@huggingface/transformers";
import * as ort from "onnxruntime-web/webgpu";
// The WebGPU build of the runtime (it also runs the WASM backend), emitted by Vite as a hashed asset.
import ortWasmUrl from "onnxruntime-web/ort-wasm-simd-threaded.asyncify.wasm?url";
import { DEFAULT_STT_MODEL, EMA_LIGHTNING, VOICE_MODELS_BASE, WHISPER_LANGUAGE, WHISPER_MODELS, WHISPER_SAMPLE_RATE, type SttModelId } from "./config";
import type { InferenceBackend, VoiceComponent, WorkerRequest, WorkerResponse } from "./protocol";
import { EmaLightning, RATE } from "./vendor/emaLightning";

const scope = self as unknown as {
  postMessage(message: WorkerResponse, transfer: ArrayBuffer[]): void;
  onmessage: ((event: MessageEvent<WorkerRequest>) => void) | null;
};

// Everything is served by the application origin: no Hub, no CDN, no blob: module imports
// (the CSP allows neither).
env.allowRemoteModels = false;
env.allowLocalModels = true;
env.localModelPath = VOICE_MODELS_BASE;
env.useBrowserCache = true;
env.cacheKey = "modai-voice-transformers-v1";
env.useWasmCache = false;
// A proxy that compresses on the fly drops Content-Length; Transformers.js would then start a
// second full download of the same file to learn its size, which breaks the first stream
// ("network error"). Buffer such responses and state their length instead.
env.fetch = async (input: string | URL, init?: Parameters<typeof fetch>[1]) => {
  const response = await fetch(input, init);
  if (!response.ok || response.headers.get("content-length") || init?.method === "HEAD") return response;
  const body = await response.arrayBuffer();
  const headers = new Headers(response.headers);
  headers.set("content-length", String(body.byteLength));
  return new Response(body, { status: response.status, statusText: response.statusText, headers });
};
ort.env.wasm.wasmPaths = { wasm: ortWasmUrl };
ort.env.wasm.proxy = false;

const post = (message: WorkerResponse, transfer: ArrayBuffer[] = []) => scope.postMessage(message, transfer);
const clock = () => performance.timeOrigin + performance.now();

let synthesizer: Promise<EmaLightning> | null = null;
let cancelledUpTo = 0;

// Both engines share one onnxruntime-web instance, which fails on concurrent initialization
// ("multiple calls to 'initWasm()'") and must not interleave runs, so every load step, warm-up
// and inference runs one at a time. Speech input (recognition) goes before speech output
// (synthesis), so a question never waits for a whole voice-model load or a long answer; each
// queue is FIFO, which keeps sentences in order.
type Lane = "input" | "output";
interface Job { run: () => Promise<unknown>; resolve: (value: unknown) => void; reject: (reason: unknown) => void }
const lanes: Record<Lane, Job[]> = { input: [], output: [] };
let draining = false;

function schedule<T>(lane: Lane, run: () => Promise<T>): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    lanes[lane].push({ run, resolve: resolve as (value: unknown) => void, reject });
    void drain();
  });
}

async function drain() {
  if (draining) return;
  draining = true;
  try {
    for (let job = lanes.input.shift() ?? lanes.output.shift(); job; job = lanes.input.shift() ?? lanes.output.shift()) {
      try {
        job.resolve(await job.run());
      } catch (error) {
        job.reject(error);
      }
    }
  } finally {
    draining = false;
  }
}

function describe(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

interface GpuAdapter { features: { has(name: string): boolean } }
let adapterProbe: Promise<GpuAdapter | null> | null = null;

// requestAdapter() can hang in some embedded browsers; treat no answer within 2 s as no WebGPU.
function webgpuAdapter(): Promise<GpuAdapter | null> {
  adapterProbe ??= (async () => {
    const gpu = (navigator as Navigator & { gpu?: { requestAdapter(): Promise<GpuAdapter | null> } }).gpu;
    if (!gpu) return null;
    const timeout = new Promise<null>((resolve) => setTimeout(() => resolve(null), 2000));
    try {
      return await Promise.race([gpu.requestAdapter(), timeout]);
    } catch {
      return null;
    }
  })();
  return adapterProbe;
}

const TRANSCRIBE = { language: WHISPER_LANGUAGE, task: "transcribe" } as const;

// One Whisper model in memory at a time: selecting another model releases the current one (its
// ONNX sessions, WebGPU buffers and WASM allocations) before the new one is created.
interface Recognizer {
  model: SttModelId;
  promise: Promise<AutomaticSpeechRecognitionPipeline>;
  backend: InferenceBackend;
  ready: boolean;
  released: boolean;
}
class Superseded extends Error {}
let recognizer: Recognizer | null = null;
let requestedModel: SttModelId = DEFAULT_STT_MODEL;

/** Frees a recognizer after any inference already queued for it. */
async function releaseRecognizer(previous: Recognizer) {
  previous.released = true;
  const asr = await previous.promise.catch(() => null);
  if (asr) await schedule("input", () => asr.dispose());
}

function loadRecognizer(model: SttModelId, requested?: InferenceBackend): Recognizer {
  requestedModel = model;
  if (recognizer?.model === model) return recognizer;
  const previous = recognizer;
  const config = WHISPER_MODELS[model];
  const started = performance.now();
  const files = new Map<string, { loaded: number; total: number }>();
  let expectedBytes = config.downloadBytes;
  const onProgress = (info: ProgressInfo) => {
    if (info.status !== "progress" || entry.released) return;
    files.set(info.file, { loaded: info.loaded, total: info.total });
    let loaded = 0;
    for (const file of files.values()) loaded += file.loaded;
    post({ type: "progress", component: "stt", loaded, total: expectedBytes, stage: info.file, model });
  };
  // Measured on Apple M1 Pro (Chrome 152): the fixed 30-second Whisper tiny encoder pass takes
  // ~1.45 s on single-threaded WASM (q8) but ~0.5 s on WebGPU (fp16), with no accuracy loss.
  // The q8 decoder stays on WASM: its integer kernels are not WebGPU kernels.
  const create = (backend: InferenceBackend) => pipeline("automatic-speech-recognition", config.directory, {
    ...(backend === "webgpu"
      ? { device: { encoder_model: "webgpu", decoder_model_merged: "wasm" } as const, dtype: { encoder_model: "fp16", decoder_model_merged: config.dtype } as const }
      : { device: "wasm" as const, dtype: config.dtype }),
    local_files_only: true,
    progress_callback: onProgress,
  }) as Promise<AutomaticSpeechRecognitionPipeline>;
  const entry: Recognizer = { model, backend: "wasm", ready: false, released: false, promise: null as unknown as Promise<AutomaticSpeechRecognitionPipeline> };
  entry.promise = (async () => {
    if (previous) await releaseRecognizer(previous);
    if (entry.released) throw new Superseded(); // another model was selected meanwhile
    let backend: InferenceBackend = requested ?? ((await webgpuAdapter())?.features.has("shader-f16") ? "webgpu" : "wasm");
    expectedBytes = backend === "webgpu" ? config.webgpuDownloadBytes : config.downloadBytes;
    const asr = await schedule("input", async () => {
      let created: AutomaticSpeechRecognitionPipeline;
      try {
        created = await create(backend);
      } catch (error) {
        if (backend === "wasm") throw error;
        backend = "wasm";
        expectedBytes = config.downloadBytes;
        created = await create("wasm");
      }
      // The first inference compiles kernels (tiny: 7.2 s on WASM, 1.0 s on WebGPU, then 1.45 s /
      // 0.5 s): pay for it now, before the user's first question.
      await created(new Float32Array(WHISPER_SAMPLE_RATE), TRANSCRIBE).catch(() => undefined);
      return created;
    });
    entry.backend = backend;
    entry.ready = true;
    if (!entry.released) post({ type: "ready", component: "stt", backend, ms: performance.now() - started, model });
    return asr;
  })();
  entry.promise.catch((error) => {
    if (recognizer === entry) recognizer = null; // allow a retry
    if (!(error instanceof Superseded) && !entry.released) post({ type: "load-error", component: "stt", message: describe(error), model });
  });
  recognizer = entry;
  return entry;
}

function loadSynthesizer(requested?: InferenceBackend): Promise<EmaLightning> {
  if (synthesizer) return synthesizer;
  const started = performance.now();
  const base = `${VOICE_MODELS_BASE}${EMA_LIGHTNING.directory}/`;
  const cacheName = `modai-voice-ema-${EMA_LIGHTNING.revision.slice(0, 8)}`;
  const progress = (stage: string, fraction: number) =>
    post({ type: "progress", component: "tts", loaded: Math.round(fraction * EMA_LIGHTNING.downloadBytes), total: EMA_LIGHTNING.downloadBytes, stage });
  const step = <T,>(run: () => Promise<T>) => schedule("output", run);
  synthesizer = (async () => {
    const backend: InferenceBackend = requested ?? ((await webgpuAdapter()) ? "webgpu" : "wasm");
    let engine: EmaLightning;
    try {
      engine = await EmaLightning.load(backend, base, cacheName, progress, step);
    } catch (error) {
      if (backend === "wasm") throw error;
      engine = await EmaLightning.load("wasm", base, cacheName, progress, step); // WebGPU adapter present but unusable
    }
    // Warm up once so the first answer does not pay for shader compilation.
    await step(async () => { for await (const samples of engine.stream("Merhaba.")) void samples; });
    post({ type: "ready", component: "tts", backend: engine.backend, ms: performance.now() - started });
    return engine;
  })();
  synthesizer.catch((error) => {
    synthesizer = null;
    post({ type: "load-error", component: "tts", message: describe(error) });
  });
  return synthesizer;
}

async function transcribe(id: number, audio: Float32Array, receivedAt: number, warm: boolean) {
  try {
    for (;;) {
      const entry = recognizer ?? loadRecognizer(requestedModel);
      const asr = await entry.promise.catch((error: unknown) => { if (error instanceof Superseded) return null; throw error; });
      if (!asr) continue;
      const output = await schedule("input", async () => {
        if (entry.released) return null; // the model was switched while this waited: use the new one
        const startedAt = clock();
        const result = await asr(audio, TRANSCRIBE);
        return { result, startedAt, endedAt: clock() };
      });
      if (!output) continue;
      const text = (Array.isArray(output.result) ? output.result.map((item) => item.text).join(" ") : output.result.text).trim();
      post({
        type: "transcript", id, text, ms: output.endedAt - receivedAt,
        receivedAt, startedAt: output.startedAt, endedAt: output.endedAt,
        warm, backend: entry.backend, audioSeconds: audio.length / WHISPER_SAMPLE_RATE, model: entry.model,
      });
      return;
    }
  } catch (error) {
    post({ type: "transcribe-error", id, message: describe(error) });
  }
}

async function speak(engine: EmaLightning, id: number, seq: number, text: string, speed: number) {
  if (id <= cancelledUpTo) return;
  try {
    const synthStartedAt = clock();
    for await (const samples of engine.stream(text, { speed })) {
      if (id <= cancelledUpTo) return; // a newer request or stop: drop the rest of this sentence
      post({ type: "audio", id, seq, samples, sampleRate: RATE, synthStartedAt, postedAt: clock() }, [samples.buffer as ArrayBuffer]);
    }
    if (id > cancelledUpTo) post({ type: "spoken", id, seq, ms: clock() - synthStartedAt });
  } catch (error) {
    post({ type: "speak-error", id, seq, message: describe(error) });
  }
}

scope.onmessage = (event: MessageEvent<WorkerRequest>) => {
  const request = event.data;
  if (request.type === "load") {
    const component: VoiceComponent = request.component;
    if (component === "stt") void loadRecognizer(request.model ?? DEFAULT_STT_MODEL, request.backend).promise.catch(() => undefined);
    else void loadSynthesizer(request.backend).catch(() => undefined);
  } else if (request.type === "transcribe") {
    void transcribe(request.id, request.audio, clock(), recognizer?.ready ?? false);
  } else if (request.type === "speak") {
    if (request.id <= cancelledUpTo) return;
    // Queue the sentence only once the model is ready: a sentence must never hold the queue
    // while it waits for a load step queued behind it.
    void loadSynthesizer().then(
      (engine) => schedule("output", () => speak(engine, request.id, request.seq, request.text, request.speed ?? 1)),
      (error: unknown) => post({ type: "speak-error", id: request.id, seq: request.seq, message: describe(error) }),
    );
  } else if (request.type === "cancel") {
    cancelledUpTo = Math.max(cancelledUpTo, request.upTo);
  }
};
