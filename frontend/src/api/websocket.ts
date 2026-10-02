import type { IndexingEvent, ModelPullEvent, RagEvent } from "../types";
import { request, websocketUrl } from "./client";

async function websocketTicket(scope: "chat" | "rag" | "indexing" | "models_pull", workspaceId?: number): Promise<string> {
  const result = await request<{ ticket: string }>("/auth/ws-ticket", { method: "POST", body: JSON.stringify({ scope, workspace_id: workspaceId }) });
  return result.ticket;
}

export function connectIndexing(
  workspaceId: number,
  onEvent: (event: IndexingEvent) => void,
  onState: (state: "connecting" | "open" | "closed") => void,
): () => void {
  let stopped = false;
  let socket: WebSocket | null = null;
  let retry = 0;
  let timer: number | undefined;

  const connect = () => {
    if (stopped) return;
    onState("connecting");
    void websocketTicket("indexing", workspaceId).then((ticket) => {
      if (stopped) return;
      socket = new WebSocket(websocketUrl(`/ws/indexing?ticket=${encodeURIComponent(ticket)}`));
      socket.onopen = () => { retry = 0; onState("open"); };
      socket.onmessage = (message) => {
        try { onEvent(JSON.parse(message.data as string) as IndexingEvent); } catch { /* Ignore malformed events. */ }
      };
      socket.onclose = () => {
        onState("closed");
        if (!stopped && retry < 5) {
          const delay = Math.min(1000 * 2 ** retry, 16000);
          retry += 1;
          timer = window.setTimeout(connect, delay);
        }
      };
    }).catch(() => onState("closed"));
  };
  connect();
  return () => { stopped = true; if (timer) window.clearTimeout(timer); socket?.close(); };
}

export function streamRag(
  knowledgeBaseIds: number[],
  question: string,
  onEvent: (event: RagEvent) => void,
): Promise<void> {
  return new Promise((resolve, reject) => {
    let socket: WebSocket | null = null;
    let finished = false;
    let terminalEvent = false;
    const fail = (reason: Error) => {
      if (finished) return;
      finished = true;
      reject(reason);
      socket?.close();
    };
    const attach = (nextSocket: WebSocket) => {
      socket = nextSocket;
      nextSocket.onopen = () => nextSocket.send(JSON.stringify({ question, knowledge_base_ids: knowledgeBaseIds }));
      nextSocket.onmessage = (message) => {
      try {
        const event = JSON.parse(message.data as string) as RagEvent;
        onEvent(event);
        if (event.type === "complete" || event.type === "error") {
          terminalEvent = true;
          socket?.close();
        }
      } catch { fail(new Error("RAG yanıtı okunamadı.")); }
      };
      nextSocket.onerror = () => fail(new Error("RAG bağlantısı kurulamadı."));
      nextSocket.onclose = () => {
      if (finished) return;
      finished = true;
      if (terminalEvent) resolve();
      else reject(new Error("RAG bağlantısı beklenmedik şekilde kapandı."));
      };
    };
    void websocketTicket("rag").then((ticket) => attach(new WebSocket(websocketUrl(`/ws/rag?ticket=${encodeURIComponent(ticket)}`)))).catch(() => fail(new Error("RAG bağlantısı kurulamadı.")));
  });
}

export function streamModelPull(model: string, onEvent: (event: ModelPullEvent) => void): Promise<void> {
  return new Promise((resolve, reject) => {
    let socket: WebSocket | null = null;
    let finished = false;
    let terminalEvent = false;
    const fail = (reason: Error) => {
      if (finished) return;
      finished = true;
      reject(reason);
      socket?.close();
    };
    const attach = (nextSocket: WebSocket) => {
      socket = nextSocket;
      nextSocket.onopen = () => nextSocket.send(JSON.stringify({ model }));
      nextSocket.onmessage = (message) => {
      try {
        const event = JSON.parse(message.data as string) as ModelPullEvent;
        onEvent(event);
        if (event.type === "complete" || event.type === "error") {
          terminalEvent = true;
          socket?.close();
        }
      } catch { fail(new Error("Model indirme durumu okunamadı.")); }
      };
      nextSocket.onerror = () => fail(new Error("Model sağlayıcısına bağlanılamadı."));
      nextSocket.onclose = () => {
      if (finished) return;
      finished = true;
      if (terminalEvent) resolve();
      else reject(new Error("Model indirme bağlantısı beklenmedik şekilde kapandı."));
      };
    };
    void websocketTicket("models_pull").then((ticket) => attach(new WebSocket(websocketUrl(`/ws/models/pull?ticket=${encodeURIComponent(ticket)}`)))).catch(() => fail(new Error("Model sağlayıcısına bağlanılamadı.")));
  });
}
