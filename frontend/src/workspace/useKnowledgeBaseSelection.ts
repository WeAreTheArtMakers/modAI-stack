import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router";
import { listKnowledgeBases } from "../api/knowledgeBases";
import { useWorkspace } from "./WorkspaceContext";

/** Knowledge Bases of the current workspace the user may query, and the selected subset. */
export function useKnowledgeBaseSelection() {
  const [searchParams] = useSearchParams();
  const { current } = useWorkspace();
  const kbs = useQuery({ queryKey: ["knowledge-bases"], queryFn: listKnowledgeBases });
  const available = useMemo(() => kbs.data?.filter((kb) => kb.workspace_id === current?.id) ?? [], [kbs.data, current?.id]);
  const [selected, setSelected] = useState<number[]>([]);
  const requestedKb = searchParams.get("kb");
  useEffect(() => {
    const requestedId = requestedKb && /^\d+$/.test(requestedKb) ? Number(requestedKb) : null;
    const authorizedRequest = requestedId !== null && Number.isSafeInteger(requestedId) && available.some((kb) => kb.id === requestedId);
    setSelected((previous) => {
      const next = authorizedRequest ? [requestedId] : previous.filter((id) => available.some((kb) => kb.id === id));
      if (!next.length && available.length === 1) next.push(available[0].id);
      return next.length === previous.length && next.every((id, index) => id === previous[index]) ? previous : next;
    });
  }, [available, requestedKb]);
  function toggle(id: number) { setSelected((currentSelection) => currentSelection.includes(id) ? currentSelection.filter((item) => item !== id) : [...currentSelection, id]); }
  return { current, kbs, available, selected, toggle };
}
