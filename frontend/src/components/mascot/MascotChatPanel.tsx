import {
  useState,
  type FormEvent,
} from "react";

import {
  Send,
  Sparkles,
  X,
} from "lucide-react";

import {
  MascotFace,
} from "./MascotFace";

type MascotChatPanelProps = {
  onClose: () => void;
};

type Message = {
  id: number;
  role: "assistant" | "user";
  content: string;
};

const INITIAL_MESSAGES: Message[] = [
  {
    id: 1,
    role: "assistant",
    content:
      "Merhaba! Ben modAI yardımcısıyım. "
      + "Şimdilik arayüzde yol gösterebilirim.",
  },
];

function mockReply(question: string): string {
  const normalized = question
    .trim()
    .toLocaleLowerCase("tr-TR");

  if (
    normalized.includes("merhaba")
    || normalized.includes("selam")
    || normalized === "hi"
    || normalized === "hello"
  ) {
    return (
      "Merhaba! Knowledge Base, Belgeler, Chat, "
      + "Modeller ve Sistem bölümlerinde sana yol gösterebilirim."
    );
  }

  if (
    normalized.includes("knowledge")
    || normalized.includes("bilgi tabanı")
  ) {
    return (
      "Knowledge Base'ler bölümünde kurumsal kaynaklarını "
      + "oluşturabilir ve düzenleyebilirsin."
    );
  }

  if (
    normalized.includes("belge")
    || normalized.includes("document")
  ) {
    return (
      "Belgeler bölümünden seçili Knowledge Base'e "
      + "doküman yükleyebilir ve indeksleme durumunu izleyebilirsin."
    );
  }

  if (
    normalized.includes("chat")
    || normalized.includes("soru")
  ) {
    return (
      "RAG Chat bölümünde seçtiğin Knowledge Base'ler üzerinden "
      + "yerel modelle kaynak destekli sorular sorabilirsin."
    );
  }

  if (
    normalized.includes("model")
    || normalized.includes("ollama")
  ) {
    return (
      "Modeller bölümünde yerel model çalışma zamanını ve "
      + "hazırlık durumunu görebilirsin."
    );
  }

  if (
    normalized.includes("sistem")
    || normalized.includes("system")
    || normalized.includes("health")
  ) {
    return (
      "Sistem bölümünde servis ve platform durumunu "
      + "kontrol edebilirsin."
    );
  }

  if (
    normalized.includes("ne yap")
    || normalized.includes("yardım")
    || normalized.includes("help")
  ) {
    return (
      "Şimdilik yalnızca ürün içinde yol gösteriyorum. "
      + "Yerel model bağlantısı Sprint 2'de eklenecek."
    );
  }

  return (
    "Bu sürüm henüz gerçek modele bağlı değil. "
    + "Knowledge Base, Belgeler, Chat, Modeller veya Sistem "
    + "hakkında soru sorabilirsin."
  );
}

export function MascotChatPanel({
  onClose,
}: MascotChatPanelProps) {
  const [messages, setMessages] =
    useState<Message[]>(INITIAL_MESSAGES);

  const [question, setQuestion] = useState("");
  const [nextId, setNextId] = useState(2);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const trimmed = question.trim();

    if (!trimmed) {
      return;
    }

    const userMessage: Message = {
      id: nextId,
      role: "user",
      content: trimmed,
    };

    const assistantMessage: Message = {
      id: nextId + 1,
      role: "assistant",
      content: mockReply(trimmed),
    };

    setMessages((current) => [
      ...current,
      userMessage,
      assistantMessage,
    ]);

    setNextId((current) => current + 2);
    setQuestion("");
  }

  return (
    <section
      role="dialog"
      aria-label="modAI Assistant"
      className="flex w-[min(360px,calc(100vw-2rem))] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl"
    >
      <header className="flex items-center gap-3 border-b border-slate-100 px-4 py-3">
        <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-ink text-white">
          <MascotFace active compact />
        </span>

        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h2 className="truncate text-sm font-bold text-ink">
              modAI Assistant
            </h2>

            <span className="inline-flex items-center gap-1 rounded-full bg-cyan/10 px-2 py-0.5 text-[10px] font-semibold text-cyan">
              <Sparkles size={10} />
              Prototype
            </span>
          </div>

          <p className="mt-0.5 text-xs text-slate-500">
            Ürün rehberi
          </p>
        </div>

        <button
          type="button"
          className="rounded-lg p-2 text-slate-400 transition hover:bg-cloud hover:text-ink"
          aria-label="Maskot sohbetini kapat"
          onClick={onClose}
        >
          <X size={16} />
        </button>
      </header>

      <div className="max-h-72 space-y-3 overflow-y-auto p-4">
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
              {message.content}
            </div>
          </div>
        ))}
      </div>

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
          />

          <button
            type="submit"
            aria-label="Mesaj gönder"
            className="button-primary h-10 w-10 shrink-0 p-0"
            disabled={!question.trim()}
          >
            <Send size={16} />
          </button>
        </div>

        <p className="mt-2 text-center text-[10px] leading-4 text-slate-400">
          Prototype assistant · Yerel model bağlantısı sonraki sprintte
        </p>
      </form>
    </section>
  );
}
