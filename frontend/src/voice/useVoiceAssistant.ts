import { useCallback, useEffect, useRef, useState } from "react";
import { streamRag } from "../api/websocket";
import type { Source } from "../types";
import { WebAudioPlayer, type Player } from "./audioPlayback";
import { DEFAULT_SPEECH_SPEED, SPEECH_SPEEDS, VOICE_READY_STORAGE_KEY, VOICE_REVIEW_STORAGE_KEY, VOICE_SPEED_STORAGE_KEY } from "./config";
import { MicrophoneError, MicrophoneRecorder, trimSilence, type Recorder } from "./microphone";
import type { InferenceBackend } from "./protocol";
import { ReplayRecorder } from "./replayRecorder";
import { SentenceBuffer } from "./sentenceBuffer";
import { BrowserSystemVoice, type SystemVoice } from "./systemVoice";
import { clock, recordDebugTiming, stageDurations, type Timeline } from "./timeline";
import { IDLE_LOAD, sharedVoiceEngine, type LoadState, type VoiceEngine } from "./voiceEngine";

export type VoicePhase = "idle" | "listening" | "transcribing" | "reviewing" | "searching" | "answering" | "speaking" | "error";
export type SpeechMode = "neural" | "system" | "off";

export interface VoiceDependencies {
  engine: VoiceEngine;
  recorder: Recorder;
  player: Player;
  systemVoice: SystemVoice;
  streamRag: typeof streamRag;
}

export function createBrowserVoiceDependencies(): VoiceDependencies {
  const recorder = import.meta.env.VITE_VOICE_REPLAY === "1" ? new ReplayRecorder() : new MicrophoneRecorder();
  return { engine: sharedVoiceEngine(), recorder, player: new WebAudioPlayer(), systemVoice: new BrowserSystemVoice(), streamRag };
}

export interface TurnMetrics {
  recordingMs?: number;
  sttMs?: number;
  firstTokenMs?: number; // question sent -> first RAG token
  firstAudioMs?: number; // end of user speech (or question sent) -> first audible answer
  completeMs?: number; // end of user speech (or question sent) -> answer fully spoken
  speech?: SpeechMode;
  speed?: number;
  stages?: Record<string, number>; // see timeline.ts
}

export interface VoiceTurn {
  id: number;
  origin: "voice" | "text";
  question: string;
  answer: string;
  sources: Source[];
  streaming: boolean;
  stopped?: boolean;
  corrected?: boolean;
  error?: string;
  phrases: number; // speakable phrases produced from the answer
  spokenPhrases: number; // phrases whose audio actually reached the playback queue
  metrics: TurnMetrics;
}

interface PendingTranscript {
  text: string;
  stoppedAt: number;
  metrics: TurnMetrics;
  timeline: Timeline;
}

const NOT_UNDERSTOOD = "Konuşma anlaşılamadı. Lütfen tekrar deneyin.";
const NO_SOURCE = "Önce en az bir Knowledge Base seçin.";
const MAX_IN_FLIGHT = 2; // sentences handed to the synthesizer ahead of playback
const MAX_BUFFERED_SECONDS = 15; // synthesized audio waiting to be played

function stored(key: string): string | null {
  try { return window.localStorage.getItem(key); } catch { return null; }
}

function store(key: string, value: string) {
  try { window.localStorage.setItem(key, value); } catch { /* optional */ }
}

function storedSpeed(): number {
  const value = Number(stored(VOICE_SPEED_STORAGE_KEY));
  return (SPEECH_SPEEDS as readonly number[]).includes(value) ? value : DEFAULT_SPEECH_SPEED;
}

