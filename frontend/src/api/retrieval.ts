import type { RetrievalProfileCatalog, RetrievalProfileStatus } from "../types";
import { request } from "./client";

export function getRetrievalProfiles(): Promise<RetrievalProfileCatalog> {
  return request<RetrievalProfileCatalog>("/retrieval/profiles");
}

export function getRetrievalStatus(): Promise<RetrievalProfileStatus> {
  return request<RetrievalProfileStatus>("/retrieval/status");
}
