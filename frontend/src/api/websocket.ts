import type { IndexingEvent, RagEvent } from "../types";
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
    socket.onopen = () => socket.send(JSON.stringify({ question, knowledge_base_ids: knowledgeBaseIds }));
    socket.onmessage = (message) => {
      try {
        const event = JSON.parse(message.data as string) as RagEvent;
        onEvent(event);
        if (event.type === "complete" || event.type === "error") socket.close();
      } catch { reject(new Error("RAG yanıtı okunamadı.")); socket.close(); }
    };
    socket.onerror = () => reject(new Error("RAG bağlantısı kurulamadı."));
    socket.onclose = () => resolve();
  });
}
