import { useCallback, useEffect, useRef, useState } from "react";
import { createAssistantConversation, getAssistantConversation, listAssistantConversations } from "../api/assistantConversations";
import { warmGenerationModel } from "../api/rag";
import { streamRag } from "../api/websocket";
import type { AssistantConversationDetail, AssistantConversationList, AssistantConversationSummary, RagTimings, Source } from "../types";
import { WebAudioPlayer, type Player } from "./audioPlayback";
import {
  DEFAULT_SPEECH_SPEED, SPEECH_SPEEDS, VOICE_LANGUAGE_STORAGE_KEY, VOICE_READY_STORAGE_KEY, VOICE_REVIEW_STORAGE_KEY,
  VOICE_SPEED_STORAGE_KEY, VOICE_TITLE_PREFIX,
} from "./config";
import { classifyIntent, LOCAL_REPLIES, sentenceLanguage } from "./intent";
import { MicrophoneError, MicrophoneRecorder, trimSilence, type AudioDiagnostics, type Recorder } from "./microphone";
import type { InferenceBackend } from "./protocol";
import { ReplayRecorder } from "./replayRecorder";
import { SentenceBuffer, speakable } from "./sentenceBuffer";
import { BrowserSystemVoice, type SystemVoice } from "./systemVoice";
import { clock, recordDebugTiming, stageDurations, type Timeline } from "./timeline";
import { IDLE_LOAD, sharedVoiceEngine, type LoadState, type VoiceEngine } from "./voiceEngine";

export type VoicePhase = "idle" | "listening" | "transcribing" | "reviewing" | "searching" | "answering" | "speaking" | "error";
export type SpeechMode = "neural" | "system" | "off";
export type AnswerLanguage = "tr" | "auto";

export interface ConversationApi {
  list(workspaceId: number): Promise<AssistantConversationList>;
  create(workspaceId: number, title: string): Promise<AssistantConversationSummary>;
  get(conversationId: number): Promise<AssistantConversationDetail>;
}

export interface VoiceDependencies {
  engine: VoiceEngine;
  recorder: Recorder;
  player: Player;
  systemVoice: SystemVoice;
  streamRag: typeof streamRag;
  conversations: ConversationApi;
  warmup: () => Promise<void>;
}

export function createBrowserVoiceDependencies(): VoiceDependencies {
  const recorder = import.meta.env.VITE_VOICE_REPLAY === "1" ? new ReplayRecorder() : new MicrophoneRecorder();
  return {
    engine: sharedVoiceEngine(),
    recorder,
    player: new WebAudioPlayer(),
    systemVoice: new BrowserSystemVoice(),
    streamRag,
    conversations: { list: listAssistantConversations, create: createAssistantConversation, get: getAssistantConversation },
    warmup: warmGenerationModel,
  };
}

export interface TurnMetrics {
  recordingMs?: number;
  sttMs?: number; // end of speech -> transcript on the page (capture + transfer + queue + inference)
  firstTokenMs?: number; // question sent -> first RAG token
  firstAudioMs?: number; // end of user speech (or question sent) -> first audible answer
  completeMs?: number; // end of user speech (or question sent) -> answer fully spoken
  speech?: SpeechMode;
  speed?: number;
  stages?: Record<string, number>; // see timeline.ts
  server?: RagTimings; // numeric server stage timings
  audio?: AudioDiagnostics & { trimmedLeadingMs: number; trimmedTrailingMs: number; trimmedDurationMs: number };
  stt?: { warm?: boolean; backend?: InferenceBackend };
}