export function useVoiceAssistant(knowledgeBaseIds: number[], dependencies?: VoiceDependencies) {
  const depsRef = useRef<VoiceDependencies | null>(null);
  if (!depsRef.current) depsRef.current = dependencies ?? createBrowserVoiceDependencies();
  const deps = depsRef.current;

  const [phase, setPhaseState] = useState<VoicePhase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [turns, setTurns] = useState<VoiceTurn[]>([]);
  const [stt, setStt] = useState<LoadState>(IDLE_LOAD);
  const [tts, setTts] = useState<LoadState>(IDLE_LOAD);
  const [speechMode, setSpeechMode] = useState<SpeechMode>("neural");
  const [voiceEnabled, setVoiceEnabled] = useState(true);
  const [speed, setSpeedState] = useState(storedSpeed);
  const [review, setReviewState] = useState(() => stored(VOICE_REVIEW_STORAGE_KEY) === "1");
  const [pending, setPending] = useState<PendingTranscript | null>(null);

  const phaseRef = useRef<VoicePhase>("idle");
  const requestRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
  const speechModeRef = useRef<SpeechMode>("neural");
  const voiceEnabledRef = useRef(true);
  const speedRef = useRef(speed);
  const reviewRef = useRef(review);
  const kbRef = useRef(knowledgeBaseIds);
  const recordingRef = useRef<{ startedAt: number; stopRequested: boolean } | null>(null);
  kbRef.current = knowledgeBaseIds;

  const setPhase = useCallback((next: VoicePhase) => { phaseRef.current = next; setPhaseState(next); }, []);
  const updateTurn = useCallback((id: number, patch: (turn: VoiceTurn) => Partial<VoiceTurn>) => {
    setTurns((items) => items.map((turn) => (turn.id === id ? { ...turn, ...patch(turn) } : turn)));
  }, []);
  const updateMetrics = useCallback((id: number, metrics: TurnMetrics) => {
    updateTurn(id, (turn) => ({ metrics: { ...turn.metrics, ...metrics } }));
  }, [updateTurn]);

  const fail = useCallback((message: string) => { setError(message); setPhase("error"); }, [setPhase]);

  const prepare = useCallback(() => {
    void deps.engine.load("stt", setStt).catch(() => undefined);
    void deps.engine.load("tts", setTts).then(() => {
      speechModeRef.current = "neural";
      setSpeechMode("neural");
      store(VOICE_READY_STORAGE_KEY, "1");
    }).catch(() => {
      const fallback: SpeechMode = deps.systemVoice.available() ? "system" : "off";
      speechModeRef.current = fallback;
      setSpeechMode(fallback);
    });
  }, [deps]);

  /** Stops audio and generation for the current answer; nothing stale may play afterwards. */
  const stopCurrent = useCallback((reason: "stopped" | "superseded") => {
    const id = requestRef.current;
    abortRef.current?.abort();
    abortRef.current = null;
    deps.engine.cancel(id);
    deps.player.reset(-id); // no request ever uses a negative generation
    deps.systemVoice.cancel();
    if (reason === "stopped" && id) {
      const busy = ["searching", "answering", "speaking"].includes(phaseRef.current);
      updateTurn(id, (turn) => (turn.streaming || busy ? { streaming: false, stopped: true } : {}));
    }
  }, [deps, updateTurn]);

  const ask = useCallback(async (
    question: string,
    origin: "voice" | "text",
    startedAt = performance.now(),
    metrics: TurnMetrics = {},
    timeline: Timeline = {},
    corrected = false,
  ) => {
    const knowledgeBases = kbRef.current;
    if (!knowledgeBases.length) { fail(NO_SOURCE); return; }
    stopCurrent("superseded");
    setPending(null);
    const id = ++requestRef.current;
    const controller = new AbortController();
    abortRef.current = controller;
    deps.player.reset(id);
    const mode: SpeechMode = voiceEnabledRef.current ? speechModeRef.current : "off";
    const speechSpeed = speedRef.current;
    setError(null);
    setTurns((items) => [...items, { id, origin, question, answer: "", sources: [], streaming: true, corrected, phrases: 0, spokenPhrases: 0, metrics: { ...metrics, speech: mode, speed: speechSpeed } }]);
    setPhase("searching");

    const sentAt = performance.now();
    timeline.ragStart = clock();
    const buffer = new SentenceBuffer();
    const current = () => requestRef.current === id && !controller.signal.aborted;
    let firstToken = true;
    let firstAudio = true;
    let answerLength = 0;
    let phrases = 0;
    const spoken = new Set<number>();

    const audible = (absoluteAt: number) => {
      if (!firstAudio || !current()) return;
      firstAudio = false;
      timeline.firstAudible = absoluteAt;
      updateMetrics(id, { firstAudioMs: absoluteAt - performance.timeOrigin - startedAt });
      setPhase("speaking");
    };
    const markSpoken = (seq: number) => {
      if (spoken.has(seq)) return;
      spoken.add(seq);
      updateTurn(id, () => ({ spokenPhrases: spoken.size }));
    };

    // Neural speech: an ordered queue with backpressure. At most MAX_IN_FLIGHT phrases wait in
    // the synthesizer and at most MAX_BUFFERED_SECONDS of audio waits to be played.
    const queue: { seq: number; text: string }[] = [];
    let inFlight = 0;
    let streamDone = false;
    let retry: number | undefined;
    let finishSpeech!: () => void;
    const speechDone = new Promise<void>((resolve) => { finishSpeech = resolve; });
    const pump = () => {
      window.clearTimeout(retry);
      retry = undefined;
      if (!current()) { finishSpeech(); return; }
      while (queue.length && inFlight < MAX_IN_FLIGHT && deps.player.bufferedSeconds() < MAX_BUFFERED_SECONDS) {
        const { seq, text } = queue.shift()!;
        inFlight += 1;
        void deps.engine.speak(id, seq, text, (samples, rate, timing) => {
          if (timeline.firstBufferReceived === undefined && timing) {
            timeline.ttsStart = timing.synthStartedAt;
            timeline.firstBufferPosted = timing.postedAt;
            timeline.firstBufferReceived = clock();
          }
          const at = deps.player.enqueue(samples, rate, id);
          if (at === null) return;
          markSpoken(seq);
          audible(at);
        }, speechSpeed).catch(() => undefined).finally(() => { inFlight -= 1; pump(); });
      }
      if (queue.length && inFlight < MAX_IN_FLIGHT) retry = window.setTimeout(pump, 250); // let playback catch up
      else if (streamDone && !queue.length && !inFlight) finishSpeech();
    };
    let systemChain = Promise.resolve();

    const say = (sentence: string) => {
      timeline.firstPhrase ??= clock();
      const seq = phrases++;
      updateTurn(id, () => ({ phrases }));
      if (mode === "neural") {
        queue.push({ seq, text: sentence });
        pump();
      } else if (mode === "system") {
        systemChain = systemChain.then(() => (current()
          ? deps.systemVoice.speak(sentence, () => { markSpoken(seq); audible(clock()); }, speechSpeed)
          : undefined));
      }
    };
    const endOfAnswer = () => {
      streamDone = true;
      if (mode === "neural") pump();
    };

    try {
      await deps.streamRag(knowledgeBases, question, (event) => {
        if (!current()) return;
        if (event.type === "sources") {
          timeline.sources ??= clock();
          if (phaseRef.current === "searching") setPhase("answering");
          updateTurn(id, () => ({ sources: event.data }));
        } else if (event.type === "token") {
          if (firstToken) {
            firstToken = false;
            timeline.firstToken = clock();
            if (phaseRef.current === "searching") setPhase("answering");
            updateMetrics(id, { firstTokenMs: performance.now() - sentAt });
          }
          answerLength += event.data.length;
          updateTurn(id, (turn) => ({ answer: turn.answer + event.data }));
          buffer.push(event.data).forEach(say);
        } else if (event.type === "complete") {
          timeline.ragComplete = clock();
          buffer.flush().forEach(say);
          endOfAnswer();
          updateTurn(id, () => ({ streaming: false }));
        } else if (event.type === "error") {
          endOfAnswer();
          updateTurn(id, () => ({ streaming: false, error: event.data }));
        }
      }, controller.signal, { onSent: () => { timeline.ragSent = clock(); } });
      endOfAnswer();
      if (mode === "neural") {
        await speechDone;
        await deps.player.drained();
      } else if (mode === "system") {
        await systemChain;
      }
      if (!current()) return;
      timeline.speechEnd = clock();
      const stages = stageDurations(timeline);
      updateMetrics(id, { completeMs: performance.now() - startedAt, stages });
      recordDebugTiming({ id, origin, speech: mode, speed: speechSpeed, phrases, spokenPhrases: spoken.size, answerChars: answerLength, stages });
      setPhase("idle");
    } catch (reason) {
      if (!current()) return; // superseded or stopped by the user
      const message = reason instanceof Error ? reason.message : "Yanıt alınamadı.";
      updateTurn(id, () => ({ streaming: false, error: message }));
      fail(message);
    } finally {
      window.clearTimeout(retry);
      if (abortRef.current === controller) abortRef.current = null;
    }
  }, [deps, fail, setPhase, stopCurrent, updateMetrics, updateTurn]);

  const stopListening = useCallback(async () => {
    const recording = recordingRef.current;
    if (!recording) return;
    if (!deps.recorder.recording) { recording.stopRequested = true; return; } // permission prompt still open
    recordingRef.current = null;
    const stoppedAt = performance.now();
    const timeline: Timeline = { recordStart: recording.startedAt + performance.timeOrigin, recordStop: stoppedAt + performance.timeOrigin };
    setPhase("transcribing");
    try {
      const audio = trimSilence(await deps.recorder.stop());
      timeline.audioReady = clock();
      const result = await deps.engine.transcribe(audio);
      timeline.sttStart = result.startedAt;
      timeline.sttEnd = result.endedAt;
      timeline.transcriptReceived = clock();
      const metrics: TurnMetrics = { recordingMs: stoppedAt - recording.startedAt, sttMs: performance.now() - stoppedAt };
      if (!result.text) { fail(NOT_UNDERSTOOD); return; }
      if (reviewRef.current) {
        setPending({ text: result.text, stoppedAt, metrics, timeline });
        setPhase("reviewing");
        return;
      }
      await ask(result.text, "voice", stoppedAt, metrics, timeline);
    } catch (reason) {
      fail(reason instanceof MicrophoneError ? reason.message : `Konuşma yazıya çevrilemedi: ${reason instanceof Error ? reason.message : "bilinmeyen hata"}`);
    }
  }, [ask, deps, fail, setPhase]);

  const startListening = useCallback(async () => {
    if (recordingRef.current || phaseRef.current === "transcribing") return;
    if (!kbRef.current.length) { fail(NO_SOURCE); return; }
    stopCurrent("stopped"); // the microphone never records while an answer is playing
    setPending(null);
    deps.player.unlock();
    if (stt.status === "idle") prepare();
    setError(null);
    const recording = { startedAt: performance.now(), stopRequested: false };
    recordingRef.current = recording;
    setPhase("listening");
    try {
      await deps.recorder.start(() => { void stopListening(); });
    } catch (reason) {
      recordingRef.current = null;
      fail(reason instanceof MicrophoneError ? reason.message : "Mikrofon başlatılamadı.");
      return;
    }
    if (recording.stopRequested) await stopListening();
  }, [deps, fail, prepare, setPhase, stopCurrent, stopListening, stt.status]);

  const cancelListening = useCallback(() => {
    recordingRef.current = null;
    deps.recorder.cancel();
    setPhase("idle");
  }, [deps, setPhase]);

  const stop = useCallback(() => {
    stopCurrent("stopped");
    setPhase("idle");
  }, [setPhase, stopCurrent]);

  const askText = useCallback((question: string) => {
    deps.player.unlock();
    void ask(question.trim(), "text");
  }, [ask, deps]);

  /** Sends the reviewed, possibly edited, transcript. */
  const confirmTranscript = useCallback((text: string) => {
    const waiting = pending;
    if (!waiting || !text.trim()) return;
    deps.player.unlock();
    void ask(text.trim(), "voice", waiting.stoppedAt, waiting.metrics, waiting.timeline, text.trim() !== waiting.text);
  }, [ask, deps, pending]);

  const discardTranscript = useCallback(() => { setPending(null); setPhase("idle"); }, [setPhase]);

  /** Asks a corrected version of an earlier question; the current answer stops. */
  const correct = useCallback((turnId: number, text: string) => {
    const turn = turns.find((item) => item.id === turnId);
    if (!turn || !text.trim()) return;
    deps.player.unlock();
    void ask(text.trim(), turn.origin, performance.now(), {}, {}, true);
  }, [ask, deps, turns]);

  const toggleVoice = useCallback(() => {
    voiceEnabledRef.current = !voiceEnabledRef.current;
    setVoiceEnabled(voiceEnabledRef.current);
    if (!voiceEnabledRef.current && phaseRef.current === "speaking") stop();
  }, [stop]);

  const setSpeed = useCallback((value: number) => {
    speedRef.current = value;
    setSpeedState(value);
    store(VOICE_SPEED_STORAGE_KEY, String(value));
  }, []);

  const setReview = useCallback((value: boolean) => {
    reviewRef.current = value;
    setReviewState(value);
    store(VOICE_REVIEW_STORAGE_KEY, value ? "1" : "0");
  }, []);

  const dismissError = useCallback(() => { setError(null); setPhase("idle"); }, [setPhase]);

  useEffect(() => {
    if (stored(VOICE_READY_STORAGE_KEY) === "1") prepare(); // warm models come back from the browser cache
  }, [prepare]);

  useEffect(() => () => {
    abortRef.current?.abort();
    deps.recorder.cancel();
    deps.systemVoice.cancel();
    deps.player.dispose();
    deps.engine.cancel(requestRef.current); // the shared voice worker stays warm for the next visit
  }, [deps]);

  const level = useCallback(() => {
    if (phaseRef.current === "listening") return deps.recorder.level();
    if (phaseRef.current === "speaking") return speechModeRef.current === "system" ? -1 : deps.player.level();
    return 0;
  }, [deps]);

  const backend: InferenceBackend | undefined = tts.backend;
  return {
    phase, error, turns, stt, tts, speechMode, voiceEnabled, backend, speed, review, pending,
    systemVoiceName: deps.systemVoice.voiceName(),
    prepare, startListening, stopListening, cancelListening, stop, askText, confirmTranscript, discardTranscript, correct,
    toggleVoice, setSpeed, setReview, dismissError, level,
  };
}
