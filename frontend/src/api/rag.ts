import { request } from "./client";

/** Asks the server to load the generation model before the next question (throttled server-side). */
export function warmGenerationModel(): Promise<void> {
  return request<unknown>("/rag/warmup", { method: "POST" }).then(() => undefined);
}