export interface VoiceTurn {
  id: number;
  origin: "voice" | "text";
  question: string;
  answer: string;
  sources: Source[];
  streaming: boolean;
  restored?: boolean; // loaded from the saved conversation; never played automatically
  local?: boolean; // answered without document retrieval (greeting, thanks, capability)
  stopped?: boolean;
  corrected?: boolean;
  saved?: boolean; // persisted in the conversation by the server
  error?: string;
  phrases: number; // speakable phrases produced from the answer
  spokenPhrases: number; // phrases whose audio actually reached the playback queue
  unspokenForeign: number; // phrases not spoken because they were not Turkish
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
const WARMUP_INTERVAL_MS = 60_000;

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

function conversationTitle(question: string): string {
  const text = question.replace(/\s+/g, " ").trim();
  return `${VOICE_TITLE_PREFIX}${text.length > 80 ? `${text.slice(0, 79)}…` : text}`;
}

/** Saved user/assistant messages as turns, in order. Source excerpts are not stored, so `text` is null. */
export function turnsFromConversation(detail: AssistantConversationDetail): VoiceTurn[] {
  const turns: VoiceTurn[] = [];
  for (const message of detail.messages) {
    if (message.role === "user") {
      turns.push({
        id: -message.id, origin: "voice", question: message.content, answer: "", sources: [], streaming: false,
        restored: true, saved: true, phrases: 0, spokenPhrases: 0, unspokenForeign: 0, metrics: {},
      });
    } else if (turns.length && !turns[turns.length - 1].answer) {
      const turn = turns[turns.length - 1];
      turn.answer = message.content;
      turn.sources = message.sources.map((source) => ({ ...source, text: null }));
    }
  }
  return turns;
}

export function useVoiceAssistant(knowledgeBaseIds: number[], workspaceId: number | null, dependencies?: VoiceDependencies) {
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
  // Reviewing the transcript is on by default: Whisper tiny often mishears Turkish.
  const [review, setReviewState] = useState(() => stored(VOICE_REVIEW_STORAGE_KEY) !== "0");
  const [answerLanguage, setAnswerLanguageState] = useState<AnswerLanguage>(() => (stored(VOICE_LANGUAGE_STORAGE_KEY) === "auto" ? "auto" : "tr"));
  const [pending, setPending] = useState<PendingTranscript | null>(null);
  const [conversations, setConversations] = useState<AssistantConversationSummary[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<number | null>(null);
  const [conversationStatus, setConversationStatus] = useState<"idle" | "loading" | "error">("idle");

  const phaseRef = useRef<VoicePhase>("idle");
  const requestRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
  const speechModeRef = useRef<SpeechMode>("neural");
  const voiceEnabledRef = useRef(true);
  const speedRef = useRef(speed);
  const reviewRef = useRef(review);
  const languageRef = useRef(answerLanguage);
  const kbRef = useRef(knowledgeBaseIds);
  const workspaceRef = useRef(workspaceId);
  const conversationRef = useRef<number | null>(null);
  const conversationGeneration = useRef(0);
  const restoringRef = useRef(false);
  const lastWarmup = useRef(-Infinity);
  const recordingRef = useRef<{ startedAt: number; stopRequested: boolean } | null>(null);
  kbRef.current = knowledgeBaseIds;
  workspaceRef.current = workspaceId;

  const setPhase = useCallback((next: VoicePhase) => { phaseRef.current = next; setPhaseState(next); }, []);
  const updateTurn = useCallback((id: number, patch: (turn: VoiceTurn) => Partial<VoiceTurn>) => {
    setTurns((items) => items.map((turn) => (turn.id === id ? { ...turn, ...patch(turn) } : turn)));
  }, []);
  const updateMetrics = useCallback((id: number, metrics: TurnMetrics) => {
    updateTurn(id, (turn) => ({ metrics: { ...turn.metrics, ...metrics } }));
  }, [updateTurn]);
  const setActiveConversation = useCallback((id: number | null) => { conversationRef.current = id; setActiveConversationId(id); }, []);

  const fail = useCallback((message: string) => { setError(message); setPhase("error"); }, [setPhase]);

  /** Loads the generation model ahead of the question (at most once a minute). */
  const warmGeneration = useCallback(() => {
    const now = performance.now();
    if (now - lastWarmup.current < WARMUP_INTERVAL_MS) return;
    lastWarmup.current = now;
    void deps.warmup().catch(() => undefined);
  }, [deps]);

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

  const restoreConversation = useCallback(async (conversationId: number) => {
    const generation = ++conversationGeneration.current;
    restoringRef.current = true;
    setConversationStatus("loading");
    try {
      const detail = await deps.conversations.get(conversationId);
      if (generation !== conversationGeneration.current) return;
      restoringRef.current = false;
      if (detail.workspace_id !== workspaceRef.current) throw new Error("Bu görüşme seçili Workspace'e ait değil.");
      setActiveConversation(detail.id);
      setTurns(turnsFromConversation(detail));
      setConversationStatus("idle");
    } catch (reason) {
      if (generation !== conversationGeneration.current) return;
      restoringRef.current = false;
      setConversationStatus("error");
      setError(reason instanceof Error ? reason.message : "Görüşme yüklenemedi.");
    }
  }, [deps, setActiveConversation]);

  // Restore the latest voice conversation of the workspace; nothing is played automatically.
  useEffect(() => {
    stopCurrent("superseded");
    setTurns([]);
    setPending(null);
    setActiveConversation(null);
    setConversations([]);
    if (workspaceId === null) return;
    const generation = ++conversationGeneration.current;
    restoringRef.current = true;
    setConversationStatus("loading");
    deps.conversations.list(workspaceId).then((list) => {
      if (generation !== conversationGeneration.current) return;
      restoringRef.current = false;
      const items = list.items.filter((item) => item.workspace_id === workspaceId);
      setConversations(items);
      const latestVoice = items.find((item) => item.title?.startsWith(VOICE_TITLE_PREFIX));
      if (latestVoice) void restoreConversation(latestVoice.id);
      else setConversationStatus("idle");
    }).catch(() => {
      if (generation !== conversationGeneration.current) return;
      restoringRef.current = false;
      setConversationStatus("error");
    });
  }, [deps, restoreConversation, setActiveConversation, stopCurrent, workspaceId]);

  const ensureConversation = useCallback(async (question: string, timeline: Timeline): Promise<number> => {
    if (conversationRef.current !== null) return conversationRef.current;
    const workspace = workspaceRef.current;
    if (workspace === null) throw new Error("Workspace seçilmedi.");
    timeline.conversationStart = clock();
    const created = await deps.conversations.create(workspace, conversationTitle(question));
    timeline.conversationReady = clock();
    if (workspaceRef.current === workspace && conversationRef.current === null) {
      setActiveConversation(created.id);
      setConversations((items) => [created, ...items.filter((item) => item.id !== created.id)]);
    }
    return created.id;
  }, [deps, setActiveConversation]);

  /** Speaks a fixed Turkish reply without retrieval (greetings and "what can you do"). */
  const replyLocally = useCallback((id: number, reply: string, startedAt: number, timeline: Timeline) => {
    const mode: SpeechMode = voiceEnabledRef.current ? speechModeRef.current : "off";
    updateTurn(id, () => ({ answer: reply, streaming: false, local: true, phrases: mode === "off" ? 0 : 1 }));
    const finish = () => {
      if (requestRef.current !== id) return;
      timeline.speechEnd = clock();
      updateMetrics(id, { completeMs: performance.now() - startedAt, stages: stageDurations(timeline) });
      setPhase("idle");
    };
    const audible = (at: number) => {
      if (requestRef.current !== id) return;
      timeline.firstAudible = at;
      updateTurn(id, () => ({ spokenPhrases: 1 }));
      updateMetrics(id, { firstAudioMs: at - performance.timeOrigin - startedAt });
      setPhase("speaking");
    };
    if (mode === "neural") {
      void deps.engine.speak(id, 0, speakable(reply), (samples, rate) => {
        const at = deps.player.enqueue(samples, rate, id);
        if (at !== null && timeline.firstAudible === undefined) audible(at);
      }, speedRef.current).then(() => deps.player.drained()).then(finish, finish);
    } else if (mode === "system") {
      void deps.systemVoice.speak(reply, () => audible(clock()), speedRef.current).then(finish, finish);
    } else {
      finish();
    }
  }, [deps, setPhase, updateMetrics, updateTurn]);

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
    if (restoringRef.current) {
      // A restore still in flight must not replace this new turn: it starts a new conversation.
      conversationGeneration.current += 1;
      restoringRef.current = false;
      setConversationStatus("idle");
    }
    timeline.askStart = clock();
    const id = ++requestRef.current;
    const controller = new AbortController();
    abortRef.current = controller;
    deps.player.reset(id);
    const mode: SpeechMode = voiceEnabledRef.current ? speechModeRef.current : "off";
    const speechSpeed = speedRef.current;
    const language = languageRef.current;
    setError(null);
    setTurns((items) => [...items, {
      id, origin, question, answer: "", sources: [], streaming: true, corrected,
      phrases: 0, spokenPhrases: 0, unspokenForeign: 0, metrics: { ...metrics, speech: mode, speed: speechSpeed },
    }]);

    const intent = classifyIntent(question);
    if (intent !== "question") {
      replyLocally(id, LOCAL_REPLIES[intent], startedAt, timeline);
      return;
    }
    setPhase("searching");

    const current = () => requestRef.current === id && !controller.signal.aborted;
    let firstToken = true;
    let firstAudio = true;
    let answerLength = 0;
    let phrases = 0;
    let foreign = 0;
    const spoken = new Set<number>();
    const buffer = new SentenceBuffer();

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
      // The neural voice speaks Turkish only; never read an English sentence with it.
      if (language === "tr" && mode !== "off" && sentenceLanguage(sentence) === "en") {
        foreign += 1;
        updateTurn(id, () => ({ unspokenForeign: foreign }));
        return;
      }
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
      const conversationId = await ensureConversation(question, timeline);
      if (!current()) return;
      const sentAt = performance.now();
      timeline.ragStart = clock();
      let completed = false;
      await deps.streamRag(knowledgeBases, question, (event) => {
        if (!current()) return;
        if (event.type === "sources") {
          timeline.sources ??= clock();
          if (phaseRef.current === "searching") setPhase("answering");
          updateTurn(id, (turn) => ({ sources: event.data, metrics: { ...turn.metrics, server: { ...turn.metrics.server, ...event.timings } } }));
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
          completed = true;
          timeline.ragComplete = clock();
          buffer.flush().forEach(say);
          endOfAnswer();
          // The server saves the turn before it sends "complete".
          updateTurn(id, (turn) => ({ streaming: false, saved: true, metrics: { ...turn.metrics, server: { ...turn.metrics.server, ...event.timings } } }));
        } else if (event.type === "error") {
          endOfAnswer();
          updateTurn(id, () => ({ streaming: false, error: event.data }));
        }
      }, controller.signal, {
        conversationId,
        responseLanguage: language === "tr" ? "tr" : undefined,
        diagnostics: true,
        onTicket: () => { timeline.ragTicket = clock(); },
        onOpen: () => { timeline.ragOpen = clock(); },
        onSent: () => { timeline.ragSent = clock(); },
      });
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
      recordDebugTiming({ id, origin, speech: mode, speed: speechSpeed, phrases, spokenPhrases: spoken.size, unspokenForeign: foreign, answerChars: answerLength, stages });
      if (completed) {
        setConversations((items) => {
          const active = items.find((item) => item.id === conversationId);
          return active ? [{ ...active, updated_at: new Date().toISOString() }, ...items.filter((item) => item.id !== conversationId)] : items;
        });
      }
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
  }, [deps, ensureConversation, fail, replyLocally, setPhase, stopCurrent, updateMetrics, updateTurn]);

