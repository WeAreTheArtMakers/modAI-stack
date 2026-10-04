import { Link } from "react-router";
import { useAuth } from "../auth/AuthContext";
import { PageHeader } from "../components/PageHeader";

export function HelpPage() {
  const { user } = useAuth();
  const canAdminister = user?.role === "admin" || user?.organizations.some((organization) => organization.organization_admin);
  return <>
    <PageHeader eyebrow="Kullanım Rehberi" title="modAI-stack'i kullanın" description="Belge yükleme, kaynak seçimi ve güvenli erişim için kısa yol haritanız." />
    <div className="grid gap-5 lg:grid-cols-2">
      <section className="panel p-6"><h2 className="text-lg font-bold">Hızlı başlangıç</h2><p className="mt-3 text-sm leading-6 text-slate-600">Workspace seçin, yetkili olduğunuz Knowledge Base'i açın ve belgelerin hazır olmasını bekleyin. Sonra RAG Chat'te kaynağı seçip soru sorun.</p><Link to="/knowledge-bases" className="mt-4 inline-block text-sm font-semibold text-cyan">Knowledge Base'lere git →</Link></section>
      <section className="panel p-6"><h2 className="text-lg font-bold">Bilgi hiyerarşisi</h2><p className="mt-3 text-sm leading-6 text-slate-600">Organization şirket sınırıdır; Workspace ekip veya çalışma alanıdır. Knowledge Base belgeleri gruplar. Yalnızca üyeliğinizin izin verdiği kapsamı görürsünüz.</p></section>
      <section className="panel p-6"><h2 className="text-lg font-bold">Belge yükleme</h2><p className="mt-3 text-sm leading-6 text-slate-600">Manager veya admin rolüyle bir Knowledge Base seçip PDF, DOCX, TXT veya Markdown yükleyin. Durum sırayla kuyrukta, işleniyor, hazır ya da hatalı olabilir. Yalnızca hazır belgeler sorgulanabilir.</p><Link to="/documents" className="mt-4 inline-block text-sm font-semibold text-cyan">Belgelere git →</Link></section>
      <section className="panel p-6"><h2 className="text-lg font-bold">RAG Chat ve kaynaklar</h2><p className="mt-3 text-sm leading-6 text-slate-600">Aynı Workspace içindeki yetkili kaynakları seçin. Yanıtın altındaki kaynak kartları belgeyi, parça numarasını ve ilgili alıntıyı gösterir. Yanıtı önemli kararlar öncesinde kaynakla karşılaştırın.</p><Link to="/chat" className="mt-4 inline-block text-sm font-semibold text-cyan">Chat'i aç →</Link></section>
      <section className="panel p-6"><h2 className="text-lg font-bold">Roller ve davetler</h2><p className="mt-3 text-sm leading-6 text-slate-600">User okur ve soru sorar; manager belge ve Knowledge Base yönetir; Organization admin tenant üyeliklerini ve alanlarını yönetir. Platform admin rolü tek başına tenant belge erişimi sağlamaz. Yeni çalışanlar tek kullanımlık davet bağlantısıyla katılır.</p></section>
      <section className="panel p-6"><h2 className="text-lg font-bold">Sorun giderme</h2><p className="mt-3 text-sm leading-6 text-slate-600">Workspace boşsa yöneticinizden üyelik isteyin. KB oluştur düğmesi yoksa manager/admin yetkisi gerekir. Belge hazır değilse indeks durumunu Belgeler'de izleyin. Servis sorunu için Sistem ekranını kontrol edin.</p><Link to="/system" className="mt-4 inline-block text-sm font-semibold text-cyan">Sistem durumunu gör →</Link></section>
      {canAdminister && <section className="panel p-6 lg:col-span-2"><h2 className="text-lg font-bold">Yöneticiler için ilk kurulum</h2><p className="mt-3 text-sm leading-6 text-slate-600">Organization oluşturun. Platform yöneticisiyseniz Üyelikler'de kendinize açıkça Organization Admin erişimi verin; ardından Workspace ve Knowledge Base oluşturun. Mevcut hesapları Üyelikler'den ekleyin, yeni çalışanlar için Davetler'i kullanın.</p><div className="mt-4 flex flex-wrap gap-4 text-sm font-semibold text-cyan"><Link to="/admin/memberships">Üyelikler →</Link><Link to="/admin/workspaces">Workspaceler →</Link><Link to="/admin/invitations">Davetler →</Link></div></section>}
    </div>
  </>;
}
