import { DEFAULT_STT_MODEL, type SttModelId } from "./config";
import type { InferenceBackend, VoiceComponent, WorkerRequest, WorkerResponse } from "./protocol";

export type LoadStatus = "idle" | "loading" | "ready" | "error";

export interface LoadState {
  status: LoadStatus;
  loaded: number;
  total: number;
  backend?: InferenceBackend;
  ms?: number;
  message?: string;
  model?: SttModelId; // speech recognition only
}

export const IDLE_LOAD: LoadState = { status: "idle", loaded: 0, total: 0 };

export interface AudioTiming { synthStartedAt: number; postedAt: number }
export type AudioSink = (samples: Float32Array, sampleRate: number, timing?: AudioTiming) => void;
export interface Transcript {
  text: string;
  ms: number;
  postedAt?: number; // absolute times (see timeline.ts)
  receivedAt?: number;
  startedAt?: number;
  endedAt?: number;
  warm?: boolean;
  backend?: InferenceBackend;
  model?: SttModelId;
}

/** A speech-recognition load that was replaced by a load of another model. */
export class LoadSuperseded extends Error {}

export interface VoiceEngine {
  /** For "stt", `model` selects the Whisper model (default: the current one, else tiny); another model replaces the loaded one. */
  load(component: VoiceComponent, onState: (state: LoadState) => void, model?: SttModelId): Promise<InferenceBackend>;
  transcribe(audio: Float32Array): Promise<Transcript>;
  /** Resolves when the sentence is fully synthesized, or immediately once it is cancelled. */
  speak(requestId: number, seq: number, text: string, onAudio: AudioSink, speed?: number): Promise<void>;
  /** Drops queued and in-progress synthesis for every request id <= upTo. */
  cancel(upTo: number): void;
  dispose(): void;
}

interface Deferred<T> {
  resolve(value: T): void;
  reject(reason: Error): void;
}

export class WorkerVoiceEngine implements VoiceEngine {
  private worker: Worker | null = null;
  private nextTranscription = 0;
  private readonly loads = new Map<VoiceComponent, { promise: Promise<InferenceBackend>; deferred: Deferred<InferenceBackend>; listeners: Set<(state: LoadState) => void>; state: LoadState }>();
  private readonly transcriptions = new Map<number, Deferred<Transcript>>();
  private readonly transcriptPosted = new Map<number, number>();
  private readonly speeches = new Map<string, { deferred: Deferred<void>; onAudio: AudioSink; id: number }>();
  private sttModel: SttModelId | null = null;

  constructor(private readonly createWorker: () => Worker = () => new Worker(new URL("./voice.worker.ts", import.meta.url), { type: "module" })) {}

  private send(message: WorkerRequest, transfer: ArrayBuffer[] = []) {
    if (!this.worker) {
      this.worker = this.createWorker();
      this.worker.onmessage = (event: MessageEvent<WorkerResponse>) => this.receive(event.data);
      this.worker.onerror = (event) => this.failAll(event.message || "Ses motoru başlatılamadı.");
    }
    this.worker.postMessage(message, transfer);
  }

  private updateLoad(component: VoiceComponent, patch: Partial<LoadState>) {
    const entry = this.loads.get(component);
    if (!entry) return;
    entry.state = { ...entry.state, ...patch };
    for (const listener of entry.listeners) listener(entry.state);
  }

  private receive(message: WorkerResponse) {
    // Progress and results of a recognition model that was since replaced are stale.
    if ((message.type === "progress" || message.type === "ready" || message.type === "load-error") && message.component === "stt" && message.model !== undefined && message.model !== this.sttModel) return;
    switch (message.type) {
      case "progress":
        this.updateLoad(message.component, { status: "loading", loaded: message.loaded, total: message.total });
        break;
      case "ready": {
        this.updateLoad(message.component, { status: "ready", backend: message.backend, ms: message.ms, model: message.model, loaded: this.loads.get(message.component)?.state.total ?? 0 });
        this.loads.get(message.component)?.deferred.resolve(message.backend);
        this.loads.get(message.component)?.listeners.clear();
        break;
      }
      case "load-error": {
        const entry = this.loads.get(message.component);
        this.updateLoad(message.component, { status: "error", message: message.message });
        entry?.deferred.reject(new Error(message.message));
        this.loads.delete(message.component); // allow a retry
        break;
      }
      case "transcript":
        this.transcriptions.get(message.id)?.resolve({
          text: message.text, ms: message.ms, postedAt: this.transcriptPosted.get(message.id), receivedAt: message.receivedAt,
          startedAt: message.startedAt, endedAt: message.endedAt, warm: message.warm, backend: message.backend, model: message.model,
        });
        this.transcriptPosted.delete(message.id);
        this.transcriptions.delete(message.id);
        break;
      case "transcribe-error":
        this.transcriptions.get(message.id)?.reject(new Error(message.message));
        this.transcriptions.delete(message.id);
        break;
      case "audio":
        this.speeches.get(`${message.id}:${message.seq}`)?.onAudio(message.samples, message.sampleRate, { synthStartedAt: message.synthStartedAt, postedAt: message.postedAt });
        break;
      case "spoken":
        this.speeches.get(`${message.id}:${message.seq}`)?.deferred.resolve();
        this.speeches.delete(`${message.id}:${message.seq}`);
        break;
      case "speak-error":
        this.speeches.get(`${message.id}:${message.seq}`)?.deferred.reject(new Error(message.message));
        this.speeches.delete(`${message.id}:${message.seq}`);
        break;
    }
  }

