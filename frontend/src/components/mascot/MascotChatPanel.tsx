import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";

import {
  Send,
  Settings2,
  Sparkles,
  Square,
  X,
} from "lucide-react";

import {
  getErrorMessage,
} from "../../api/client";
import {
  DEFAULT_ASSISTANT_PREFERENCES,
  getAssistantPreferences,
  updateAssistantPreferences,
  type AssistantPreferences,
  type AssistantPreferencesUpdate,
} from "../../api/assistantPreferences";
import { useAuth } from "../../auth/AuthContext";

import {
  createAssistantConversation,
  getAssistantConversation,
  listAssistantConversations,
} from "../../api/assistantConversations";

import {
  listKnowledgeBases,
} from "../../api/knowledgeBases";

import {
  streamRag,
} from "../../api/websocket";

import type {
  KnowledgeBase,
  Source,
} from "../../types";

import {
  MascotFace,
} from "./MascotFace";

type MascotChatPanelProps = {
  onClose: () => void;
  workspaceId?: number | null;
};

type Message = {
  id: number;
  role: "assistant" | "user";
  content: string;
  sources?: Source[];
  streaming?: boolean;
};

const INITIAL_MESSAGES: Message[] = [
  {
    id: 1,
    role: "assistant",
    content:
      "Merhaba! Ben modAI Assistant'ım. "
      + "Uygulamada sana yardımcı olabilir ve aktif "
      + "Workspace'teki erişebildiğin Knowledge Base'lerden "
      + "kaynak destekli yerel RAG yanıtları üretebilirim.",
  },
];

const MAX_RAG_KNOWLEDGE_BASES = 20;

type ResolvedRagScope = {
  knowledgeBaseIds: number[];
  explicit: boolean;
};

