// Per-turn latency marks. Times are absolute (performance.timeOrigin + performance.now()) so
// marks taken in the voice worker and on the page compare directly. Only numbers are kept:
// never audio, question text, answers or document content.

export type TimelineMark =
  | "recordStart" | "recordStop" | "audioReady"
  | "sttPosted" | "sttReceived" | "sttStart" | "sttEnd" | "transcriptReceived"
  | "askStart" | "conversationStart" | "conversationReady"
  | "ragStart" | "ragTicket" | "ragOpen" | "ragSent" | "sources" | "firstToken" | "firstPhrase"
  | "ttsStart" | "firstBufferPosted" | "firstBufferReceived" | "firstAudible"
  | "ragComplete" | "speechEnd";

export type Timeline = Partial<Record<TimelineMark, number>>;

export const clock = () => performance.timeOrigin + performance.now();

/** [stage, from, to]; "userStop" is the end of speech, or the moment a typed question was sent. */
export const STAGES: [name: string, from: TimelineMark | "userStop", to: TimelineMark][] = [
  ["recording", "recordStart", "recordStop"],
  ["sttCapture", "recordStop", "audioReady"], // MediaRecorder finalize + decode/resample
  ["sttTransferIn", "sttPosted", "sttReceived"],
  ["sttQueueWait", "sttReceived", "sttStart"], // waiting for the model or another inference
  ["sttInference", "sttStart", "sttEnd"],
  ["sttTransferBack", "sttEnd", "transcriptReceived"],
  ["review", "transcriptReceived", "askStart"], // user reading/correcting the transcript
  ["conversationCreate", "conversationStart", "conversationReady"],
  ["ragTicket", "ragStart", "ragTicket"],
  ["ragConnect", "ragTicket", "ragOpen"],
  ["ragServerToSources", "ragSent", "sources"], // authorization, embedding, Qdrant, prompt
  ["sourcesToFirstToken", "sources", "firstToken"], // model load (if cold) + prompt prefill
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

/** Stage durations in ms, for every stage whose two marks exist. */
export function stageDurations(timeline: Timeline): Record<string, number> {
  const userStop = timeline.recordStop ?? timeline.askStart;
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
