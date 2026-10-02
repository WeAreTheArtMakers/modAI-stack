import type { Workspace } from "../types";
import { request } from "./client";

export function listWorkspaces(): Promise<Workspace[]> {
  return request<Workspace[]>("/workspaces");
}