  const stopListening = useCallback(async () => {
    const recording = recordingRef.current;
    if (!recording) return;
    if (!deps.recorder.recording) { recording.stopRequested = true; return; } // permission prompt still open
    recordingRef.current = null;
    const stoppedAt = performance.now();
    const timeline: Timeline = { recordStart: recording.startedAt + performance.timeOrigin, recordStop: stoppedAt + performance.timeOrigin };
    setPhase("transcribing");
    try {
      const recorded = await deps.recorder.stop();
      const trimmed = trimSilence(recorded.samples);
      timeline.audioReady = clock();
      const result = await deps.engine.transcribe(trimmed.samples);
      timeline.sttPosted = result.postedAt;
      timeline.sttReceived = result.receivedAt;
      timeline.sttStart = result.startedAt;
      timeline.sttEnd = result.endedAt;
      timeline.transcriptReceived = clock();
      const metrics: TurnMetrics = {
        recordingMs: stoppedAt - recording.startedAt,
        sttMs: performance.now() - stoppedAt,
        audio: {
          ...recorded.diagnostics,
          trimmedLeadingMs: trimmed.leadingMs,
          trimmedTrailingMs: trimmed.trailingMs,
          trimmedDurationMs: (trimmed.samples.length / 16_000) * 1000,
        },
        stt: { warm: result.warm, backend: result.backend },
      };
      if (!result.text) { fail(NOT_UNDERSTOOD); return; }
      warmGeneration();
      if (reviewRef.current) {
        setPending({ text: result.text, stoppedAt, metrics, timeline });
        setPhase("reviewing");
        return;
      }
      await ask(result.text, "voice", stoppedAt, metrics, timeline);
    } catch (reason) {
      fail(reason instanceof MicrophoneError ? reason.message : `Konuşma yazıya çevrilemedi: ${reason instanceof Error ? reason.message : "bilinmeyen hata"}`);
    }
  }, [ask, deps, fail, setPhase, warmGeneration]);

