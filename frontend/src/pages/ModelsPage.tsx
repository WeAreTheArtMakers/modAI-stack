import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, CircleSlash2, Cpu, Download, LoaderCircle, ShieldAlert, Trash2 } from "lucide-react";
import { useState } from "react";
import { deleteManagedModel, listManagedModels, getModelStatus } from "../api/models";
import { getErrorMessage } from "../api/client";
import { streamModelPull } from "../api/websocket";
import { useAuth } from "../auth/AuthContext";
import { PageHeader } from "../components/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "../components/State";
import type { ManagedModel, ModelPullEvent } from "../types";

function bytes(value: number | null): string {
  if (value === null) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let amount = value;
  let index = 0;
  while (amount >= 1024 && index < units.length - 1) { amount /= 1024; index += 1; }
  return `${amount.toFixed(index > 1 ? 1 : 0)} ${units[index]}`;
}

function availability(ready: boolean) {
  return ready
    ? <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-emerald-600"><CheckCircle2 size={15} /> Hazır</span>
    : <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-red-600"><CircleSlash2 size={15} /> Ulaşılamıyor</span>;
}

function PullProgress({ event }: { event: ModelPullEvent | null }) {
  if (!event || event.type !== "model_pull_progress") return null;
  const percent = event.completed !== null && event.total && event.total > 0 ? Math.round((event.completed / event.total) * 100) : null;
  return <div className="mt-4 rounded-xl border border-cyan/20 bg-cyan/5 p-4" role="status"><div className="flex items-center gap-2 text-sm font-medium text-ink"><LoaderCircle className="animate-spin text-cyan" size={16} />{event.status}</div>{percent !== null && <><div className="mt-3 h-1.5 overflow-hidden rounded-full bg-cyan/15"><div className="h-full rounded-full bg-cyan transition-all" style={{ width: `${percent}%` }} /></div><p className="mt-2 text-xs text-slate-500">{percent}% · {bytes(event.completed)} / {bytes(event.total)}</p></>}</div>;
}

