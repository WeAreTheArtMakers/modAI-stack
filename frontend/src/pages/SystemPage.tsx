import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, CircleSlash2, Database, Gauge, Network, Server, TriangleAlert } from "lucide-react";
import { getHealth, getReadiness } from "../api/health";
import { PageHeader } from "../components/PageHeader";
import { ErrorState, LoadingState } from "../components/State";

export function SystemPage() {
  const health = useQuery({ queryKey: ["health"], queryFn: getHealth, refetchInterval: 30_000 }); const ready = useQuery({ queryKey: ["readiness"], queryFn: getReadiness, refetchInterval: 30_000 });
  if (health.isLoading || ready.isLoading) return <LoadingState label="Servis durumu okunuyor" />;
  if (health.error && ready.error) return <ErrorState error={health.error} />;
  const services = [{ name: "API", detail: "FastAPI", ok: health.data?.status === "ok", icon: Server }, { name: "Ollama", detail: "Yerel model sağlayıcısı", ok: ready.data?.ollama === true, icon: Gauge }, { name: "PostgreSQL", detail: "Kalıcı veri", ok: undefined, icon: Database }, { name: "Redis", detail: "İndeks kuyruğu", ok: undefined, icon: Network }, { name: "Qdrant", detail: "Vektör arama", ok: undefined, icon: Server }];
  return <><PageHeader eyebrow="Sistem" title="Platform durumu" description="Uygulamanın yayınladığı sağlık sinyalleri ve Compose servisleri." /><div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{services.map(({ name, detail, ok, icon: Icon }) => <div className="panel flex items-center gap-4 p-5" key={name}><span className="flex h-11 w-11 items-center justify-center rounded-xl bg-cloud text-slate-600"><Icon size={20} /></span><div className="min-w-0 flex-1"><p className="font-semibold text-ink">{name}</p><p className="mt-1 text-xs text-slate-500">{detail}</p></div>{ok === undefined ? <span className="flex items-center gap-1.5 text-xs font-semibold text-slate-400"><TriangleAlert size={14} /> API sinyali yok</span> : ok ? <span className="flex items-center gap-1.5 text-xs font-semibold text-emerald-600"><CheckCircle2 size={15} /> Hazır</span> : <span className="flex items-center gap-1.5 text-xs font-semibold text-red-600"><CircleSlash2 size={15} /> Ulaşılamıyor</span>}</div>)}</div><div className="panel mt-6 flex gap-4 p-5"><Gauge className="mt-0.5 shrink-0 text-cyan" size={19} /><p className="text-sm leading-6 text-slate-500">PostgreSQL, Redis ve Qdrant için ayrı sağlık endpoint'i mevcut değil; bu servisler Docker Compose tarafından yönetilir. Buradaki gösterim, backend'in yayınladığı API/Ollama sinyallerini diğer servislerden ayırır.</p></div></>;
}
