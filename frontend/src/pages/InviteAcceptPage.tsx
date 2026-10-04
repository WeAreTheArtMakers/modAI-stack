import { useState, type FormEvent } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, Navigate, useSearchParams } from "react-router";
import { CheckCircle2 } from "lucide-react";
import { acceptInvitation } from "../api/admin";
import { inspectInvitation, setupInvitedAccount } from "../api/auth";
import { getErrorMessage } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { PageHeader } from "../components/PageHeader";

export function InviteAcceptPage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const { user, logout } = useAuth();
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const info = useQuery({ queryKey: ["invitation-info", token], queryFn: () => inspectInvitation(token), enabled: token.length >= 32, retry: false });
  const setup = useMutation({ mutationFn: () => setupInvitedAccount(token, password) });
  const accept = useMutation({ mutationFn: () => acceptInvitation(token) });
  const loginReturnTo = `/invite/accept?token=${encodeURIComponent(token)}`;

  function submitSetup(event: FormEvent) {
    event.preventDefault();
    if (password !== confirmation) { setFormError("Şifreler eşleşmiyor."); return; }
    setFormError(null);
    setup.mutate();
  }

  if (setup.isSuccess) return <Navigate to="/login" replace state={{ notice: "Hesabınız oluşturuldu ve şirkete katıldınız. Şimdi giriş yapın." }} />;
  return <main className="min-h-screen bg-cloud p-6 sm:p-10"><div className="mx-auto max-w-xl">
    <PageHeader eyebrow="Kurumsal davet" title="Şirketinize katılın" description="Davetinizin kapsamını doğrulayın ve hesabınızla katılın." />
    {!token || token.length < 32 ? <p role="alert" className="panel p-6">Geçerli bir davet bağlantısı gerekli.</p> : info.isLoading ? <p className="panel p-6">Davet doğrulanıyor...</p> : info.error ? <p role="alert" className="panel p-6 text-red-700">Davet geçersiz veya iptal edilmiş olabilir.</p> : info.data && <div className="panel space-y-5 p-6">
      <div className="text-sm leading-7"><p><strong>Organization:</strong> {info.data.organization_name}</p>{info.data.workspace_name && <p><strong>Workspace:</strong> {info.data.workspace_name}</p>}<p><strong>Rol:</strong> {info.data.role}</p><p><strong>E-posta:</strong> {info.data.email}</p><p><strong>Son geçerlilik:</strong> {new Date(info.data.expires_at).toLocaleString("tr-TR")}</p></div>
      {info.data.status === "expired" ? <p role="alert" className="text-amber-700">Bu davetin süresi dolmuş. Yöneticinizden yeni bağlantı isteyin.</p> : info.data.status === "accepted" ? <p role="status" className="text-emerald-700">Bu davet daha önce kabul edilmiş.</p> : info.data.account_exists ? <>
        <p>Bu e-posta için bir hesap zaten var. Şifrenizi değiştirmeden, o hesapla giriş yapıp daveti kabul edin.</p>
        {user?.email.toLowerCase() === info.data.email.toLowerCase() ? <>
          <button className="button-primary" onClick={() => accept.mutate()} disabled={accept.isPending || accept.isSuccess}>Daveti kabul et</button>
          {accept.isSuccess && <p role="status" className="flex items-center gap-2 text-emerald-700"><CheckCircle2 size={18} /> Davet kabul edildi. Yeni üyeliğinizi görmek için sayfayı yenileyin.</p>}
          {accept.error && <p role="alert" className="text-red-700">{getErrorMessage(accept.error)}</p>}
        </> : user ? <button className="button-secondary" onClick={logout}>Başka hesapla devam etmek için çıkış yap</button> : <Link className="button-primary inline-flex" to="/login" state={{ returnTo: loginReturnTo }}>Giriş yap</Link>}
      </> : user ? <div className="space-y-3"><p role="alert">Yeni hesabı oluşturmadan önce mevcut oturumdan çıkın.</p><button className="button-secondary" onClick={logout}>Mevcut hesaptan çık</button></div> : <form className="space-y-4" onSubmit={submitSetup}>
        <label className="block"><span className="mb-2 block text-sm font-semibold">Şifre</span><input className="field" aria-label="Yeni şifre" type="password" minLength={8} maxLength={128} value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="new-password" required /></label>
        <label className="block"><span className="mb-2 block text-sm font-semibold">Şifreyi doğrula</span><input className="field" aria-label="Şifreyi doğrula" type="password" minLength={8} maxLength={128} value={confirmation} onChange={(event) => setConfirmation(event.target.value)} autoComplete="new-password" required /></label>
        <button className="button-primary" disabled={setup.isPending}>Hesap oluştur ve katıl</button>
        {(formError || setup.error) && <p role="alert" className="text-sm text-red-700">{formError ?? getErrorMessage(setup.error)}</p>}
      </form>}
    </div>}
  </div></main>;
}
