import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { CheckCircle2, KeyRound } from "lucide-react";
import { useSearchParams } from "react-router";
import { acceptInvitation } from "../api/admin";
import { getErrorMessage } from "../api/client";
import { PageHeader } from "../components/PageHeader";

export function InviteAcceptPage() {
  const [params] = useSearchParams();
  const [token, setToken] = useState(params.get("token") ?? "");
  const accept = useMutation({ mutationFn: () => acceptInvitation(token) });
  if (accept.isSuccess) return <><PageHeader eyebrow="Davet" title="Davet kabul edildi" description="Tenant erişiminiz eklendi. Sol menüden çalışma alanınızı seçebilirsiniz." /><div className="panel flex max-w-xl items-start gap-3 p-6 text-emerald-800"><CheckCircle2 className="shrink-0" size={21} /><p className="text-sm leading-6">Bu davet bir kez kullanıldı ve hesabınıza yalnızca ilgili tenant üyeliği eklendi. Platform rolünüz değişmedi.</p></div></>;
  return <><PageHeader eyebrow="Davet" title="Organization davetini kabul et" description="Davetin gönderildiği hesapla giriş yaptıktan sonra, tek kullanımlık anahtarı buraya yapıştırın." /><form className="panel max-w-xl p-6" onSubmit={(event) => { event.preventDefault(); accept.mutate(); }}><label><span className="mb-2 flex items-center gap-2 text-sm font-semibold"><KeyRound size={16} /> Davet anahtarı</span><textarea aria-label="Davet anahtarı" className="field min-h-28 font-mono text-xs" value={token} onChange={(event) => setToken(event.target.value)} placeholder="Yönetici tarafından iletilen anahtar" required /></label><button className="button-primary mt-4" disabled={accept.isPending}>{accept.isPending ? "Doğrulanıyor" : "Daveti kabul et"}</button>{accept.error && <p className="mt-3 text-sm text-red-600">{getErrorMessage(accept.error)}</p>}</form></>;
}
