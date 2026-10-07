import { useQuery } from "@tanstack/react-query";
import {
  CheckCircle2,
  CircleSlash2,
  Database,
  Gauge,
  Globe2,
  Network,
  Server,
  TriangleAlert,
} from "lucide-react";
import { getReadiness } from "../api/health";
import { getBackendVersion } from "../api/version";
import { getModelStatus } from "../api/models";
import { getRetrievalProfiles } from "../api/retrieval";
import { PageHeader } from "../components/PageHeader";
import { ErrorState, LoadingState } from "../components/State";
import type { RetrievalProfile, RetrievalProfileAvailability } from "../types";
import { FRONTEND_BUILD_SHA, isReleaseSha, shortSha, versionsMismatch } from "../version";

const availabilityLabels: Record<RetrievalProfileAvailability, string> = {
  active: "Aktif",
  available_after_provisioning: "Model sağlandıktan sonra",
  experimental: "Deneysel",
  not_configured: "Yapılandırılmadı",
};

function ProfileCard({ profile }: { profile: RetrievalProfile }) {
  const activeClasses = profile.active
    ? "border-cyan/50 bg-cyan/[0.04]"
    : "border-slate-200 bg-white";

  return (
    <article
      className={`rounded-2xl border p-5 ${activeClasses}`}
      aria-label={`${profile.display_name}: ${availabilityLabels[profile.availability]}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="font-semibold text-ink">{profile.display_name}</h3>
          <p className="mt-2 text-sm leading-6 text-slate-600">{profile.description}</p>
        </div>
        <span
          className={`rounded-full px-3 py-1 text-xs font-semibold ${profile.active ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600"}`}
        >
          {availabilityLabels[profile.availability]}
        </span>
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        {profile.language_capabilities.map((language) => (
          <span key={language} className="rounded-lg bg-cloud px-2.5 py-1 text-xs text-slate-600">
            {language}
          </span>
        ))}
      </div>
      <p className="mt-4 text-xs font-medium text-slate-500">Kaynak sınıfı: {profile.hardware_class}</p>
    </article>
  );
}

export function ReleaseBuildPanel({
  frontendBuildSha = FRONTEND_BUILD_SHA,
  backendBuildSha,
}: {
  frontendBuildSha?: string;
  backendBuildSha?: string;
}) {
  const versionMismatch = versionsMismatch(frontendBuildSha, backendBuildSha);
  const versionsSynced = isReleaseSha(frontendBuildSha)
    && isReleaseSha(backendBuildSha)
    && !versionMismatch;

  return (
    <section className="panel mt-6 p-5 sm:p-6" aria-labelledby="release-build-heading">
      <p className="eyebrow">Release / Build</p>
      <h2 id="release-build-heading" className="mt-2 text-xl font-bold text-ink">Dağıtım sürümü</h2>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <div className="rounded-xl bg-cloud p-4">
          <p className="text-xs font-semibold text-slate-500">Frontend</p>
          <p className="mt-1 font-mono text-sm text-ink" title={frontendBuildSha}>{shortSha(frontendBuildSha)}</p>
        </div>
        <div className="rounded-xl bg-cloud p-4">
          <p className="text-xs font-semibold text-slate-500">Backend</p>
          <p className="mt-1 font-mono text-sm text-ink" title={backendBuildSha ?? "Backend version unavailable"}>
            {backendBuildSha ? shortSha(backendBuildSha) : "Development build"}
          </p>
        </div>
      </div>
      <p className={`mt-4 text-sm font-semibold ${versionMismatch ? "text-amber-700 dark:text-amber-300" : "text-emerald-700 dark:text-emerald-300"}`}>
        {versionMismatch ? "Version mismatch" : versionsSynced ? "Synced" : "Development build"}
      </p>
    </section>
  );
}

export function SystemPage() {
  const readiness = useQuery({ queryKey: ["readiness"], queryFn: getReadiness, refetchInterval: 30_000 });
  const models = useQuery({ queryKey: ["model-status"], queryFn: getModelStatus, refetchInterval: 30_000 });
  const backendVersion = useQuery({ queryKey: ["backend-version"], queryFn: getBackendVersion, retry: false });
  const profiles = useQuery({
    queryKey: ["retrieval-profiles"],
    queryFn: getRetrievalProfiles,
    refetchInterval: 60_000,
  });

  if (readiness.isLoading || models.isLoading || profiles.isLoading) {
    return <LoadingState label="Servis ve arama profili durumu okunuyor" />;
  }
  if (readiness.error && models.error && profiles.error) {
    return <ErrorState error={readiness.error} />;
  }

  const ollama = models.data?.providers.find((provider) => provider.provider === "ollama");
  const backendBuildSha = backendVersion.data?.build_sha;
  const activeProfile = profiles.data?.profiles.find((profile) => profile.active);
  const services = [
    { name: "API", detail: "FastAPI", ok: readiness.data ? true : readiness.error ? false : undefined, icon: Server },
    {
      name: "Ollama",
      detail: models.data?.generation.configured_model ?? "Yerel model sağlayıcısı",
      ok: readiness.data?.ollama.ready ?? ollama?.ready,
      icon: Gauge,
    },
    {
      name: "Embedding",
      detail: activeProfile?.display_name ?? "Profil eşlemesi bulunamadı",
      ok: readiness.data?.embedding.ready ?? models.data?.embedding.ready,
      icon: Globe2,
    },
    { name: "PostgreSQL", detail: "Kalıcı veri", ok: readiness.data?.dependencies.postgres, icon: Database },
    { name: "Redis", detail: "İndeks kuyruğu", ok: readiness.data?.dependencies.redis, icon: Network },
    { name: "Qdrant", detail: "Vektör arama", ok: readiness.data?.dependencies.qdrant, icon: Server },
  ];

  return (
    <>
      <PageHeader
        eyebrow="Sistem"
        title="Platform durumu"
        description="Yerel servis sinyalleri ve çalışma alanınızın arama profili."
      />

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {services.map(({ name, detail, ok, icon: Icon }) => (
          <div className="panel flex items-center gap-4 p-5" key={name}>
            <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-cloud text-slate-600">
              <Icon size={20} />
            </span>
            <div className="min-w-0 flex-1">
              <p className="font-semibold text-ink">{name}</p>
              <p className="mt-1 truncate text-xs text-slate-500" title={detail}>{detail}</p>
            </div>
            {ok === undefined ? (
              <span className="flex items-center gap-1.5 text-xs font-semibold text-slate-400">
                <TriangleAlert size={14} /> API sinyali yok
              </span>
            ) : ok ? (
              <span className="flex items-center gap-1.5 text-xs font-semibold text-emerald-600">
                <CheckCircle2 size={15} /> Hazır
              </span>
            ) : (
              <span className="flex items-center gap-1.5 text-xs font-semibold text-red-600">
                <CircleSlash2 size={15} /> Ulaşılamıyor
              </span>
            )}
          </div>
        ))}
      </div>

      <ReleaseBuildPanel backendBuildSha={backendBuildSha} />

      <section className="panel mt-6 p-5 sm:p-6" aria-labelledby="retrieval-profile-heading">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <p className="eyebrow">Search / Retrieval Profile</p>
            <h2 id="retrieval-profile-heading" className="mt-2 text-xl font-bold text-ink">
              Etkin arama profili
            </h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
              Profil adları dil ve yerel kaynak ihtiyacını anlatır; düşük seviye model kimlikleri bu katalogda gösterilmez.
            </p>
          </div>
          <span className="rounded-full bg-slate-100 px-3 py-1.5 text-xs font-semibold text-slate-600">
            Profil değiştirme kapalı
          </span>
        </div>

        {profiles.error ? (
          <p className="mt-5 rounded-xl bg-amber-50 p-4 text-sm text-amber-800">
            Arama profili kataloğu şu anda alınamıyor; mevcut retrieval yapılandırmasına dokunulmadı.
          </p>
        ) : (
          <>
            {activeProfile ? (
              <div className="mt-5 rounded-2xl border border-cyan/30 bg-cyan/[0.04] p-5">
                <div className="flex items-start gap-3">
                  <span className="mt-0.5 rounded-xl bg-white p-2 text-cyan"><Globe2 size={20} /></span>
                  <div>
                    <p className="text-xs font-bold uppercase tracking-wide text-cyan">Aktif yapılandırma eşleşmesi</p>
                    <h3 className="mt-1 text-lg font-bold text-ink">{activeProfile.display_name}</h3>
                    <p className="mt-1 text-sm text-slate-600">{activeProfile.description}</p>
                  </div>
                </div>
              </div>
            ) : (
              <div className="mt-5 rounded-2xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-900">
                Geçerli embedding yapılandırması katalogdaki profillerle eşleşmiyor. Bu ekran model kimliğini veya dosya yolunu göstermez.
              </div>
            )}

            <div className="mt-5 grid gap-4 lg:grid-cols-2">
              {profiles.data?.profiles.map((profile) => <ProfileCard key={profile.profile_id} profile={profile} />)}
            </div>
            <p className="mt-5 rounded-xl bg-cloud p-4 text-sm leading-6 text-slate-600">
              Katalog salt okunurdur; burada seçim veya yeniden indeksleme başlatılamaz. Embedding değişimi vektör uzayını ya da boyutunu değiştirebilir ve mevcut belgelerin kontrollü biçimde yeniden indekslenmesini gerektirir. Türkçe retrieval kalitesi ayrıca ölçülmelidir.
            </p>
          </>
        )}
      </section>

      <div className="panel mt-6 flex gap-4 p-5">
        <Gauge className="mt-0.5 shrink-0 text-cyan" size={19} />
        <p className="text-sm leading-6 text-slate-500">
          PostgreSQL, Redis, Qdrant, Ollama ve embedding hazırlığı sunucunun /ready yanıtından okunur. Servisler hazır değilse yöneticinize bildirin.
        </p>
      </div>
    </>
  );
}
