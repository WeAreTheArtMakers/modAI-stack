import { statusLabel, statusTone } from "../lib";

export function StatusBadge({ status }: { status: string }) {
  return <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ${statusTone(status)}`}><span className={`h-1.5 w-1.5 rounded-full ${status === "ready" ? "bg-emerald-500" : status === "failed" ? "bg-red-500" : status === "processing" ? "bg-cyan" : "bg-amber-400"}`} />{statusLabel(status)}</span>;
}
