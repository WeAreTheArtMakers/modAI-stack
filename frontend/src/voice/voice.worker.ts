/// <reference lib="webworker" />
// Speech recognition (Whisper tiny via Transformers.js) and Turkish speech synthesis
// (EMA Lightning) off the React main thread. Both share one onnxruntime-web instance.
import { env, pipeline, type AutomaticSpeechRecognitionPipeline, type ProgressInfo } from "@huggingface/transformers";
import * as ort from "onnxruntime-web/webgpu";
// The WebGPU build of the runtime (it also runs the WASM backend), emitted by Vite as a hashed asset.
import ortWasmUrl from "onnxruntime-web/ort-wasm-simd-threaded.asyncify.wasm?url";
import { EMA_LIGHTNING, VOICE_MODELS_BASE, WHISPER } from "./config";
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

let recognizer: Promise<AutomaticSpeechRecognitionPipeline> | null = null;
let synthesizer: Promise<EmaLightning> | null = null;
let cancelledUpTo = 0;
// One FIFO for every inference: sentences stay in order and STT never runs concurrently with TTS.
let work: Promise<void> = Promise.resolve();
// Model loads run one at a time: both engines share one onnxruntime-web instance, and
// initializing its WebAssembly concurrently fails ("multiple calls to 'initWasm()'").
let loading: Promise<unknown> = Promise.resolve();

function oneAtATime<T>(task: () => Promise<T>): Promise<T> {
  const run = loading.then(task, task);
  loading = run.catch(() => undefined);
  return run;
}

function describe(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

async function webgpuAvailable(): Promise<boolean> {
  const gpu = (navigator as Navigator & { gpu?: { requestAdapter(): Promise<unknown> } }).gpu;
  if (!gpu) return false;
  try {
    return (await gpu.requestAdapter()) !== null;
  } catch {
    return false;
  }
}

function loadRecognizer(): Promise<AutomaticSpeechRecognitionPipeline> {
  if (recognizer) return recognizer;
  const started = performance.now();
  const files = new Map<string, { loaded: number; total: number }>();
  const onProgress = (info: ProgressInfo) => {
    if (info.status !== "progress") return;
    files.set(info.file, { loaded: info.loaded, total: info.total });
    let loaded = 0;
    for (const file of files.values()) loaded += file.loaded;
    post({ type: "progress", component: "stt", loaded, total: WHISPER.downloadBytes, stage: info.file });
  };
  // Quantized (q8) Whisper runs on the WASM backend; its integer kernels are not WebGPU kernels.
  recognizer = oneAtATime(() => pipeline("automatic-speech-recognition", WHISPER.directory, {
    device: "wasm",
    dtype: WHISPER.dtype,
    local_files_only: true,
    progress_callback: onProgress,
  }) as Promise<AutomaticSpeechRecognitionPipeline>).then((loaded) => {
    post({ type: "ready", component: "stt", backend: "wasm", ms: performance.now() - started });
    return loaded;
  });
  recognizer.catch((error) => {
    recognizer = null;
    post({ type: "load-error", component: "stt", message: describe(error) });
  });
  return recognizer;
}

function loadSynthesizer(requested?: InferenceBackend): Promise<EmaLightning> {
  if (synthesizer) return synthesizer;
  const started = performance.now();
  const base = `${VOICE_MODELS_BASE}${EMA_LIGHTNING.directory}/`;
  const cacheName = `modai-voice-ema-${EMA_LIGHTNING.revision.slice(0, 8)}`;
  const progress = (stage: string, fraction: number) =>
    post({ type: "progress", component: "tts", loaded: Math.round(fraction * EMA_LIGHTNING.downloadBytes), total: EMA_LIGHTNING.downloadBytes, stage });
  synthesizer = oneAtATime(async () => {
    const backend: InferenceBackend = requested ?? ((await webgpuAvailable()) ? "webgpu" : "wasm");
    try {
      return await EmaLightning.load(backend, base, cacheName, progress);
    } catch (error) {
      if (backend === "wasm") throw error;
      return EmaLightning.load("wasm", base, cacheName, progress); // WebGPU adapter present but unusable
    }
  }).then((engine) => {
    post({ type: "ready", component: "tts", backend: engine.backend, ms: performance.now() - started });
    return engine;
  });
  synthesizer.catch((error) => {
    synthesizer = null;
    post({ type: "load-error", component: "tts", message: describe(error) });
  });
  return synthesizer;
}

async function transcribe(id: number, audio: Float32Array) {
  try {
    const started = performance.now();
    const asr = await loadRecognizer();
    const startedAt = clock();
    const output = await asr(audio, { language: WHISPER.language, task: "transcribe" });
    const text = (Array.isArray(output) ? output.map((item) => item.text).join(" ") : output.text).trim();
    post({ type: "transcript", id, text, ms: performance.now() - started, startedAt, endedAt: clock() });
  } catch (error) {
    post({ type: "transcribe-error", id, message: describe(error) });
  }
}

async function speak(id: number, seq: number, text: string) {
  if (id <= cancelledUpTo) return;
  try {
    const started = performance.now();
    const engine = await loadSynthesizer();
    const synthStartedAt = clock();
    for await (const samples of engine.stream(text)) {
      if (id <= cancelledUpTo) return; // a newer request or stop: drop the rest of this sentence
      post({ type: "audio", id, seq, samples, sampleRate: RATE, synthStartedAt, postedAt: clock() }, [samples.buffer as ArrayBuffer]);
    }
    if (id > cancelledUpTo) post({ type: "spoken", id, seq, ms: performance.now() - started });
  } catch (error) {
    post({ type: "speak-error", id, seq, message: describe(error) });
  }
}

scope.onmessage = (event: MessageEvent<WorkerRequest>) => {
  const request = event.data;
  if (request.type === "load") {
    const component: VoiceComponent = request.component;
    void (component === "stt" ? loadRecognizer() : loadSynthesizer(request.backend)).catch(() => undefined);
  } else if (request.type === "transcribe") {
    work = work.then(() => transcribe(request.id, request.audio));
  } else if (request.type === "speak") {
    work = work.then(() => speak(request.id, request.seq, request.text));
  } else if (request.type === "cancel") {
    cancelledUpTo = Math.max(cancelledUpTo, request.upTo);
  }
};
