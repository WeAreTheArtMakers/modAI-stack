import type { InferenceBackend, VoiceComponent, WorkerRequest, WorkerResponse } from "./protocol";

export type LoadStatus = "idle" | "loading" | "ready" | "error";

export interface LoadState {
  status: LoadStatus;
  loaded: number;
  total: number;
  backend?: InferenceBackend;
  ms?: number;
  message?: string;
}

export const IDLE_LOAD: LoadState = { status: "idle", loaded: 0, total: 0 };

export interface AudioTiming { synthStartedAt: number; postedAt: number }
export type AudioSink = (samples: Float32Array, sampleRate: number, timing?: AudioTiming) => void;
export interface Transcript { text: string; ms: number; startedAt?: number; endedAt?: number }

export interface VoiceEngine {
  load(component: VoiceComponent, onState: (state: LoadState) => void): Promise<InferenceBackend>;
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
  private readonly speeches = new Map<string, { deferred: Deferred<void>; onAudio: AudioSink; id: number }>();

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
    switch (message.type) {
      case "progress":
        this.updateLoad(message.component, { status: "loading", loaded: message.loaded, total: message.total });
        break;
      case "ready": {
        this.updateLoad(message.component, { status: "ready", backend: message.backend, ms: message.ms, loaded: this.loads.get(message.component)?.state.total ?? 0 });
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
        this.transcriptions.get(message.id)?.resolve({ text: message.text, ms: message.ms, startedAt: message.startedAt, endedAt: message.endedAt });
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

  load(component: VoiceComponent, onState: (state: LoadState) => void): Promise<InferenceBackend> {
    let entry = this.loads.get(component);
    if (!entry) {
      let deferred!: Deferred<InferenceBackend>;
      const promise = new Promise<InferenceBackend>((resolve, reject) => { deferred = { resolve, reject }; });
      entry = { promise, deferred, listeners: new Set(), state: { status: "loading", loaded: 0, total: 0 } };
      this.loads.set(component, entry);
      this.send({ type: "load", component });
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
  }
}

let shared: WorkerVoiceEngine | null = null;

/** One voice worker per tab: warmed models survive leaving and reopening the voice page. */
export function sharedVoiceEngine(): WorkerVoiceEngine {
  shared ??= new WorkerVoiceEngine();
  return shared;
}
