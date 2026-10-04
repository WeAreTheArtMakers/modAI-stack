import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { listWorkspaces } from "../api/workspaces";
import { useAuth } from "../auth/AuthContext";
import type { Workspace } from "../types";

interface WorkspaceContextValue {
  workspaces: Workspace[];
  current: Workspace | null;
  setCurrentId: (id: number) => void;
  loading: boolean;
}
const WorkspaceContext = createContext<WorkspaceContextValue | undefined>(undefined);

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const query = useQuery({ queryKey: ["workspaces", user?.id], queryFn: listWorkspaces, enabled: Boolean(user) });
  const [currentId, setCurrentId] = useState<number | null>(() => {
    const saved = localStorage.getItem("modai.workspace_id");
    return saved ? Number(saved) : null;
  });
  useEffect(() => {
    if (!query.data?.length) return;
    const valid = query.data.some((workspace) => workspace.id === currentId);
    if (!valid) setCurrentId(query.data[0].id);
  }, [query.data, currentId]);
  const current = query.data?.find((workspace) => workspace.id === currentId) ?? query.data?.[0] ?? null;
  const value = useMemo(() => ({
    workspaces: query.data ?? [], current,
    setCurrentId(id: number) { setCurrentId(id); localStorage.setItem("modai.workspace_id", String(id)); },
    loading: query.isLoading,
  }), [query.data, current, query.isLoading]);
  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspace() {
  const value = useContext(WorkspaceContext);
  if (!value) throw new Error("useWorkspace must be used within WorkspaceProvider");
  return value;
}
