import { AlertCircle, LoaderCircle } from "lucide-react";
import type { ReactNode } from "react";
import { getErrorMessage } from "../api/client";

export function LoadingState({ label = "Yükleniyor" }: { label?: string }) {
  return <div className="flex min-h-40 items-center justify-center gap-3 text-sm text-slate-500"><LoaderCircle className="animate-spin" size={18} /> {label}</div>;
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  return <div className="panel flex items-center justify-between gap-4 p-5 text-sm text-red-700"><div className="flex items-center gap-3"><AlertCircle size={18} /><span>{getErrorMessage(error)}</span></div>{onRetry && <button className="button-secondary" onClick={onRetry}>Tekrar dene</button>}</div>;
}

export function EmptyState({ icon, title, description, action }: { icon: ReactNode; title: string; description: string; action?: ReactNode }) {
  return <div className="panel flex min-h-56 flex-col items-center justify-center px-6 text-center"><div className="mb-4 rounded-2xl bg-cloud p-3 text-slate-500">{icon}</div><h3 className="font-semibold text-ink">{title}</h3><p className="mt-2 max-w-md text-sm text-slate-500">{description}</p>{action && <div className="mt-5">{action}</div>}</div>;
}
