import type { HealthState } from "../types";
import { request } from "./client";

export function getHealth(): Promise<HealthState> {
  return request<HealthState>("/health", {}, false);
}

export function getReadiness(): Promise<HealthState> {
  return request<HealthState>("/ready", {}, false);
}
