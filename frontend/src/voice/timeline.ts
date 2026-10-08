// Per-turn latency marks. Times are absolute (performance.timeOrigin + performance.now()) so
// marks taken in the voice worker and on the page compare directly. Only numbers are kept:
// never audio, question text, answers or document content.

export type TimelineMark =
  | "recordStart" | "recordStop" | "audioReady" | "sttStart" | "sttEnd" | "transcriptReceived"
  | "ragStart" | "ragSent" | "sources" | "firstToken" | "firstPhrase"
  | "ttsStart" | "firstBufferPosted" | "firstBufferReceived" | "firstAudible"
  | "ragComplete" | "speechEnd";

export type Timeline = Partial<Record<TimelineMark, number>>;

export const clock = () => performance.timeOrigin + performance.now();

const STAGES: [name: string, from: TimelineMark | "userStop", to: TimelineMark][] = [
  ["recording", "recordStart", "recordStop"],
  ["stopToSttStart", "recordStop", "sttStart"],
  ["stt", "sttStart", "sttEnd"],
  ["sttToRagStart", "sttEnd", "ragStart"],
  ["ragConnect", "ragStart", "ragSent"],
  ["ragToFirstToken", "ragStart", "firstToken"],
  ["firstTokenToPhrase", "firstToken", "firstPhrase"],
  ["phraseToTtsStart", "firstPhrase", "ttsStart"],
  ["ttsToFirstBuffer", "ttsStart", "firstBufferPosted"],
  ["bufferToAudible", "firstBufferPosted", "firstAudible"],
  ["stopToFirstAudible", "userStop", "firstAudible"],
  ["answerGeneration", "ragStart", "ragComplete"],
  ["playback", "firstAudible", "speechEnd"],
  ["stopToSpeechEnd", "userStop", "speechEnd"],
];

/** Stage durations in ms; "userStop" is the end of speech, or the moment a typed question was sent. */
export function stageDurations(timeline: Timeline): Record<string, number> {
  const userStop = timeline.recordStop ?? timeline.ragStart;
  const out: Record<string, number> = {};
  for (const [name, from, to] of STAGES) {
    const start = from === "userStop" ? userStop : timeline[from];
    const end = timeline[to];
    if (start !== undefined && end !== undefined) out[name] = Math.round(end - start);
  }
  return out;
}

export const VOICE_DEBUG_STORAGE_KEY = "modai.voice.debug";

/** Opt-in (localStorage "modai.voice.debug" = "1"): keep numeric stage timings on window for diagnosis. */
export function recordDebugTiming(entry: Record<string, unknown>) {
  try {
    if (window.localStorage.getItem(VOICE_DEBUG_STORAGE_KEY) !== "1") return;
  } catch {
    return;
  }
  const target = window as unknown as { __modaiVoiceTimings?: Record<string, unknown>[] };
  (target.__modaiVoiceTimings ??= []).push(entry);
}
