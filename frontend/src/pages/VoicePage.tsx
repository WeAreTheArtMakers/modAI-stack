import { useRef, useState, type FormEvent, type KeyboardEvent, type PointerEvent } from "react";
import { Link } from "react-router";
import { AudioLines, Download, FileText, Lock, Mic, Send, Square, Volume2, VolumeX, X } from "lucide-react";
import { PageHeader } from "../components/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "../components/State";
import { useAuth } from "../auth/AuthContext";
import { canManage } from "../lib";
import { useKnowledgeBaseSelection } from "../workspace/useKnowledgeBaseSelection";
import { SourceCard } from "./ChatPage";
import { EMA_LIGHTNING, ORT_RUNTIME_BYTES, WHISPER } from "../voice/config";
import { VoiceMascot, phaseLabel } from "../voice/VoiceMascot";
import { useVoiceAssistant, type TurnMetrics, type VoiceDependencies, type VoicePhase } from "../voice/useVoiceAssistant";
import type { LoadState } from "../voice/voiceEngine";

const HOLD_MS = 400;
const FIRST_USE_MB = Math.round((WHISPER.downloadBytes + EMA_LIGHTNING.downloadBytes + ORT_RUNTIME_BYTES) / 1e6);

const HINTS: Record<VoicePhase, string> = {
  idle: "Basılı tutup konuşun, bırakınca yanıtlarım. Ya da bir kez dokunun, bitince tekrar dokunun.",
  listening: "Konuşun… Bitirdiğinizde düğmeyi bırakın ya da tekrar dokunun.",
  transcribing: "Konuşmanız bu cihazda yazıya çevriliyor.",
  thinking: "Yetkili belgelerinizde yanıt aranıyor.",
  speaking: "Yanıtı durdurmak için Durdur'a, yeni soru için mikrofona basın.",
  error: "Tekrar denemek için mikrofona basın.",
};

function seconds(ms?: number): string | null {
  return ms === undefined ? null : `${(ms / 1000).toFixed(1)} sn`;
}

function MetricsLine({ metrics }: { metrics: TurnMetrics }) {
  const parts = [
    metrics.sttMs !== undefined && `yazıya çevirme ${seconds(metrics.sttMs)}`,
    metrics.firstTokenMs !== undefined && `ilk kelime ${seconds(metrics.firstTokenMs)}`,
    metrics.firstAudioMs !== undefined && `ilk ses ${seconds(metrics.firstAudioMs)}`,
    metrics.completeMs !== undefined && `tamamı ${seconds(metrics.completeMs)}`,
  ].filter(Boolean);
  return parts.length ? <p className="mt-2 text-[11px] text-slate-400" data-testid="turn-metrics">{parts.join(" · ")}</p> : null;
}

function ProgressRow({ label, state }: { label: string; state: LoadState }) {
  const percent = state.status === "ready" ? 100 : state.total ? Math.min(100, Math.round((state.loaded / state.total) * 100)) : 0;
  const status = state.status === "ready" ? `Hazır${state.backend ? ` · ${state.backend === "webgpu" ? "WebGPU" : "WASM"}` : ""}` : state.status === "error" ? "Başlatılamadı" : state.status === "loading" ? `%${percent}` : "Bekliyor";
  return <div><div className="flex justify-between text-xs"><span className="text-slate-300">{label}</span><span className={state.status === "error" ? "text-red-300" : "text-slate-400"}>{status}</span></div><div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-white/10" role="progressbar" aria-label={label} aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100}><div className={`h-full rounded-full transition-all ${state.status === "error" ? "bg-red-400" : "bg-cyan"}`} style={{ width: `${percent}%` }} /></div></div>;
}

