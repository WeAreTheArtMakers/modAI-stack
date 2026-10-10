import type { DocumentItem, DocumentPage, DocumentVersion } from "../types";
import { request } from "./client";

export function listDocuments(params: {
  knowledgeBaseId?: number;
  limit?: number;
  offset?: number;
} = {}): Promise<DocumentPage> {
  const search = new URLSearchParams();
  if (params.knowledgeBaseId) search.set("knowledge_base_id", String(params.knowledgeBaseId));
  search.set("limit", String(params.limit ?? 100));
  search.set("offset", String(params.offset ?? 0));
  return request<DocumentPage>(`/documents?${search.toString()}`);
}

export async function uploadDocuments(
  files: File[],
  knowledgeBaseId: number,
): Promise<DocumentItem[]> {
  const form = new FormData();
  form.set("knowledge_base_id", String(knowledgeBaseId));
  files.forEach((file) => form.append("files", file));
  const path = files.length === 1 ? "/documents/upload" : "/documents/upload-batch";
  if (files.length === 1) {
    const single = new FormData();
    single.set("knowledge_base_id", String(knowledgeBaseId));
    single.set("file", files[0]);
    return [await request<DocumentItem>(path, { method: "POST", body: single })];
  }
  return request<DocumentItem[]>(path, { method: "POST", body: form });
}

export function reindexDocument(id: number): Promise<DocumentItem> {
  return request<DocumentItem>(`/documents/${id}/reindex`, { method: "POST" });
}

export function replaceDocument(id: number, file: File): Promise<DocumentItem> {
  const form = new FormData();
  form.set("file", file);
  return request<DocumentItem>(`/documents/${id}/replace`, { method: "POST", body: form });
}

export function archiveDocument(id: number): Promise<DocumentItem> {
  return request<DocumentItem>(`/documents/${id}/archive`, { method: "POST" });
}

export function unarchiveDocument(id: number): Promise<DocumentItem> {
  return request<DocumentItem>(`/documents/${id}/unarchive`, { method: "POST" });
}

export function listDocumentVersions(id: number): Promise<DocumentVersion[]> {
  return request<DocumentVersion[]>(`/documents/${id}/versions`);
}

export function deleteDocument(id: number): Promise<void> {
  return request<void>(`/documents/${id}`, { method: "DELETE" });
}