  private failAll(reason: string) {
    const error = new Error(reason);
    for (const [component, entry] of this.loads) {
      if (entry.state.status !== "ready") {
        this.updateLoad(component, { status: "error", message: reason });
        entry.deferred.reject(error);
        this.loads.delete(component);
      }
    }
    for (const deferred of this.transcriptions.values()) deferred.reject(error);
    this.transcriptions.clear();
    for (const speech of this.speeches.values()) speech.deferred.reject(error);
    this.speeches.clear();
  }

  load(component: VoiceComponent, onState: (state: LoadState) => void, model?: SttModelId): Promise<InferenceBackend> {
    let entry = this.loads.get(component);
    if (component === "stt") {
      const wanted = model ?? this.sttModel ?? DEFAULT_STT_MODEL;
      if (entry && this.sttModel !== wanted) {
        // The worker releases the current model before it loads the new one.
        entry.listeners.clear();
        if (entry.state.status !== "ready") entry.deferred.reject(new LoadSuperseded(`${this.sttModel} replaced by ${wanted}`));
        this.loads.delete(component);
        entry = undefined;
      }
      this.sttModel = wanted;
    }
    if (!entry) {
      let deferred!: Deferred<InferenceBackend>;
      const promise = new Promise<InferenceBackend>((resolve, reject) => { deferred = { resolve, reject }; });
      promise.catch(() => undefined); // a superseded load may have no listener left
      const sttModel = component === "stt" ? this.sttModel ?? DEFAULT_STT_MODEL : undefined;
      entry = { promise, deferred, listeners: new Set(), state: { status: "loading", loaded: 0, total: 0, model: sttModel } };
      this.loads.set(component, entry);
      this.send(sttModel ? { type: "load", component, model: sttModel } : { type: "load", component });
    }
    // Once loaded, later callers (e.g. a remounted page) only need the current state.
    if (entry.state.status !== "ready") entry.listeners.add(onState);
    onState(entry.state);
    return entry.promise;
  }

  transcribe(audio: Float32Array): Promise<Transcript> {
    const id = ++this.nextTranscription;
    return new Promise((resolve, reject) => {
      this.transcriptions.set(id, { resolve, reject });
      this.transcriptPosted.set(id, performance.timeOrigin + performance.now());
      this.send({ type: "transcribe", id, audio }, [audio.buffer as ArrayBuffer]);
    });
  }

  speak(requestId: number, seq: number, text: string, onAudio: AudioSink, speed = 1): Promise<void> {
    return new Promise((resolve, reject) => {
      this.speeches.set(`${requestId}:${seq}`, { deferred: { resolve, reject }, onAudio, id: requestId });
      this.send({ type: "speak", id: requestId, seq, text, speed });
    });
  }

  cancel(upTo: number) {
    for (const [key, speech] of this.speeches) {
      if (speech.id <= upTo) {
        speech.deferred.resolve();
        this.speeches.delete(key);
      }
    }
    if (this.worker) this.send({ type: "cancel", upTo });
  }

  dispose() {
    this.cancel(Number.MAX_SAFE_INTEGER);
    this.worker?.terminate();
    this.worker = null;
    this.loads.clear();
    this.sttModel = null;
  }
}

let shared: WorkerVoiceEngine | null = null;

/** One voice worker per tab: warmed models survive leaving and reopening the voice page. */
export function sharedVoiceEngine(): WorkerVoiceEngine {
  shared ??= new WorkerVoiceEngine();
  return shared;
}