export function VoicePage({ dependencies }: { dependencies?: VoiceDependencies }) {
  const { user } = useAuth();
  const { current, kbs, available, selected, toggle } = useKnowledgeBaseSelection();
  const voice = useVoiceAssistant(selected, dependencies);
  const [typed, setTyped] = useState("");
  const pressRef = useRef<number | null>(null);

  if (kbs.isLoading) return <LoadingState />;
  if (kbs.error) return <ErrorState error={kbs.error} />;
  if (!current || !available.length) {
    const canSetup = current ? canManage(current.membership_role) : user?.role === "admin" || user?.organizations.some((organization) => organization.organization_admin);
    return <><PageHeader eyebrow="modAI Voice" title="Belgelerinizle konuşun" description="Sesli asistan, seçtiğiniz Knowledge Base'lerden yanıt verir." /><EmptyState icon={<AudioLines size={22} />} title={current ? "Bu Workspace'te henüz RAG kaynağı yok" : "Workspace gerekli"} description={canSetup ? "Bir Knowledge Base oluşturup belge yükleyerek başlayın." : "Erişim için yöneticinizle iletişime geçin."} action={canSetup && <Link className="button-primary" to="/knowledge-bases">Knowledge Base'lere git</Link>} /></>;
  }

  const listening = voice.phase === "listening";
  const busy = voice.phase === "thinking" || voice.phase === "speaking";
  const modelsReady = voice.stt.status === "ready" && (voice.tts.status === "ready" || voice.tts.status === "error");
  const modelsLoading = voice.stt.status === "loading" || voice.tts.status === "loading";
  const canTalk = selected.length > 0 && voice.phase !== "transcribing";
  const latest = [...voice.turns].reverse().find((turn) => turn.sources.length);

  const onPointerDown = (event: PointerEvent<HTMLButtonElement>) => {
    if (event.button > 0 || !canTalk) return;
    event.currentTarget.setPointerCapture?.(event.pointerId);
    if (listening) { pressRef.current = null; void voice.stopListening(); return; }
    pressRef.current = performance.now();
    void voice.startListening();
  };
  const onPointerUp = () => {
    const pressedAt = pressRef.current;
    pressRef.current = null;
    if (pressedAt !== null && performance.now() - pressedAt > HOLD_MS) void voice.stopListening();
  };
  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if ((event.key !== " " && event.key !== "Enter") || event.repeat || !canTalk) return;
    event.preventDefault();
    void (listening ? voice.stopListening() : voice.startListening());
  };
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!typed.trim() || !selected.length) return;
    voice.askText(typed);
    setTyped("");
  };

  const engineBadge = voice.tts.status === "error"
    ? voice.speechMode === "system" ? `Sistem sesi (yedek)${voice.systemVoiceName ? ` · ${voice.systemVoiceName}` : ""}` : "Sesli yanıt kullanılamıyor"
    : voice.tts.status === "ready" ? `Nöral Türkçe ses · ${voice.backend === "webgpu" ? "WebGPU" : "WASM"}` : "Ses modeli yüklenmedi";

  return <>
    <PageHeader eyebrow="modAI Voice" title="Konuşun · Dinleyin · Belgelerden yanıt alın" description="Your knowledge. Your infrastructure. Your voice assistant. Sorunuzu Türkçe sorun; yanıt yalnızca erişim yetkiniz olan belgelerden üretilir ve kaynaklarıyla gösterilir." />
    {typeof window !== "undefined" && !window.isSecureContext && <div role="note" className="mb-6 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">Mikrofon yalnızca güvenli bağlantıda çalışır. Uygulamayı HTTPS üzerinden ya da bu cihazda <code>localhost</code> ile açın; yazarak soru sormaya devam edebilirsiniz.</div>}
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
      <section className="min-w-0 space-y-6">
        <div className="voice-stage px-5 py-6 sm:px-8">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1.5 text-xs font-semibold" aria-live="polite"><span className={`h-2 w-2 rounded-full ${listening ? "bg-emerald-400 pulse-soft" : voice.phase === "error" ? "bg-red-400" : busy || voice.phase === "transcribing" ? "bg-amber-300 pulse-soft" : "bg-cyan"}`} />{phaseLabel(voice.phase)}</span>
            <div className="flex items-center gap-2">
              <span className="rounded-full bg-white/5 px-3 py-1.5 text-[11px] text-slate-300" data-testid="speech-engine">{engineBadge}</span>
              <button type="button" className="rounded-full bg-white/10 p-2 text-slate-200 hover:bg-white/20" onClick={voice.toggleVoice} aria-pressed={!voice.voiceEnabled} title={voice.voiceEnabled ? "Sesli yanıtı kapat" : "Sesli yanıtı aç"} aria-label={voice.voiceEnabled ? "Sesli yanıtı kapat" : "Sesli yanıtı aç"}>{voice.voiceEnabled ? <Volume2 size={16} /> : <VolumeX size={16} />}</button>
            </div>
          </div>
          <div className="mt-2 flex flex-col items-center text-center">
            <VoiceMascot phase={voice.phase} level={voice.level} />
            <p className="mt-1 max-w-md text-sm text-slate-300">{HINTS[voice.phase]}</p>
            {!modelsReady && <div className="mt-5 w-full max-w-md rounded-2xl border border-white/10 bg-white/5 p-4 text-left">
              {voice.stt.status === "idle" && voice.tts.status === "idle" ? <>
                <p className="text-sm font-semibold text-white">Sesli asistanı hazırlayın</p>
                <p className="mt-1 text-xs leading-5 text-slate-400">İlk kullanımda yaklaşık {FIRST_USE_MB} MB konuşma ve ses modeli bu sunucudan indirilir ve tarayıcınızda saklanır. Sonraki açılışlar önbellekten yüklenir.</p>
                <button type="button" className="button-primary mt-3 w-full bg-cyan hover:bg-cyan/90" onClick={voice.prepare}><Download size={16} /> Modelleri hazırla</button>
              </> : <div className="space-y-3" aria-busy={modelsLoading}>
                <ProgressRow label="Konuşma tanıma · Whisper tiny" state={voice.stt} />
                <ProgressRow label="Türkçe ses · EMA Lightning" state={voice.tts} />
                {voice.stt.status === "error" && <button type="button" className="button-secondary w-full" onClick={voice.prepare}>Tekrar dene</button>}
              </div>}
            </div>}
            <div className="mt-6 flex items-center gap-4">
              <button type="button" className={`voice-talk-button ${listening ? "is-recording" : ""}`} disabled={!canTalk} onPointerDown={onPointerDown} onPointerUp={onPointerUp} onPointerCancel={onPointerUp} onKeyDown={onKeyDown} aria-pressed={listening} aria-label={listening ? "Kaydı bitir" : "Konuşmaya başla"}>{listening ? <Square size={26} fill="currentColor" /> : <Mic size={32} />}</button>
              {listening && <button type="button" className="rounded-full bg-white/10 p-3 text-slate-200 hover:bg-white/20" onClick={voice.cancelListening} aria-label="Kaydı iptal et"><X size={18} /></button>}
              {busy && <button type="button" className="button-secondary border-white/20 bg-white/10 text-white hover:bg-white/20" onClick={voice.stop}><Square size={14} fill="currentColor" /> Durdur</button>}
            </div>
            {listening && <p className="mt-3 flex items-center gap-2 text-xs font-semibold text-red-300" role="status"><span className="h-2 w-2 rounded-full bg-red-500 pulse-soft" /> Mikrofon kaydediyor</p>}
            {!selected.length && <p className="mt-3 text-xs text-amber-300">Konuşmak için sağdan en az bir Knowledge Base seçin.</p>}
            {voice.error && <div role="alert" className="mt-4 flex w-full max-w-md items-start justify-between gap-3 rounded-xl bg-red-500/15 px-4 py-3 text-left text-sm text-red-200"><span>{voice.error}</span><button type="button" onClick={voice.dismissError} aria-label="Uyarıyı kapat" className="text-red-200/70 hover:text-red-100"><X size={16} /></button></div>}
            <p className="mt-5 flex items-center gap-1.5 text-[11px] text-slate-500"><Lock size={12} /> Ses kaydınız bu cihazdan çıkmaz; yalnızca tanınan metin yetkili RAG servisine gönderilir.</p>
          </div>
        </div>

        <div className="panel p-5 sm:p-6">
          <p className="eyebrow">Konuşma</p>
          <div className="mt-4 space-y-5" aria-live="polite">
            {!voice.turns.length && <p className="text-sm text-slate-500">Henüz bir soru sorulmadı. Örneğin: “Yıllık izin başvurusunu ne kadar önce yapmalıyım?”</p>}
            {voice.turns.map((turn) => <article key={turn.id} className="space-y-3" data-testid="voice-turn">
              <div className="flex justify-end"><div className="max-w-xl rounded-2xl bg-ink px-4 py-3 text-sm text-white"><p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-white/50">{turn.origin === "voice" ? "Tanınan konuşma" : "Yazılı soru"}</p>{turn.question}</div></div>
              <div className="max-w-2xl rounded-2xl bg-cloud px-4 py-3 text-sm leading-6 text-ink">
                {turn.answer || (turn.streaming ? <span className="text-slate-400">Yanıt hazırlanıyor…</span> : turn.error ? null : "Yanıt alınamadı.")}
                {turn.streaming && turn.answer && <span className="ml-1 inline-block h-4 w-1 animate-pulse bg-cyan align-middle" />}
                {turn.error && <p className="mt-2 text-sm text-red-600">{turn.error}</p>}
                {turn.stopped && <p className="mt-2 text-xs font-semibold text-slate-400">Durduruldu</p>}
                {turn.sources.length > 0 && <p className="mt-2 flex items-center gap-1 text-xs font-semibold text-cyan"><FileText size={13} /> {turn.sources.length} kaynak</p>}
                <MetricsLine metrics={turn.metrics} />
              </div>
            </article>)}
          </div>
          <form className="mt-6 flex items-end gap-3 border-t border-slate-100 pt-4" onSubmit={submit}>
            <input className="field" value={typed} onChange={(event) => setTyped(event.target.value)} placeholder={selected.length ? "Ya da sorunuzu yazın…" : "Önce bir Knowledge Base seçin"} disabled={!selected.length} aria-label="Yazılı soru" />
            <button className="button-primary h-12 shrink-0 px-4" disabled={!selected.length || !typed.trim()} title="Gönder" aria-label="Gönder"><Send size={17} /></button>
          </form>
        </div>
      </section>

      <aside className="space-y-6">
        <div className="panel p-5">
          <p className="eyebrow">Kaynaklar</p>
          <h2 className="mt-2 text-base font-bold text-ink">Yanıtın dayandığı belgeler</h2>
          <div className="mt-4 space-y-2" data-testid="voice-sources">
            {latest ? latest.sources.map((source, index) => <div key={`${source.document_id}-${source.chunk_index}-${index}`} className="flex gap-2"><span className="mt-4 text-xs font-bold text-slate-400">{index + 1}</span><div className="min-w-0 flex-1"><SourceCard source={source} /></div></div>) : <p className="text-sm text-slate-500">Yanıt geldiğinde kullanılan belge parçaları burada görünür.</p>}
          </div>
        </div>
        <div className="panel p-5">
          <p className="eyebrow">Bilgi kaynakları</p>
          <h2 className="mt-2 text-base font-bold text-ink">Knowledge Base'ler</h2>
          <div className="mt-4 space-y-2">{available.map((kb) => <label key={kb.id} className={`flex cursor-pointer items-start gap-3 rounded-xl border p-3 transition ${selected.includes(kb.id) ? "border-cyan bg-cyan/5" : "border-slate-100 hover:bg-cloud"}`}><input type="checkbox" className="mt-1 accent-cyan" checked={selected.includes(kb.id)} onChange={() => toggle(kb.id)} /><span><span className="block text-sm font-semibold text-ink">{kb.name}</span><span className="mt-1 block text-xs text-slate-500">{kb.membership_role}</span></span></label>)}</div>
          <p className="mt-4 border-t border-slate-100 pt-4 text-xs leading-5 text-slate-400">Yanıtlar yalnızca seçtiğiniz ve erişim yetkiniz olan kaynaklarda aranır.</p>
        </div>
      </aside>
    </div>
  </>;
}
