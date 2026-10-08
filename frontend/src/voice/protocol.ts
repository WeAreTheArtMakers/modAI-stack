// Messages between the main thread and voice.worker.ts. Audio is transferred, never copied
// to the network: the worker only fetches self-hosted model files. Timestamps are absolute
// (performance.timeOrigin + performance.now()) so worker and page times are comparable.

import type { SttModelId } from "./config";

export type VoiceComponent = "stt" | "tts";
export type InferenceBackend = "webgpu" | "wasm";

export type WorkerRequest =
  // For "stt", `model` selects the Whisper model; loading another model releases the current one.
  | { type: "load"; component: VoiceComponent; backend?: InferenceBackend; model?: SttModelId }
  | { type: "transcribe"; id: number; audio: Float32Array }
  | { type: "speak"; id: number; seq: number; text: string; speed?: number }
  | { type: "cancel"; upTo: number };

export type WorkerResponse =
  | { type: "progress"; component: VoiceComponent; loaded: number; total: number; stage: string; model?: SttModelId }
  | { type: "ready"; component: VoiceComponent; backend: InferenceBackend; ms: number; model?: SttModelId }
  | { type: "load-error"; component: VoiceComponent; message: string; model?: SttModelId }
  | {
      type: "transcript"; id: number; text: string; ms: number;
      receivedAt: number; startedAt: number; endedAt: number; // worker queue wait = startedAt - receivedAt
      warm: boolean; backend: InferenceBackend; audioSeconds: number; model: SttModelId;
    }
  | { type: "transcribe-error"; id: number; message: string }
  | { type: "audio"; id: number; seq: number; samples: Float32Array; sampleRate: number; synthStartedAt: number; postedAt: number }
  | { type: "spoken"; id: number; seq: number; ms: number }
  | { type: "speak-error"; id: number; seq: number; message: string };
