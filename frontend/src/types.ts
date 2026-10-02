export type Role = "admin" | "manager" | "user";

export interface OrganizationAccess {
  id: number;
  name: string;
  slug: string;
  membership_role: Role;
}

export interface Workspace {
  id: number;
  organization_id: number;
  name: string;
  slug: string;
  membership_role: Role;
}

export interface UserContext {
  id: number;
  email: string;
  role: Role;
  organizations: OrganizationAccess[];
  workspaces: Workspace[];
}

export interface KnowledgeBase {
  id: number;
  workspace_id: number;
  name: string;
  slug: string;
  description: string | null;
  membership_role: Role | null;
}

export interface DocumentItem {
  id: number;
  filename: string;
  knowledge_base_id: number | null;
  file_size: number;
  active_version: number;
  index_status: "queued" | "processing" | "ready" | "failed" | string;
  index_error: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface DocumentPage {
  items: DocumentItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface DocumentVersion {
  version: number;
  status: string;
  content_hash: string;
  file_size: number;
  created_at: string | null;
}

export interface Source {
  document: string;
  score: number;
  document_id: number | null;
  chunk_index: number | null;
  text: string | null;
}

export interface IndexingEvent {
  type: "index_progress";
  organization_id: number | null;
  workspace_id: number;
  knowledge_base_id: number | null;
  document_id: number;
  job_id: string;
  status: DocumentItem["index_status"];
  stage: string;
}

export type RagEvent =
  | { type: "sources"; data: Source[] }
  | { type: "token"; data: string }
  | { type: "complete" }
  | { type: "error"; data: string };

export interface HealthState {
  status: string;
  ollama?: boolean;
}
