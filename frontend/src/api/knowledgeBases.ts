import type { KnowledgeBase } from "../types";
import { request } from "./client";

export function listKnowledgeBases(): Promise<KnowledgeBase[]> {
  return request<KnowledgeBase[]>("/knowledge-bases");
}

export function createKnowledgeBase(
  workspaceId: number,
  payload: { name: string; description?: string },
): Promise<KnowledgeBase> {
  return request<KnowledgeBase>(`/knowledge-bases?workspace_id=${workspaceId}`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
