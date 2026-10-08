import { RECORDING_LIMIT_MS, WHISPER_SAMPLE_RATE } from "./config";

export type MicrophoneErrorCode = "insecure_context" | "unsupported" | "permission_denied" | "no_microphone" | "microphone_busy" | "too_short" | "decode_failed";

export class MicrophoneError extends Error {
  constructor(readonly code: MicrophoneErrorCode, message: string) {
    super(message);
    this.name = "MicrophoneError";
  }
}

export const MICROPHONE_MESSAGES: Record<MicrophoneErrorCode, string> = {
  insecure_context: "Mikrofon yalnızca güvenli bağlantıda (HTTPS veya localhost) kullanılabilir.",
  unsupported: "Bu tarayıcı mikrofon kaydını desteklemiyor. Sorunuzu yazarak sorabilirsiniz.",
  permission_denied: "Mikrofon izni verilmedi. Tarayıcının adres çubuğundaki izin simgesinden mikrofonu açabilirsiniz.",
  no_microphone: "Kullanılabilir bir mikrofon bulunamadı.",
  microphone_busy: "Mikrofon başka bir uygulama tarafından kullanılıyor.",
  too_short: "Ses algılanamadı. Mikrofon düğmesine basıp konuşun, bitince bırakın.",
  decode_failed: "Ses kaydı işlenemedi. Lütfen tekrar deneyin.",
};

function classify(error: unknown): MicrophoneError {
  const name = error instanceof DOMException || error instanceof Error ? error.name : "";
  if (name === "NotAllowedError" || name === "SecurityError") return new MicrophoneError("permission_denied", MICROPHONE_MESSAGES.permission_denied);
  if (name === "NotFoundError" || name === "OverconstrainedError") return new MicrophoneError("no_microphone", MICROPHONE_MESSAGES.no_microphone);
  if (name === "NotReadableError" || name === "AbortError") return new MicrophoneError("microphone_busy", MICROPHONE_MESSAGES.microphone_busy);
  return new MicrophoneError("unsupported", MICROPHONE_MESSAGES.unsupported);
}

export interface Recorder {
  /** Starts recording after an explicit user gesture; the browser asks for permission. */
  start(onLimit: () => void): Promise<void>;
  /** Stops recording and returns 16 kHz mono samples for Whisper. Audio never leaves the browser. */
  stop(): Promise<Float32Array>;
  cancel(): void;
  level(): number;
  readonly recording: boolean;
}

export class MicrophoneRecorder implements Recorder {
  private stream: MediaStream | null = null;
  private recorder: MediaRecorder | null = null;
  private chunks: Blob[] = [];
  private meterContext: AudioContext | null = null;
  private analyser: AnalyserNode | null = null;
  private limitTimer: number | undefined;
  private meterBuffer = new Float32Array(1024);

  get recording(): boolean {
    return this.recorder?.state === "recording";
  }

