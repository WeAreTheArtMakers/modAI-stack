import type { HealthState, ReadinessState } from "../types";
import { request } from "./client";

export function getHealth(): Promise<HealthState> {
  return request<HealthState>("/health", {}, false);
}

export function getReadiness(): Promise<ReadinessState> {
  return request<ReadinessState>("/ready", {}, false);
}
