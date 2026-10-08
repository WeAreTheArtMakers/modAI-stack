// Voice models are self-hosted, revision-pinned files (see voice-models.lock.json and
// scripts/fetch_voice_models.py). Paths include the revision so browser caches never mix
// two model versions. Nothing here is fetched from a third-party host.

export const VOICE_MODELS_BASE = "/voice-models/";

export const WHISPER = {
  // Multilingual Whisper tiny (never the English-only ".en" variant).
  repository: "Xenova/whisper-tiny",
  revision: "5332fcc35e32a33b86612b9a57a89be7906102b1",
  directory: "whisper-tiny-5332fcc3",
  language: "turkish",
  dtype: "q8",
  downloadBytes: 43_622_127,
} as const;

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
