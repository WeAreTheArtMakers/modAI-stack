import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText } from "lucide-react";
import { listDocuments } from "../api/documents";
import { listKnowledgeBases } from "../api/knowledgeBases";
import { DocumentTable } from "../components/DocumentTable";
import { PageHeader } from "../components/PageHeader";
import { UploadDropzone } from "../components/UploadDropzone";
import { EmptyState, ErrorState, LoadingState } from "../components/State";
import { useWorkspace } from "../workspace/WorkspaceContext";
import { canManage } from "../lib";
import { useState } from "react";
import { Link } from "react-router";
import { useAuth } from "../auth/AuthContext";

export function DocumentsPage() {
  const { current } = useWorkspace(); const [selectedId, setSelectedId] = useState<number | undefined>(); const queryClient = useQueryClient();
  const { user } = useAuth();
  const kbs = useQuery({ queryKey: ["knowledge-bases"], queryFn: listKnowledgeBases });
  const available = kbs.data?.filter((kb) => kb.workspace_id === current?.id) ?? [];
  const effectiveId = available.some((kb) => kb.id === selectedId) ? selectedId : available[0]?.id;
  const docs = useQuery({ queryKey: ["documents", { knowledgeBaseId: effectiveId }], queryFn: () => listDocuments({ knowledgeBaseId: effectiveId }), enabled: Boolean(effectiveId) });
  if (kbs.isLoading || docs.isLoading) return <LoadingState />;
  if (kbs.error || docs.error) return <ErrorState error={kbs.error ?? docs.error} />;
  const selected = available.find((kb) => kb.id === effectiveId); const refresh = () => { void queryClient.invalidateQueries({ queryKey: ["documents"] }); };
  const canCreateKb = canManage(current?.membership_role);
  const canSetupWorkspace = user?.role === "admin" || user?.organizations.some((organization) => organization.organization_admin);
  return <><PageHeader eyebrow="Belge yönetimi" title="Kurumsal belgeler" description="İndeksleme durumunu izleyin ve Knowledge Base'lerinizin kaynaklarını yönetin." action={available.length > 0 && <select aria-label="Knowledge Base seç" className="field w-auto min-w-56" value={effectiveId ?? ""} onChange={(event) => setSelectedId(Number(event.target.value))}>{available.map((kb) => <option key={kb.id} value={kb.id}>{kb.name}</option>)}</select>} />{selected && canManage(selected.membership_role) && <div className="mb-8"><UploadDropzone knowledgeBaseId={selected.id} onUploaded={refresh} /></div>}{!selected ? <EmptyState icon={<FileText size={22} />} title={current ? "Belge yüklemek için Knowledge Base gerekli" : "Workspace gerekli"} description={current ? canCreateKb ? "Önce bir Knowledge Base oluşturun." : "Bu Workspace'te Knowledge Base yok. Oluşturmak için manager veya admin yetkisi gerekir." : canSetupWorkspace ? "Önce Organization erişiminizi ve Workspace'i hazırlayın." : "Erişim için Organization yöneticinizle iletişime geçin."} action={canCreateKb ? <Link className="button-primary" to="/knowledge-bases">Knowledge Base oluştur</Link> : !current && canSetupWorkspace ? <Link className="button-primary" to="/admin/workspaces">Workspace oluştur</Link> : null} /> : docs.data?.items.length ? <DocumentTable documents={docs.data.items} canManage={canManage(selected?.membership_role)} onChanged={refresh} /> : <EmptyState icon={<FileText size={22} />} title="Henüz belge yok" description={canManage(selected.membership_role) ? `${selected.name} içine belge yükleyerek indekslemeyi başlatın.` : "Bu Knowledge Base'e henüz belge eklenmemiş. Yükleme için manager veya admin yetkisi gerekir."} />}</>;
}
