import { useCallback, useEffect, useRef, useState } from "react";
import { streamRag } from "../api/websocket";
import type { Source } from "../types";
import { WebAudioPlayer, type Player } from "./audioPlayback";
import { VOICE_READY_STORAGE_KEY } from "./config";
import { MicrophoneError, MicrophoneRecorder, type Recorder } from "./microphone";
import type { InferenceBackend } from "./protocol";
import { SentenceBuffer } from "./sentenceBuffer";
import { BrowserSystemVoice, type SystemVoice } from "./systemVoice";
import { IDLE_LOAD, WorkerVoiceEngine, type LoadState, type VoiceEngine } from "./voiceEngine";

export type VoicePhase = "idle" | "listening" | "transcribing" | "thinking" | "speaking" | "error";
export type SpeechMode = "neural" | "system" | "off";

export interface VoiceDependencies {
  engine: VoiceEngine;
  recorder: Recorder;
  player: Player;
  systemVoice: SystemVoice;
  streamRag: typeof streamRag;
}

export function createBrowserVoiceDependencies(): VoiceDependencies {
  return { engine: new WorkerVoiceEngine(), recorder: new MicrophoneRecorder(), player: new WebAudioPlayer(), systemVoice: new BrowserSystemVoice(), streamRag };
}

export interface TurnMetrics {
  recordingMs?: number;
  sttMs?: number;
  firstTokenMs?: number; // question sent -> first RAG token
  firstAudioMs?: number; // end of user speech (or question sent) -> first audible answer
  completeMs?: number; // end of user speech (or question sent) -> answer fully spoken
  speech?: SpeechMode;
}

export interface VoiceTurn {
  id: number;
  origin: "voice" | "text";
  question: string;
  answer: string;
  sources: Source[];
  streaming: boolean;
  stopped?: boolean;
  error?: string;
  metrics: TurnMetrics;
}

const NOT_UNDERSTOOD = "Konuşma anlaşılamadı. Lütfen tekrar deneyin.";
const NO_SOURCE = "Önce en az bir Knowledge Base seçin.";

function readyBefore(): boolean {
  try { return window.localStorage.getItem(VOICE_READY_STORAGE_KEY) === "1"; } catch { return false; }
}