  const startListening = useCallback(async () => {
    if (recordingRef.current || phaseRef.current === "transcribing") return;
    if (!kbRef.current.length) { fail(NO_SOURCE); return; }
    stopCurrent("stopped"); // the microphone never records while an answer is playing
    setPending(null);
    deps.player.unlock();
    if (stt.status === "idle") prepare();
    warmGeneration(); // the model loads while the user speaks
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
  }, [deps, fail, prepare, setPhase, stopCurrent, stopListening, stt.status, warmGeneration]);

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
    warmGeneration();
    void ask(question.trim(), "text");
  }, [ask, deps, warmGeneration]);

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

  const selectConversation = useCallback((conversationId: number) => {
    if (conversationId === conversationRef.current) return;
    stopCurrent("superseded");
    setPending(null);
    setPhase("idle");
    void restoreConversation(conversationId);
  }, [restoreConversation, setPhase, stopCurrent]);

  /** Starts an empty conversation; it is created on the server with the first question. */
  const newConversation = useCallback(() => {
    conversationGeneration.current += 1;
    stopCurrent("superseded");
    setPending(null);
    setTurns([]);
    setActiveConversation(null);
    setConversationStatus("idle");
    setPhase("idle");
  }, [setActiveConversation, setPhase, stopCurrent]);

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

  const setAnswerLanguage = useCallback((value: AnswerLanguage) => {
    languageRef.current = value;
    setAnswerLanguageState(value);
    store(VOICE_LANGUAGE_STORAGE_KEY, value);
  }, []);

  const dismissError = useCallback(() => { setError(null); setPhase("idle"); }, [setPhase]);

  useEffect(() => {
    if (stored(VOICE_READY_STORAGE_KEY) === "1") prepare(); // warm models come back from the browser cache
    warmGeneration();
  }, [prepare, warmGeneration]);

  useEffect(() => () => {
    conversationGeneration.current += 1;
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
    phase, error, turns, stt, tts, speechMode, voiceEnabled, backend, speed, review, answerLanguage, pending,
    conversations, activeConversationId, conversationStatus,
    systemVoiceName: deps.systemVoice.voiceName(),
    prepare, startListening, stopListening, cancelListening, stop, askText, confirmTranscript, discardTranscript, correct,
    selectConversation, newConversation, toggleVoice, setSpeed, setReview, setAnswerLanguage, dismissError, level,
  };
}
