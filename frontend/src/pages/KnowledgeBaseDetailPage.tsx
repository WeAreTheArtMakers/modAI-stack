import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, BookOpen, MessageSquare } from "lucide-react";
import { Link, useParams } from "react-router";
import { listDocuments } from "../api/documents";
import { listKnowledgeBases } from "../api/knowledgeBases";
import { DocumentTable } from "../components/DocumentTable";
import { PageHeader } from "../components/PageHeader";
import { UploadDropzone } from "../components/UploadDropzone";
import { EmptyState, ErrorState, LoadingState } from "../components/State";
import { useWorkspace } from "../workspace/WorkspaceContext";
import { canManage } from "../lib";

export function KnowledgeBaseDetailPage() {
  const { id } = useParams(); const knowledgeBaseId = Number(id); const { current } = useWorkspace(); const queryClient = useQueryClient();
  const kbs = useQuery({ queryKey: ["knowledge-bases"], queryFn: listKnowledgeBases });
  const docs = useQuery({ queryKey: ["documents", { knowledgeBaseId }], queryFn: () => listDocuments({ knowledgeBaseId }), enabled: Number.isSafeInteger(knowledgeBaseId) && knowledgeBaseId > 0 && Boolean(kbs.data?.some((item) => item.id === knowledgeBaseId && item.workspace_id === current?.id)) });
  if (kbs.isLoading || docs.isLoading) return <LoadingState />;
  if (kbs.error || docs.error) return <ErrorState error={kbs.error ?? docs.error} />;
  const kb = kbs.data?.find((item) => item.id === knowledgeBaseId && item.workspace_id === current?.id);
  if (!kb) return <EmptyState icon={<BookOpen size={22} />} title="Knowledge Base bulunamadı" description="Bu kayıt mevcut değil veya mevcut workspace kapsamında değil." action={<Link to="/knowledge-bases" className="button-secondary"><ArrowLeft size={16} /> Listeye dön</Link>} />;
  const refresh = () => { void queryClient.invalidateQueries({ queryKey: ["documents", { knowledgeBaseId }] }); void queryClient.invalidateQueries({ queryKey: ["documents"] }); };
  return <><Link to="/knowledge-bases" className="mb-6 inline-flex items-center gap-2 text-sm font-semibold text-slate-500 hover:text-ink"><ArrowLeft size={16} /> Knowledge Base'ler</Link><PageHeader eyebrow="Knowledge Base" title={kb.name} description={kb.description || "Bu workspace içindeki kurumsal belgeler."} action={<Link to={`/chat?kb=${kb.id}`} className="button-secondary"><MessageSquare size={16} /> Bu kaynaklarla chat</Link>} /><div className="mb-6 grid gap-4 sm:grid-cols-3"><div className="panel p-5"><p className="eyebrow">Workspace</p><p className="mt-2 font-semibold text-ink">{current?.name}</p></div><div className="panel p-5"><p className="eyebrow">Yetki</p><p className="mt-2 font-semibold capitalize text-ink">{kb.membership_role}</p></div><div className="panel p-5"><p className="eyebrow">Belge</p><p className="mt-2 font-semibold text-ink">{docs.data?.total ?? 0} kayıt</p></div></div>{canManage(kb.membership_role) && <div className="mb-8"><UploadDropzone knowledgeBaseId={kb.id} onUploaded={refresh} /></div>}<div className="mb-4 flex items-center justify-between"><h2 className="text-lg font-bold text-ink">Belgeler</h2><span className="text-sm text-slate-500">{docs.data?.total ?? 0} kayıt</span></div>{docs.data?.items.length ? <DocumentTable documents={docs.data.items} canManage={canManage(kb.membership_role)} onChanged={refresh} /> : <EmptyState icon={<BookOpen size={22} />} title="Bu Knowledge Base boş" description={canManage(kb.membership_role) ? "İlk PDF, DOCX, TXT veya Markdown belgenizi yükleyin." : "Henüz belge yok. Yükleme için manager veya admin yetkisi gerekir."} />}</>;
}