function rememberReady() {
  try { window.localStorage.setItem(VOICE_READY_STORAGE_KEY, "1"); } catch { /* optional */ }
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

  const phaseRef = useRef<VoicePhase>("idle");
  const requestRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
  const speechModeRef = useRef<SpeechMode>("neural");
  const voiceEnabledRef = useRef(true);
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
      rememberReady();
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
    if (reason === "stopped" && id) updateTurn(id, (turn) => (turn.streaming || phaseRef.current === "speaking" ? { streaming: false, stopped: true } : {}));
  }, [deps, updateTurn]);

  const ask = useCallback(async (question: string, origin: "voice" | "text", startedAt = performance.now(), metrics: TurnMetrics = {}) => {
    const knowledgeBases = kbRef.current;
    if (!knowledgeBases.length) { fail(NO_SOURCE); return; }
    stopCurrent("superseded");
    const id = ++requestRef.current;
    const controller = new AbortController();
    abortRef.current = controller;
    deps.player.reset(id);
    const mode: SpeechMode = voiceEnabledRef.current ? speechModeRef.current : "off";
    setError(null);
    setTurns((items) => [...items, { id, origin, question, answer: "", sources: [], streaming: true, metrics: { ...metrics, speech: mode } }]);
    setPhase("thinking");

    const sentAt = performance.now();
    const buffer = new SentenceBuffer();
    const speeches: Promise<void>[] = [];
    let seq = 0;
    let firstToken = true;
    let firstAudio = true;
    let systemChain = Promise.resolve();
    const current = () => requestRef.current === id && !controller.signal.aborted;

    const audible = (at: number) => {
      if (!firstAudio || !current()) return;
      firstAudio = false;
      updateMetrics(id, { firstAudioMs: at - startedAt });
      setPhase("speaking");
    };
    const say = (sentence: string) => {
      if (mode === "neural") {
        speeches.push(deps.engine.speak(id, seq++, sentence, (samples, rate) => {
          const at = deps.player.enqueue(samples, rate, id);
          if (at !== null) audible(at);
        }));
      } else if (mode === "system") {
        systemChain = systemChain.then(() => (current() ? deps.systemVoice.speak(sentence, () => audible(performance.now())) : undefined));
        speeches.push(systemChain);
      }
    };

    try {
      await deps.streamRag(knowledgeBases, question, (event) => {
        if (!current()) return;
        if (event.type === "sources") {
          updateTurn(id, () => ({ sources: event.data }));
        } else if (event.type === "token") {
          if (firstToken) { firstToken = false; updateMetrics(id, { firstTokenMs: performance.now() - sentAt }); }
          updateTurn(id, (turn) => ({ answer: turn.answer + event.data }));
          buffer.push(event.data).forEach(say);
        } else if (event.type === "complete") {
          buffer.flush().forEach(say);
          updateTurn(id, () => ({ streaming: false }));
        } else if (event.type === "error") {
          updateTurn(id, () => ({ streaming: false, error: event.data }));
        }
      }, controller.signal);
      await Promise.all(speeches);
      if (mode === "neural") await deps.player.drained();
      if (!current()) return;
      updateMetrics(id, { completeMs: performance.now() - startedAt });
      setPhase("idle");
    } catch (reason) {
      if (!current()) return; // superseded or stopped by the user
      const message = reason instanceof Error ? reason.message : "Yanıt alınamadı.";
      updateTurn(id, () => ({ streaming: false, error: message }));
      fail(message);
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
    }
  }, [deps, fail, setPhase, stopCurrent, updateMetrics, updateTurn]);

  const stopListening = useCallback(async () => {
    const recording = recordingRef.current;
    if (!recording) return;
    if (!deps.recorder.recording) { recording.stopRequested = true; return; } // permission prompt still open
    recordingRef.current = null;
    const stoppedAt = performance.now();
    setPhase("transcribing");
    try {
      const audio = await deps.recorder.stop();
      const result = await deps.engine.transcribe(audio);
      const sttMs = performance.now() - stoppedAt;
      if (!result.text) { fail(NOT_UNDERSTOOD); return; }
      await ask(result.text, "voice", stoppedAt, { recordingMs: stoppedAt - recording.startedAt, sttMs });
    } catch (reason) {
      fail(reason instanceof MicrophoneError ? reason.message : `Konuşma yazıya çevrilemedi: ${reason instanceof Error ? reason.message : "bilinmeyen hata"}`);
    }
  }, [ask, deps, fail, setPhase]);

  const startListening = useCallback(async () => {
    if (recordingRef.current || phaseRef.current === "transcribing") return;
    if (!kbRef.current.length) { fail(NO_SOURCE); return; }
    stopCurrent("stopped"); // the microphone never records while an answer is playing
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

  const toggleVoice = useCallback(() => {
    voiceEnabledRef.current = !voiceEnabledRef.current;
    setVoiceEnabled(voiceEnabledRef.current);
    if (!voiceEnabledRef.current && phaseRef.current === "speaking") stop();
  }, [stop]);

  const dismissError = useCallback(() => { setError(null); setPhase("idle"); }, [setPhase]);

  useEffect(() => {
    if (readyBefore()) prepare(); // models come from the browser cache after the first visit
  }, [prepare]);

  useEffect(() => () => {
    abortRef.current?.abort();
    deps.recorder.cancel();
    deps.systemVoice.cancel();
    deps.player.dispose();
    deps.engine.dispose();
  }, [deps]);

  const level = useCallback(() => {
    if (phaseRef.current === "listening") return deps.recorder.level();
    if (phaseRef.current === "speaking") return speechModeRef.current === "system" ? -1 : deps.player.level();
    return 0;
  }, [deps]);

  const backend: InferenceBackend | undefined = tts.backend;
  return { phase, error, turns, stt, tts, speechMode, voiceEnabled, backend, systemVoiceName: deps.systemVoice.voiceName(), prepare, startListening, stopListening, cancelListening, stop, askText, toggleVoice, dismissError, level };
}
