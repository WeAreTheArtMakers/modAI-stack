// Voice models are self-hosted, revision-pinned files (see voice-models.lock.json and
// scripts/fetch_voice_models.py). Paths include the revision so browser caches never mix
// two model versions. Nothing here is fetched from a third-party host.

export const VOICE_MODELS_BASE = "/voice-models/";

export type SttModelId = "tiny" | "base";

export interface WhisperModel {
  label: string;
  repository: string;
  revision: string;
  directory: string;
  dtype: "q8";
  downloadBytes: number; // WASM: q8 encoder and decoder
  webgpuDownloadBytes: number; // WebGPU: fp16 encoder, q8 decoder
}

// Multilingual Whisper (never the English-only ".en" variants). Tiny is the default; base is an
// optional, more accurate and slower model for evaluation (fetched with --include-optional).
export const WHISPER_MODELS: Record<SttModelId, WhisperModel> = {
  tiny: {
    label: "Whisper Tiny",
    repository: "Xenova/whisper-tiny",
    revision: "5332fcc35e32a33b86612b9a57a89be7906102b1",
    directory: "whisper-tiny-5332fcc3",
    dtype: "q8",
    downloadBytes: 43_622_127,
    webgpuDownloadBytes: 50_016_993,
  },
  base: {
    label: "Whisper Base",
    repository: "Xenova/whisper-base",
    revision: "64da57285918e20ea79ea5c88eed7197933abaa8",
    directory: "whisper-base-64da5728",
    dtype: "q8",
    downloadBytes: 79_677_901,
    webgpuDownloadBytes: 97_810_249,
  },
};
export const DEFAULT_STT_MODEL: SttModelId = "tiny";
export const WHISPER_LANGUAGE = "turkish";

export function isSttModel(value: unknown): value is SttModelId {
  return value === "tiny" || value === "base";
}

export const EMA_LIGHTNING = {
  repository: "ozcancelik/ema-lightning-onnx",
  revision: "13c431db0356b2f7fafb1247cd823ec0d777c820",
  directory: "ema-lightning-13c431db",
  sampleRate: 48_000,
  downloadBytes: 36_171_095,
} as const;

// onnxruntime-web 1.30.0 WebGPU build (also runs the WASM backend), bundled by Vite.
export const ORT_RUNTIME_BYTES = 26_781_914;

export const RECORDING_LIMIT_MS = 30_000; // Whisper decodes one 30-second window
export const WHISPER_SAMPLE_RATE = 16_000;
export const VOICE_READY_STORAGE_KEY = "modai.voice.models.v1";
export const VOICE_SPEED_STORAGE_KEY = "modai.voice.speed";
export const VOICE_REVIEW_STORAGE_KEY = "modai.voice.review";
export const VOICE_LANGUAGE_STORAGE_KEY = "modai.voice.answer-language";
export const VOICE_STT_MODEL_STORAGE_KEY = "modai.voice.stt-model";
// Voice conversations live in the assistant-conversation store; the prefix marks them for /voice.
export const VOICE_TITLE_PREFIX = "Sesli görüşme: ";
export const SPEECH_SPEEDS = [1, 1.05, 1.1, 1.15] as const;
export const DEFAULT_SPEECH_SPEED = 1.05; // EMA at 1.00 already reads ~6.8 syllables/s; 1.10 and 1.15 stay selectable
