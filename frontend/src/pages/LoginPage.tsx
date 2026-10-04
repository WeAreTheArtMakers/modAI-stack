import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router";
import { ArrowRight, LockKeyhole } from "lucide-react";
import { Logo } from "../components/Logo";
import { useAuth } from "../auth/AuthContext";
import { pendingInvitation } from "../invitations/transport";

export function LoginPage() {
  const { user, loading, login, error } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const state = location.state as { notice?: unknown } | null;
  const returnTo = pendingInvitation() ? "/invite/accept" : "/";
  const notice = typeof state?.notice === "string" ? state.notice : null;
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  if (!loading && user) return <Navigate to={returnTo} replace />;

  async function submit(event: FormEvent) {
    event.preventDefault(); setSubmitting(true);
    try { await login(email, password); navigate(returnTo, { replace: true }); }
    catch { /* AuthContext exposes the message. */ }
    finally { setSubmitting(false); }
  }

  return <div className="grid min-h-screen bg-cloud lg:grid-cols-[1.1fr_.9fr]">
    <div className="relative hidden overflow-hidden bg-ink p-12 text-white lg:flex lg:flex-col lg:justify-between">
      <div className="absolute -right-32 -top-32 h-96 w-96 rounded-full border border-white/10" />
      <div className="absolute -bottom-44 -left-20 h-[28rem] w-[28rem] rounded-full border border-coral/30" />
      <Logo />
      <div className="relative max-w-lg pb-12"><p className="eyebrow text-cyan">Yerel · güvenli · kurumsal</p><h1 className="mt-5 text-5xl font-bold leading-[1.08] tracking-tight">Şirket bilginiz,<br /><span className="text-cyan">sizin altyapınızda.</span></h1><p className="mt-6 max-w-md text-base leading-7 text-slate-300">modAI Console ile belgelerinizi yönetin, yerel modellerle arayın ve cevabın kaynağını her zaman görün.</p><div className="mt-10 flex items-center gap-3 text-sm text-slate-400"><span className="h-2 w-2 rounded-full bg-emerald-400" /> Local-first RAG platform</div></div>
      <p className="text-xs text-slate-500">We Are The Art Makers · modAI-stack</p>
    </div>
    <div className="flex items-center justify-center p-6 sm:p-12"><div className="w-full max-w-md">
      <div className="mb-10 lg:hidden"><Logo /></div><p className="eyebrow">Console erişimi</p><h2 className="mt-3 text-3xl font-bold tracking-tight text-ink">Tekrar hoş geldiniz</h2><p className="mt-3 text-sm leading-6 text-slate-500">Çalışma alanınıza devam etmek için giriş yapın.</p>
      {notice && <p role="status" className="mt-5 rounded-xl border border-emerald-100 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">{notice}</p>}
      <form className="mt-8 space-y-5" onSubmit={submit}>
        <label className="block"><span className="mb-2 block text-sm font-semibold text-ink">E-posta</span><input className="field" type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="siz@şirket.com" required /></label>
        <label className="block"><span className="mb-2 block text-sm font-semibold text-ink">Şifre</span><div className="relative"><LockKeyhole className="absolute left-3.5 top-3.5 text-slate-400" size={17} /><input className="field pl-10" type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="••••••••" required /></div></label>
        {error && <div role="alert" className="rounded-xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}
        <button className="button-primary w-full py-3" disabled={submitting}>{submitting ? "Giriş yapılıyor..." : <>Console'a gir <ArrowRight size={17} /></>}</button>
      </form>
      <p className="mt-8 text-center text-xs leading-5 text-slate-400">Erişim ve yetkileriniz kuruluş yöneticiniz tarafından yönetilir.</p>
    </div></div>
  </div>;
}
