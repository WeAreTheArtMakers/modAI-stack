import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, CircleSlash2, Database, Gauge, Network, Server, TriangleAlert } from "lucide-react";
import { getHealth } from "../api/health";
import { getModelStatus } from "../api/models";
import { PageHeader } from "../components/PageHeader";
import { ErrorState, LoadingState } from "../components/State";

export function SystemPage() {
  const health = useQuery({ queryKey: ["health"], queryFn: getHealth, refetchInterval: 30_000 }); const models = useQuery({ queryKey: ["model-status"], queryFn: getModelStatus, refetchInterval: 30_000 });
  if (health.isLoading || models.isLoading) return <LoadingState label="Servis durumu okunuyor" />;
  if (health.error && models.error) return <ErrorState error={health.error} />;
  const ollama = models.data?.providers.find((provider) => provider.provider === "ollama");
  const services = [{ name: "API", detail: "FastAPI", ok: health.data?.status === "ok", icon: Server }, { name: "Ollama", detail: models.data?.generation.configured_model ?? "Yerel model sağlayıcısı", ok: ollama?.ready, icon: Gauge }, { name: "Embedding", detail: models.data?.embedding.configured_model ?? "Model hazırlanıyor", ok: models.data?.embedding.ready, icon: Gauge }, { name: "PostgreSQL", detail: "Kalıcı veri", ok: undefined, icon: Database }, { name: "Redis", detail: "İndeks kuyruğu", ok: undefined, icon: Network }, { name: "Qdrant", detail: "Vektör arama", ok: undefined, icon: Server }];
  return <><PageHeader eyebrow="Sistem" title="Platform durumu" description="Uygulamanın yayınladığı sağlık sinyalleri ve Compose servisleri." /><div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{services.map(({ name, detail, ok, icon: Icon }) => <div className="panel flex items-center gap-4 p-5" key={name}><span className="flex h-11 w-11 items-center justify-center rounded-xl bg-cloud text-slate-600"><Icon size={20} /></span><div className="min-w-0 flex-1"><p className="font-semibold text-ink">{name}</p><p className="mt-1 truncate text-xs text-slate-500" title={detail}>{detail}</p></div>{ok === undefined ? <span className="flex items-center gap-1.5 text-xs font-semibold text-slate-400"><TriangleAlert size={14} /> API sinyali yok</span> : ok ? <span className="flex items-center gap-1.5 text-xs font-semibold text-emerald-600"><CheckCircle2 size={15} /> Hazır</span> : <span className="flex items-center gap-1.5 text-xs font-semibold text-red-600"><CircleSlash2 size={15} /> Ulaşılamıyor</span>}</div>)}</div><div className="panel mt-6 flex gap-4 p-5"><Gauge className="mt-0.5 shrink-0 text-cyan" size={19} /><p className="text-sm leading-6 text-slate-500">Ollama ve embedding durumu Model Manager ile aynı API sinyalinden gelir. PostgreSQL, Redis ve Qdrant için ayrı sağlık endpoint'i mevcut değil; bu servisler Docker Compose tarafından yönetilir.</p></div></>;
}
