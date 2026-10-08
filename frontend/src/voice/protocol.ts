// Messages between the main thread and voice.worker.ts. Audio is transferred, never copied
// to the network: the worker only fetches self-hosted model files. Timestamps are absolute
// (performance.timeOrigin + performance.now()) so worker and page times are comparable.

export type VoiceComponent = "stt" | "tts";
export type InferenceBackend = "webgpu" | "wasm";

export type WorkerRequest =
  | { type: "load"; component: VoiceComponent; backend?: InferenceBackend }
  | { type: "transcribe"; id: number; audio: Float32Array }
  | { type: "speak"; id: number; seq: number; text: string; speed?: number }
  | { type: "cancel"; upTo: number };

export type WorkerResponse =
  | { type: "progress"; component: VoiceComponent; loaded: number; total: number; stage: string }
  | { type: "ready"; component: VoiceComponent; backend: InferenceBackend; ms: number }
  | { type: "load-error"; component: VoiceComponent; message: string }
  | { type: "transcript"; id: number; text: string; ms: number; startedAt: number; endedAt: number }
  | { type: "transcribe-error"; id: number; message: string }
  | { type: "audio"; id: number; seq: number; samples: Float32Array; sampleRate: number; synthStartedAt: number; postedAt: number }
  | { type: "spoken"; id: number; seq: number; ms: number }
  | { type: "speak-error"; id: number; seq: number; message: string };