  async start(onLimit: () => void): Promise<void> {
    if (!window.isSecureContext) throw new MicrophoneError("insecure_context", MICROPHONE_MESSAGES.insecure_context);
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") throw new MicrophoneError("unsupported", MICROPHONE_MESSAGES.unsupported);
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
    } catch (error) {
      throw classify(error);
    }
    this.chunks = [];
    this.recorder = new MediaRecorder(this.stream);
    this.recorder.ondataavailable = (event) => { if (event.data.size) this.chunks.push(event.data); };
    this.recorder.start();
    try {
      this.meterContext = new AudioContext();
      this.analyser = this.meterContext.createAnalyser();
      this.analyser.fftSize = 1024;
      this.meterContext.createMediaStreamSource(this.stream).connect(this.analyser);
    } catch {
      this.analyser = null; // the level meter is cosmetic
    }
    this.limitTimer = window.setTimeout(onLimit, RECORDING_LIMIT_MS);
  }

  level(): number {
    if (!this.analyser) return 0;
    this.analyser.getFloatTimeDomainData(this.meterBuffer);
    let sum = 0;
    for (const value of this.meterBuffer) sum += value * value;
    return Math.min(1, Math.sqrt(sum / this.meterBuffer.length) * 6);
  }

  private release() {
    window.clearTimeout(this.limitTimer);
    this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = null;
    void this.meterContext?.close().catch(() => undefined);
    this.meterContext = null;
    this.analyser = null;
  }

  async stop(): Promise<Float32Array> {
    const recorder = this.recorder;
    if (!recorder) throw new MicrophoneError("too_short", MICROPHONE_MESSAGES.too_short);
    const stopped = new Promise<void>((resolve) => { recorder.onstop = () => resolve(); });
    if (recorder.state !== "inactive") recorder.stop();
    await stopped;
    this.recorder = null;
    this.release();
    const blob = new Blob(this.chunks, { type: recorder.mimeType });
    this.chunks = [];
    if (!blob.size) throw new MicrophoneError("too_short", MICROPHONE_MESSAGES.too_short);
    let decoded: AudioBuffer;
    const context = new AudioContext({ sampleRate: WHISPER_SAMPLE_RATE });
    try {
      decoded = await context.decodeAudioData(await blob.arrayBuffer()); // resampled to 16 kHz
    } catch {
      throw new MicrophoneError("decode_failed", MICROPHONE_MESSAGES.decode_failed);
    } finally {
      void context.close().catch(() => undefined);
    }
    // Mono 16 kHz for Whisper: one copy for mono input, an average for multichannel input.
    let samples: Float32Array;
    if (decoded.numberOfChannels === 1) {
      samples = decoded.getChannelData(0).slice();
    } else {
      samples = new Float32Array(decoded.length);
      for (let channel = 0; channel < decoded.numberOfChannels; channel++) {
        const data = decoded.getChannelData(channel);
        for (let i = 0; i < data.length; i++) samples[i] += data[i] / decoded.numberOfChannels;
      }
    }
    if (samples.length < WHISPER_SAMPLE_RATE * 0.4) throw new MicrophoneError("too_short", MICROPHONE_MESSAGES.too_short);
    return samples;
  }

  cancel() {
    if (this.recorder && this.recorder.state !== "inactive") {
      this.recorder.onstop = null;
      this.recorder.stop();
    }
    this.recorder = null;
    this.chunks = [];
    this.release();
  }
}

/**
 * Trims leading and trailing silence (keeping 250 ms of margin) from 16 kHz mono audio. Whisper
 * tends to invent words for long silences. Returns the input unchanged if no speech is found or
 * the result would be shorter than 0.4 s.
 */
export function trimSilence(samples: Float32Array, sampleRate = WHISPER_SAMPLE_RATE): Float32Array {
  const frame = Math.round(sampleRate * 0.02);
  const frames = Math.floor(samples.length / frame);
  if (frames < 10) return samples;
  const energy = new Float32Array(frames);
  for (let f = 0; f < frames; f++) {
    let sum = 0;
    for (let i = f * frame; i < (f + 1) * frame; i++) sum += samples[i] * samples[i];
    energy[f] = Math.sqrt(sum / frame);
  }
  const sorted = Float32Array.from(energy).sort();
  const noise = sorted[Math.floor(frames * 0.1)];
  const threshold = Math.max(0.01, noise * 3);
  let first = 0;
  while (first < frames && energy[first] < threshold) first++;
  let last = frames - 1;
  while (last > first && energy[last] < threshold) last--;
  if (first >= frames) return samples;
  const margin = Math.round(0.25 * sampleRate);
  const start = Math.max(0, first * frame - margin);
  const end = Math.min(samples.length, (last + 1) * frame + margin);
  if (end - start < sampleRate * 0.4 || (start === 0 && end === samples.length)) return samples;
  return samples.subarray(start, end).slice();
}