export function ModelsPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const isAdmin = user?.role === "admin";
  const [modelName, setModelName] = useState("");
  const [pulling, setPulling] = useState(false);
  const [pullEvent, setPullEvent] = useState<ModelPullEvent | null>(null);
  const [pullError, setPullError] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<ManagedModel | null>(null);
  const [deleting, setDeleting] = useState(false);
  const status = useQuery({ queryKey: ["model-status"], queryFn: getModelStatus, refetchInterval: 30_000 });
  const models = useQuery({ queryKey: ["managed-models", "ollama"], queryFn: () => listManagedModels("ollama"), refetchInterval: 30_000 });
  const refresh = () => { void queryClient.invalidateQueries({ queryKey: ["model-status"] }); void queryClient.invalidateQueries({ queryKey: ["managed-models"] }); };

  const pull = async () => {
    if (!modelName.trim() || pulling) return;
    setPulling(true); setPullError(null); setPullEvent(null);
    try {
      await streamModelPull(modelName.trim(), (event) => setPullEvent(event));
      refresh();
    } catch (error) { setPullError(getErrorMessage(error)); }
    finally { setPulling(false); }
  };
  const remove = async () => {
    if (!deleteTarget || deleting) return;
    setDeleting(true);
    try { await deleteManagedModel(deleteTarget.provider, deleteTarget.name); setDeleteTarget(null); refresh(); }
    finally { setDeleting(false); }
  };

  if (status.isLoading || models.isLoading) return <LoadingState label="Model çalışma zamanı okunuyor" />;
  if (status.error && models.error) return <ErrorState error={status.error} onRetry={() => { void status.refetch(); void models.refetch(); }} />;
  const system = status.data;
  const provider = system?.providers.find((item) => item.provider === "ollama");

  return <><PageHeader eyebrow="Model Manager" title="Yerel modeller" description="Ollama çalışma zamanını, üretim modelini ve embedding hazırlığını tek yerden görün." />
    <div className="grid gap-4 xl:grid-cols-3">
      <section className="panel p-5"><p className="eyebrow">Provider durumu</p><div className="mt-4 flex items-center gap-3"><span className="flex h-11 w-11 items-center justify-center rounded-xl bg-cloud text-cyan"><Cpu size={21} /></span><div className="min-w-0"><p className="font-semibold text-ink">Ollama</p><p className="mt-1 truncate text-xs text-slate-500" title={provider?.endpoint}>{provider?.endpoint ?? "Durum okunamadı"}</p></div></div><div className="mt-4">{provider ? availability(provider.ready) : <span className="text-xs text-slate-500">Sinyal yok</span>}</div></section>
      <section className="panel p-5"><p className="eyebrow">Generation modeli</p><p className="mt-4 truncate font-semibold text-ink" title={system?.generation.configured_model}>{system?.generation.configured_model ?? "Yapılandırılmadı"}</p><p className="mt-1 text-xs text-slate-500">{system?.generation.provider ?? "ollama"} · {system?.generation.running ? "çalışıyor" : "çalışmıyor"}</p><div className="mt-4">{system ? availability(system.generation.ready) : <span className="text-xs text-slate-500">Sinyal yok</span>}</div></section>
      <section className="panel p-5"><p className="eyebrow">Embedding modeli</p><p className="mt-4 truncate font-semibold text-ink" title={system?.embedding.configured_model}>{system?.embedding.configured_model ?? "Yapılandırılmadı"}</p><p className="mt-1 text-xs text-slate-500">{system?.embedding.source === "local_path" ? "Yerel dizin" : "Model önbelleği"} · indirme {system?.embedding.download_allowed ? "açık" : "kapalı"}</p><div className="mt-4">{system ? availability(system.embedding.ready) : <span className="text-xs text-slate-500">Sinyal yok</span>}</div>{system?.embedding.status === "unavailable" && <p className="mt-3 text-xs leading-5 text-amber-700">Model önbellekte bulunmuyor. Bağlantılı ortamda hazırlayın veya güvenli yerel model dizini yapılandırın.</p>}</section>
    </div>

    {isAdmin ? <section className="panel mt-6 p-5"><div className="flex flex-col gap-4 sm:flex-row sm:items-end"><label className="flex-1"><span className="mb-2 block text-sm font-medium text-ink">Ollama modeli çek</span><input className="field" value={modelName} onChange={(event) => setModelName(event.target.value)} placeholder="ör. llama3.2:3b" disabled={pulling} /></label><button className="button-primary inline-flex items-center justify-center gap-2" onClick={() => void pull()} disabled={pulling || !modelName.trim()}><Download size={17} />{pulling ? "İndiriliyor" : "Modeli çek"}</button></div>{pullError && <p className="mt-3 text-sm text-red-700" role="alert">{pullError}</p>}<PullProgress event={pullEvent} /></section> : <section className="panel mt-6 flex items-center gap-3 p-5 text-sm text-slate-600"><ShieldAlert className="shrink-0 text-amber-500" size={20} />Model çekme ve silme yalnızca platform yöneticileri tarafından yapılabilir.</section>}

    <section className="panel mt-6 overflow-hidden"><div className="flex items-center justify-between border-b border-slate-100 px-5 py-4"><div><p className="font-semibold text-ink">Yüklü modeller</p><p className="mt-1 text-xs text-slate-500">Ollama'nın yerel olarak bildirdiği modeller.</p></div>{models.error && <span className="text-xs font-medium text-red-700">Liste alınamadı</span>}</div>{models.error ? <div className="p-5"><ErrorState error={models.error} onRetry={() => { void models.refetch(); }} /></div> : models.data?.length ? <div className="overflow-x-auto"><table className="min-w-full text-left text-sm"><thead className="bg-cloud text-xs font-semibold uppercase tracking-wide text-slate-500"><tr><th className="px-5 py-3">Model</th><th className="px-5 py-3">Boyut</th><th className="px-5 py-3">Aile</th><th className="px-5 py-3">Quantization</th><th className="px-5 py-3">Bağlam</th><th className="px-5 py-3 text-right">İşlem</th></tr></thead><tbody className="divide-y divide-slate-100">{models.data.map((model) => <tr key={`${model.provider}/${model.name}`}><td className="px-5 py-4 font-medium text-ink">{model.name}<p className="mt-1 text-xs font-normal text-slate-500">{model.modified_at ? new Date(model.modified_at).toLocaleDateString("tr-TR") : "Tarih yok"}</p></td><td className="px-5 py-4 text-slate-600">{bytes(model.size)}</td><td className="px-5 py-4 text-slate-600">{model.family ?? "—"}{model.parameter_size && <p className="mt-1 text-xs text-slate-400">{model.parameter_size}</p>}</td><td className="px-5 py-4 text-slate-600">{model.quantization ?? "—"}</td><td className="px-5 py-4 text-slate-600">{model.context_length?.toLocaleString("tr-TR") ?? "—"}</td><td className="px-5 py-4 text-right">{isAdmin && <button className="button-secondary inline-flex items-center gap-2 border-red-100 text-red-700 hover:bg-red-50" onClick={() => setDeleteTarget(model)}><Trash2 size={15} />Sil</button>}</td></tr>)}</tbody></table></div> : <EmptyState icon={<Cpu size={22} />} title="Yüklü model yok" description={provider?.ready ? "Bir Ollama modelini güvenle çekerek başlayın." : "Ollama erişilebilir olduğunda yüklü modeller burada görünür."} />}</section>

    {deleteTarget && <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 p-5" role="dialog" aria-modal="true" aria-labelledby="delete-model-title"><div className="panel w-full max-w-md p-6 shadow-xl"><h2 id="delete-model-title" className="text-lg font-semibold text-ink">Model silinsin mi?</h2><p className="mt-3 text-sm leading-6 text-slate-600"><strong>{deleteTarget.name}</strong> Ollama yerel deposundan silinecek. Yapılandırılmış aktif generation modeli silinemez.</p><div className="mt-6 flex justify-end gap-3"><button className="button-secondary" onClick={() => setDeleteTarget(null)} disabled={deleting}>Vazgeç</button><button className="button-primary bg-red-700 hover:bg-red-800" onClick={() => void remove()} disabled={deleting}>{deleting ? "Siliniyor" : "Sil"}</button></div></div></div>}
  </>;
}
