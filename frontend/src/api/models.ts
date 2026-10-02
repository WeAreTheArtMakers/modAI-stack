import type { ManagedModel, ModelProviderStatus, ModelSystemStatus } from "../types";
import { request } from "./client";

function modelPath(provider: string, model: string): string {
  return `${encodeURIComponent(provider)}/${model.split("/").map(encodeURIComponent).join("/")}`;
}

export function listModelProviders(): Promise<ModelProviderStatus[]> {
  return request<ModelProviderStatus[]>("/models/providers");
}

export function listManagedModels(provider = "ollama"): Promise<ManagedModel[]> {
  return request<ManagedModel[]>(`/models?provider=${encodeURIComponent(provider)}`);
}

export function getModelStatus(): Promise<ModelSystemStatus> {
  return request<ModelSystemStatus>("/models/status");
}

export function deleteManagedModel(provider: string, model: string): Promise<void> {
  return request<void>(`/models/${modelPath(provider, model)}`, { method: "DELETE" });
}
