import type { IndexingEvent, ModelPullEvent, RagEvent } from "../types";
import { tokenStore, websocketUrl } from "./client";

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
    const token = encodeURIComponent(tokenStore.access ?? "");
    socket = new WebSocket(websocketUrl(`/ws/indexing?workspace_id=${workspaceId}&token=${token}`));
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
    const token = encodeURIComponent(tokenStore.access ?? "");
    const socket = new WebSocket(websocketUrl(`/ws/rag?token=${token}`));
    let finished = false;
    let terminalEvent = false;
    const fail = (reason: Error) => {
      if (finished) return;
      finished = true;
      reject(reason);
      socket.close();
    };
    socket.onopen = () => socket.send(JSON.stringify({ question, knowledge_base_ids: knowledgeBaseIds }));
    socket.onmessage = (message) => {
      try {
        const event = JSON.parse(message.data as string) as RagEvent;
        onEvent(event);
        if (event.type === "complete" || event.type === "error") {
          terminalEvent = true;
          socket.close();
        }
      } catch { fail(new Error("RAG yanıtı okunamadı.")); }
    };
    socket.onerror = () => fail(new Error("RAG bağlantısı kurulamadı."));
    socket.onclose = () => {
      if (finished) return;
      finished = true;
      if (terminalEvent) resolve();
      else reject(new Error("RAG bağlantısı beklenmedik şekilde kapandı."));
    };
  });
}

export function streamModelPull(model: string, onEvent: (event: ModelPullEvent) => void): Promise<void> {
  return new Promise((resolve, reject) => {
    const token = encodeURIComponent(tokenStore.access ?? "");
    const socket = new WebSocket(websocketUrl(`/ws/models/pull?token=${token}`));
    let finished = false;
    let terminalEvent = false;
    const fail = (reason: Error) => {
      if (finished) return;
      finished = true;
      reject(reason);
      socket.close();
    };
    socket.onopen = () => socket.send(JSON.stringify({ model }));
    socket.onmessage = (message) => {
      try {
        const event = JSON.parse(message.data as string) as ModelPullEvent;
        onEvent(event);
        if (event.type === "complete" || event.type === "error") {
          terminalEvent = true;
          socket.close();
        }
      } catch { fail(new Error("Model indirme durumu okunamadı.")); }
    };
    socket.onerror = () => fail(new Error("Model sağlayıcısına bağlanılamadı."));
    socket.onclose = () => {
      if (finished) return;
      finished = true;
      if (terminalEvent) resolve();
      else reject(new Error("Model indirme bağlantısı beklenmedik şekilde kapandı."));
    };
  });
}