function normalizeKnowledgeBaseReference(
  value: string,
): string {
  return value
    .toLocaleLowerCase("tr-TR")
    .normalize("NFKC")
    .replace(/[-_]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function resolveRagScope(
  question: string,
  knowledgeBases: KnowledgeBase[],
): ResolvedRagScope {
  const normalizedQuestion =
    normalizeKnowledgeBaseReference(
      question,
    );

  const matched = knowledgeBases.filter(
    (knowledgeBase) => {
      const normalizedName =
        normalizeKnowledgeBaseReference(
          knowledgeBase.name,
        );

      const normalizedSlug =
        normalizeKnowledgeBaseReference(
          knowledgeBase.slug,
        );

      return (
        (
          normalizedName.length > 0
          && normalizedQuestion.includes(
            normalizedName,
          )
        )
        || (
          normalizedSlug.length > 0
          && normalizedQuestion.includes(
            normalizedSlug,
          )
        )
      );
    },
  );

  if (matched.length === 0) {
    return {
      knowledgeBaseIds:
        knowledgeBases.map(
          (knowledgeBase) =>
            knowledgeBase.id,
        ),
      explicit: false,
    };
  }

  return {
    knowledgeBaseIds: [
      ...new Set(
        matched.map(
          (knowledgeBase) =>
            knowledgeBase.id,
        ),
      ),
    ],
    explicit: true,
  };
}

function localAssistantReply(
  question: string,
): string | null {
  const normalized = question
    .trim()
    .toLocaleLowerCase("tr-TR");

  const compact = normalized
    .replace(/[!?.,]+/g, "")
    .trim();

  const creatorQuestion = [
    "kim programladı",
    "kimprogramladı",
    "kim geliştirdi",
    "kim yarattı",
    "seni kim yaptı",
    "who created you",
    "who built you",
    "who made you",
  ].some((phrase) =>
    normalized.includes(phrase),
  );

  if (creatorQuestion) {
    return (
      "Ben modAI-stack içinde çalışan modAI Assistant'ım. "
      + "modAI-stack, We Are The Art Makers tarafından geliştiriliyor. "
      + "Kurumsal kaynak sorularında aktif Workspace'teki yetkili "
      + "Knowledge Base'leri kullanırım."
    );
  }

  const identityQuestion = [
    "kimsin",
    "sen nesin",
    "adın ne",
    "adın nedir",
    "kendini tanıt",
    "kendinden bahset",
    "who are you",
    "what are you",
  ].some((phrase) =>
    normalized.includes(phrase),
  );

  if (identityQuestion) {
    return (
      "Ben modAI Assistant'ım. "
      + "modAI-stack içinde çalışan yerel yardımcınım. "
      + "Uygulamada yol gösterebilir ve aktif Workspace'teki "
      + "erişebildiğin Knowledge Base'lerden kaynak destekli "
      + "RAG yanıtları üretebilirim."
    );
  }

  if (
    [
      "merhaba",
      "selam",
      "hello",
      "hi",
      "hey",
    ].includes(compact)
  ) {
    return (
      "Merhaba! Ben modAI Assistant'ım. "
      + "Kurumsal kaynakların hakkında soru sorabilir "
      + "veya benden uygulamada yardım isteyebilirsin."
    );
  }

  if (
    normalized.includes("ne yapabilirsin")
    || normalized.includes("nasıl yardımcı")
    || compact === "yardım"
    || compact === "help"
  ) {
    return (
      "Aktif Workspace'indeki yetkili Knowledge Base'lerde "
      + "kaynak destekli arama yapabilirim. Ayrıca modAI-stack "
      + "arayüzü ve temel kullanım konusunda sana yol gösterebilirim."
    );
  }

  return null;
}

export function MascotChatPanel({
  onClose,
  workspaceId = null,
}: MascotChatPanelProps) {
  const { user } = useAuth();
  const [preferences, setPreferences] =
    useState<AssistantPreferences>(DEFAULT_ASSISTANT_PREFERENCES);
  const [preferenceDraft, setPreferenceDraft] =
    useState<AssistantPreferencesUpdate>(DEFAULT_ASSISTANT_PREFERENCES);
  const [preferencesOpen, setPreferencesOpen] = useState(false);
  const [savingPreferences, setSavingPreferences] = useState(false);
  const [messages, setMessages] =
    useState<Message[]>(INITIAL_MESSAGES);

  const [question, setQuestion] =
    useState("");

  const [nextId, setNextId] =
    useState(2);

  const [knowledgeBases, setKnowledgeBases] =
    useState<KnowledgeBase[]>([]);

  const [loadingSources, setLoadingSources] =
    useState(false);

  const [busy, setBusy] =
    useState(false);

  const [error, setError] =
    useState<string | null>(null);

  const abortRef =
    useRef<AbortController | null>(null);

  const submissionRef = useRef(false);
  const workspaceGenerationRef = useRef(0);
  const activeWorkspaceRef = useRef<number | null>(null);
  const conversationRef = useRef<{
    workspaceId: number;
    id: number;
  } | null>(null);
  const createConversationRef = useRef<{
    workspaceId: number;
    promise: Promise<number>;
  } | null>(null);
  const workspaceLoadRef = useRef<{
    workspaceId: number;
    promise: Promise<void>;
  } | null>(null);
  const currentUserIdRef = useRef(user?.id);
  currentUserIdRef.current = user?.id;

  useEffect(() => {
    let active = true;
    setPreferences(DEFAULT_ASSISTANT_PREFERENCES);
    setPreferenceDraft(DEFAULT_ASSISTANT_PREFERENCES);
    setPreferencesOpen(false);
    void getAssistantPreferences()
      .then((loaded) => {
        if (!active) return;
        setPreferences(loaded);
        setPreferenceDraft({
          assistant_name: loaded.assistant_name,
          language: loaded.language,
          tone: loaded.tone,
          response_length: loaded.response_length,
        });
      })
      .catch((reason: unknown) => {
        if (active) setError(getErrorMessage(reason));
      });
    return () => {
      active = false;
    };
  }, [user?.id]);

  useEffect(() => {
    const generation =
      workspaceGenerationRef.current + 1;
    workspaceGenerationRef.current = generation;
    activeWorkspaceRef.current = workspaceId;
    submissionRef.current = false;

    const previousController = abortRef.current;

    abortRef.current = null;
    previousController?.abort();

    setBusy(false);
    setQuestion("");
    setError(null);
    setMessages(INITIAL_MESSAGES);
    setNextId(2);
    setKnowledgeBases([]);
    conversationRef.current = null;

    if (workspaceId === null) {
      setLoadingSources(false);
      workspaceLoadRef.current = null;
      return;
    }

    let active = true;

    setLoadingSources(true);

    const loadWorkspace = async () => {
      const [knowledgeBaseResult, conversationResult] =
        await Promise.allSettled([
          listKnowledgeBases(),
          listAssistantConversations(workspaceId),
        ]);

      if (!active || workspaceGenerationRef.current !== generation) {
        return;
      }

      if (knowledgeBaseResult.status === "fulfilled") {
        setKnowledgeBases(
          knowledgeBaseResult.value.filter(
            (item) => item.workspace_id === workspaceId,
          ),
        );
      } else {
        setError(getErrorMessage(knowledgeBaseResult.reason));
      }

      if (conversationResult.status === "fulfilled") {
        const conversation = conversationResult.value.items.find(
          (item) => item.workspace_id === workspaceId,
        );
        if (conversation) {
          conversationRef.current = {
            workspaceId,
            id: conversation.id,
          };
          try {
            const detail = await getAssistantConversation(
              conversation.id,
            );
            if (!active || workspaceGenerationRef.current !== generation) {
              return;
            }
            setMessages([
              ...INITIAL_MESSAGES,
              ...detail.messages.map((message) => ({
                id: -message.id,
                role: message.role,
                content: message.content,
                sources: message.sources.map((source) => ({
                  ...source,
                  text: null,
                })),
              })),
            ]);
          } catch (reason) {
            if (active) setError(getErrorMessage(reason));
          }
        }
      } else {
        setError(getErrorMessage(conversationResult.reason));
      }

      if (active && workspaceGenerationRef.current === generation) {
        setLoadingSources(false);
      }
    };

    const promise = loadWorkspace();
    workspaceLoadRef.current = { workspaceId, promise };
    void promise.catch((reason: unknown) => {
      if (active && workspaceGenerationRef.current === generation) {
        setError(getErrorMessage(reason));
        setLoadingSources(false);
      }
    });

    return () => {
      active = false;

      const controller = abortRef.current;

      abortRef.current = null;
      controller?.abort();
    };
  }, [workspaceId]);

  async function ensureConversation(
    targetWorkspaceId: number,
    generation: number,
  ): Promise<number> {
    const loaded = conversationRef.current;
    if (loaded?.workspaceId === targetWorkspaceId) {
      return loaded.id;
    }

    const pending = createConversationRef.current;
    if (pending?.workspaceId === targetWorkspaceId) {
      const id = await pending.promise;
      if (workspaceGenerationRef.current === generation) {
        conversationRef.current = { workspaceId: targetWorkspaceId, id };
      }
      return id;
    }

    const promise = createAssistantConversation(targetWorkspaceId)
      .then((conversation) => conversation.id);
    createConversationRef.current = {
      workspaceId: targetWorkspaceId,
      promise,
    };
    try {
      const id = await promise;
      if (workspaceGenerationRef.current === generation) {
        conversationRef.current = { workspaceId: targetWorkspaceId, id };
      }
      return id;
    } finally {
      if (createConversationRef.current?.promise === promise) {
        createConversationRef.current = null;
      }
    }
  }

  const sourceLimitExceeded =
    knowledgeBases.length
    > MAX_RAG_KNOWLEDGE_BASES;

  const knowledgeBaseIds =
    knowledgeBases.map((item) => item.id);

  function appendLocalReply(
    userContent: string,
    assistantContent: string,
  ) {
    setMessages((current) => [
      ...current,
      {
        id: nextId,
        role: "user",
        content: userContent,
      },
      {
        id: nextId + 1,
        role: "assistant",
        content: assistantContent,
      },
    ]);

    setNextId((current) => current + 2);
    setQuestion("");
    setError(null);
  }

  function cancelResponse() {
    const controller = abortRef.current;

    abortRef.current = null;
    controller?.abort();

    setBusy(false);

    setMessages((current) =>
      current.map((message) =>
        message.streaming
          ? {
              ...message,
              streaming: false,
            }
          : message,
      ),
    );
  }

  async function savePreferences() {
    const requestUserId = user?.id;
    setSavingPreferences(true);
    setError(null);
    try {
      const saved = await updateAssistantPreferences(preferenceDraft);
      if (requestUserId !== currentUserIdRef.current) return;
      setPreferences(saved);
      setPreferenceDraft({
        assistant_name: saved.assistant_name,
        language: saved.language,
        tone: saved.tone,
        response_length: saved.response_length,
      });
      setPreferencesOpen(false);
    } catch (reason) {
      if (requestUserId === currentUserIdRef.current) {
        setError(getErrorMessage(reason));
      }
    } finally {
      setSavingPreferences(false);
    }
  }

  async function submit(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault();

    const trimmed = question.trim();

    if (!trimmed || busy || submissionRef.current) {
      return;
    }

    const localReply =
      localAssistantReply(trimmed);

    if (localReply !== null) {
      appendLocalReply(
        trimmed,
        localReply,
      );
      return;
    }

    if (loadingSources) {
      appendLocalReply(
        trimmed,
        "Workspace kaynakları hâlâ yükleniyor. "
          + "Kısa bir süre sonra tekrar deneyin.",
      );
      return;
    }

    if (workspaceId === null) {
      appendLocalReply(
        trimmed,
        "Kurumsal kaynaklarda arama yapabilmem için "
          + "önce bir Workspace seçmeniz gerekiyor.",
      );
      return;
    }

    if (sourceLimitExceeded) {
      appendLocalReply(
        trimmed,
        "Bu Workspace'te 20'den fazla yetkili Knowledge Base var. "
          + "Kaynak kapsamını RAG Chat üzerinden seçin.",
      );
      return;
    }

    if (knowledgeBaseIds.length === 0) {
      appendLocalReply(
        trimmed,
        "Bu Workspace'te erişebildiğiniz bir Knowledge Base yok. "
          + "Kaynak destekli yanıt için önce bir Knowledge Base gerekli.",
      );
      return;
    }

    const ragScope = resolveRagScope(
      trimmed,
      knowledgeBases,
    );

    const userMessage: Message = {
      id: nextId,
      role: "user",
      content: trimmed,
    };

    const assistantId = nextId + 1;

    const assistantMessage: Message = {
      id: assistantId,
      role: "assistant",
      content: "",
      sources: [],
      streaming: true,
    };

    const controller =
      new AbortController();

    const generation = workspaceGenerationRef.current;
    submissionRef.current = true;

    abortRef.current?.abort();
    abortRef.current = controller;

    setNextId((current) => current + 2);
    setQuestion("");
    setError(null);
    setBusy(true);

    setMessages((current) => [
      ...current,
      userMessage,
      assistantMessage,
    ]);

    try {
      const currentWorkspaceLoad = workspaceLoadRef.current;
      if (currentWorkspaceLoad?.workspaceId === workspaceId) {
        await currentWorkspaceLoad.promise;
      }
      if (
        controller.signal.aborted
        || workspaceGenerationRef.current !== generation
        || activeWorkspaceRef.current !== workspaceId
      ) {
        return;
      }

      const activeConversationId = await ensureConversation(
        workspaceId,
        generation,
      );
      if (
        controller.signal.aborted
        || workspaceGenerationRef.current !== generation
        || activeWorkspaceRef.current !== workspaceId
      ) {
        return;
      }

      await streamRag(
        ragScope.knowledgeBaseIds,
        trimmed,
        (ragEvent) => {
          if (controller.signal.aborted) {
            return;
          }

          if (
            ragEvent.type === "sources"
            && ragEvent.data.length === 0
          ) {
            const noSourceMessage =
              ragScope.explicit
                ? (
                    ragScope.knowledgeBaseIds
                      .length === 1
                      ? "Bu Knowledge Base içinde kullanılabilir bir kaynak bulunamadı."
                      : "Belirttiğiniz Knowledge Base'lerde kullanılabilir bir kaynak bulunamadı."
                  )
                : "Bu Workspace kapsamında kullanılabilir bir kaynak bulunamadı.";

            setMessages((current) =>
              current.map((message) =>
                message.id === assistantId
                  ? {
                      ...message,
                      content: noSourceMessage,
                      sources: [],
                      streaming: false,
                    }
                  : message,
              ),
            );

            controller.abort();
            return;
          }

          if (ragEvent.type === "error") {
            setError(ragEvent.data);
          }

          setMessages((current) =>
            current.map((message) => {
              if (message.id !== assistantId) {
                return message;
              }

              if (ragEvent.type === "sources") {
                return {
                  ...message,
                  sources: ragEvent.data,
                };
              }

              if (ragEvent.type === "token") {
                return {
                  ...message,
                  content:
                    message.content
                    + ragEvent.data,
                };
              }

              return {
                ...message,
                streaming: false,
              };
            }),
          );
        },
        controller.signal,
        { conversationId: activeConversationId },
      );
    } catch (reason) {
      if (
        reason instanceof Error
        && reason.name === "AbortError"
      ) {
        return;
      }

      setMessages((current) =>
        current.map((message) =>
          message.id === assistantId
            ? {
                ...message,
                streaming: false,
              }
            : message,
        ),
      );

      setError(getErrorMessage(reason));
    } finally {
      submissionRef.current = false;
      if (abortRef.current === controller) {
        abortRef.current = null;
        setBusy(false);
      }
    }
  }

  let sourceStatus =
    "Workspace bekleniyor";

  if (workspaceId !== null) {
    if (loadingSources) {
      sourceStatus =
        "Kaynaklar yükleniyor…";
    } else if (sourceLimitExceeded) {
      sourceStatus =
        `${knowledgeBases.length} yetkili KB · `
        + "RAG Chat'ten seçim gerekli";
    } else if (knowledgeBases.length === 0) {
      sourceStatus =
        "Bu Workspace'te KB yok";
    } else {
      sourceStatus =
        `${knowledgeBases.length} yetkili KB · `
        + "kaynak destekli";
    }
  }

  return (
    <section
      role="dialog"
      aria-label={`${preferences.assistant_name} Assistant`}
      className="flex w-[min(360px,calc(100vw-2rem))] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl"
    >
      <header className="flex items-center gap-3 border-b border-slate-100 px-4 py-3">
        <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-ink text-white">
          <MascotFace active compact />
        </span>

        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h2 className="truncate text-sm font-bold text-ink">
              {preferences.assistant_name} Assistant
            </h2>

            <span className="inline-flex items-center gap-1 rounded-full bg-cyan/10 px-2 py-0.5 text-[10px] font-semibold text-cyan">
              <Sparkles
                className={
                  busy
                    ? "animate-pulse"
                    : ""
                }
                size={10}
              />
              Local RAG
            </span>
          </div>

          <p className="mt-0.5 truncate text-xs text-slate-500">
            {sourceStatus}
          </p>
        </div>

        <button
          type="button"
          className="rounded-lg p-2 text-slate-400 transition hover:bg-cloud hover:text-ink"
          aria-label="Asistan tercihleri"
          aria-expanded={preferencesOpen}
          onClick={() => {
            setPreferenceDraft({
              assistant_name: preferences.assistant_name,
              language: preferences.language,
              tone: preferences.tone,
              response_length: preferences.response_length,
            });
            setPreferencesOpen((open) => !open);
          }}
        >
          <Settings2 size={16} />
        </button>

        <button
          type="button"
          className="rounded-lg p-2 text-slate-400 transition hover:bg-cloud hover:text-ink"
          aria-label="Maskot sohbetini kapat"
          onClick={onClose}
        >
          <X size={16} />
        </button>
      </header>

      {preferencesOpen && (
        <section
          aria-label="Asistan tercihleri"
          className="border-b border-slate-100 bg-cloud/50 p-3"
        >
          <h3 className="mb-3 text-xs font-bold text-ink">
            Kişiselleştirme
          </h3>
          <div className="grid grid-cols-2 gap-2">
            <label className="col-span-2 text-xs text-slate-600">
              Asistan adı
              <input
                className="field mt-1 py-2 text-sm"
                aria-label="Asistan adı"
                maxLength={32}
                value={preferenceDraft.assistant_name}
                onChange={(event) => setPreferenceDraft((current) => ({
                  ...current,
                  assistant_name: event.target.value,
                }))}
              />
            </label>
            <label className="text-xs text-slate-600">
              Dil
              <select
                className="field mt-1 py-2 text-sm"
                aria-label="Yanıt dili"
                value={preferenceDraft.language}
                onChange={(event) => setPreferenceDraft((current) => ({
                  ...current,
                  language: event.target.value as AssistantPreferencesUpdate["language"],
                }))}
              >
                <option value="auto">Otomatik</option>
                <option value="en">English</option>
                <option value="tr">Türkçe</option>
              </select>
            </label>
            <label className="text-xs text-slate-600">
              Ton
              <select
                className="field mt-1 py-2 text-sm"
                aria-label="Yanıt tonu"
                value={preferenceDraft.tone}
                onChange={(event) => setPreferenceDraft((current) => ({
                  ...current,
                  tone: event.target.value as AssistantPreferencesUpdate["tone"],
                }))}
              >
                <option value="professional">Profesyonel</option>
                <option value="friendly">Samimi</option>
                <option value="technical">Teknik</option>
                <option value="concise">Kısa ve net</option>
              </select>
            </label>
            <label className="col-span-2 text-xs text-slate-600">
              Yanıt uzunluğu
              <select
                className="field mt-1 py-2 text-sm"
                aria-label="Yanıt uzunluğu"
                value={preferenceDraft.response_length}
                onChange={(event) => setPreferenceDraft((current) => ({
                  ...current,
                  response_length: event.target.value as AssistantPreferencesUpdate["response_length"],
                }))}
              >
                <option value="short">Kısa</option>
                <option value="balanced">Dengeli</option>
                <option value="detailed">Detaylı</option>
              </select>
            </label>
          </div>
          <div className="mt-3 flex justify-end gap-2">
            <button
              type="button"
              className="button-secondary px-3 py-2 text-xs"
              onClick={() => setPreferencesOpen(false)}
              disabled={savingPreferences}
            >
              İptal
            </button>
            <button
              type="button"
              className="button-primary px-3 py-2 text-xs"
              onClick={() => void savePreferences()}
              disabled={savingPreferences || !preferenceDraft.assistant_name.trim()}
            >
              {savingPreferences ? "Kaydediliyor…" : "Kaydet"}
            </button>
          </div>
        </section>
      )}

      <div
        className="max-h-72 space-y-3 overflow-y-auto p-4"
        aria-live="polite"
      >
        {messages.map((message) => (
          <div
            key={message.id}
            className={
              message.role === "user"
                ? "flex justify-end"
                : "flex justify-start"
            }
          >
            <div
              className={
                message.role === "user"
                  ? "max-w-[85%] rounded-2xl rounded-br-md bg-ink px-3.5 py-2.5 text-sm leading-5 text-white"
                  : "max-w-[85%] rounded-2xl rounded-bl-md bg-cloud px-3.5 py-2.5 text-sm leading-5 text-ink"
              }
            >
              {message.content
                || (
                  message.streaming
                    ? (
                      <span className="text-slate-400">
                        Yanıt hazırlanıyor…
                      </span>
                    )
                    : "Yanıt alınamadı."
                )}

              {message.streaming
                && message.content && (
                  <span className="ml-1 inline-block h-4 w-1 animate-pulse bg-cyan align-middle" />
                )}

              {message.sources
                && message.sources.length > 0 && (
                  <p className="mt-2 border-t border-slate-200/80 pt-2 text-[10px] font-semibold text-slate-400">
                    {message.sources.length} kaynak
                  </p>
                )}
            </div>
          </div>
        ))}
      </div>

      {error && (
        <div
          role="alert"
          className="mx-3 mb-2 rounded-xl bg-red-50 px-3 py-2 text-xs leading-5 text-red-700"
        >
          {error}
        </div>
      )}

      <form
        className="border-t border-slate-100 p-3"
        onSubmit={submit}
      >
        <div className="flex items-center gap-2">
          <input
            aria-label="Maskota mesaj yaz"
            className="field min-w-0 py-2.5"
            value={question}
            onChange={(event) => {
              setQuestion(event.target.value);
            }}
            placeholder="Bir şey sorun..."
            disabled={busy}
          />

          {busy ? (
            <button
              type="button"
              aria-label="Yanıtı durdur"
              className="button-secondary h-10 w-10 shrink-0 p-0"
              onClick={cancelResponse}
            >
              <Square size={14} />
            </button>
          ) : (
            <button
              type="submit"
              aria-label="Mesaj gönder"
              className="button-primary h-10 w-10 shrink-0 p-0"
              disabled={!question.trim()}
            >
              <Send size={16} />
            </button>
          )}
        </div>

        <p className="mt-2 text-center text-[10px] leading-4 text-slate-400">
          Kurumsal bilgi soruları yalnız aktif Workspace'teki
          erişebildiğiniz kaynaklardan üretilir.
        </p>
      </form>
    </section>
  );
}
