import { MicrophoneError, MICROPHONE_MESSAGES, measureAudio, type RecordedAudio, type Recorder } from "./microphone";

/**
 * Measurement-only stand-in for the microphone, compiled in only when the build sets
 * VITE_VOICE_REPLAY=1. stop() returns the next prepared 16 kHz clip from
 * window.__modaiVoiceReplay; everything after capture (STT, RAG, TTS, playback) is real.
 */
export class ReplayRecorder implements Recorder {
  recording = false;

  async start(): Promise<void> {
    this.recording = true;
  }

  async stop(): Promise<RecordedAudio> {
    this.recording = false;
    const queue = (window as unknown as { __modaiVoiceReplay?: Float32Array[] }).__modaiVoiceReplay;
    const next = queue?.shift();
    if (!next) throw new MicrophoneError("too_short", MICROPHONE_MESSAGES.too_short);
    return { samples: next, diagnostics: { ...measureAudio(next), finalizeMs: 0, decodeMs: 0 } };
  }

  cancel() {
    this.recording = false;
  }

  level(): number {
    return this.recording ? 0.3 : 0;
  }
}
