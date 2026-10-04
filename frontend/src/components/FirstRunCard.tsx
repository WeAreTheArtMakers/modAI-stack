import { useQuery } from "@tanstack/react-query";
import { ArrowRight, CheckCircle2, Circle } from "lucide-react";
import { Link } from "react-router";
import { listAdminOrganizations } from "../api/admin";
import { useAuth } from "../auth/AuthContext";
import { canManage } from "../lib";
import { useWorkspace } from "../workspace/WorkspaceContext";

export function FirstRunCard({ kbCount, readyDocumentCount }: { kbCount: number; readyDocumentCount: number }) {
  const { user } = useAuth();
  const { current } = useWorkspace();
  const organizations = useQuery({ queryKey: ["admin-organizations"], queryFn: listAdminOrganizations, enabled: user?.role === "admin" });
  if (!user || (current && kbCount > 0 && readyDocumentCount > 0)) return null;
  const isPlatformAdmin = user.role === "admin";
  const organizationExists = isPlatformAdmin ? Boolean(organizations.data?.length) : user.organizations.length > 0;
  const tenantAdmin = user.organizations.some((organization) => organization.organization_admin);
  const canSetupKb = canManage(current?.membership_role);
  const steps = [
    { label: "Organization", done: organizationExists, to: isPlatformAdmin ? "/admin/organizations" : undefined },
    { label: isPlatformAdmin ? "Organization Admin erişimi" : "Organization üyeliği", done: isPlatformAdmin ? tenantAdmin : organizationExists, to: isPlatformAdmin ? "/admin/memberships" : undefined },
    { label: "Workspace", done: Boolean(current), to: isPlatformAdmin || tenantAdmin ? "/admin/workspaces" : undefined },
    { label: "Knowledge Base", done: kbCount > 0, to: canSetupKb ? "/knowledge-bases" : undefined },
    { label: "İlk belge", done: readyDocumentCount > 0, to: kbCount > 0 && canSetupKb ? "/documents" : undefined },
    { label: "RAG Chat", done: false, to: readyDocumentCount > 0 ? "/chat" : undefined },
  ];
  return <section className="panel mb-7 border-cyan/20 p-5 sm:p-6" aria-labelledby="first-run-title">
    <p className="eyebrow">Hızlı başlangıç</p>
    <h2 id="first-run-title" className="mt-2 text-xl font-bold text-ink">Kurumsal alanınızı hazırlayın</h2>
    <p className="mt-2 text-sm text-slate-600">{isPlatformAdmin ? "Platform yöneticiliği tenant belgelerine otomatik erişim vermez. Seçili Organization için üyeliğinizi açıkça tanımlayın." : "Erişiminiz eksikse Organization yöneticinizden yardım isteyin; belgeler hazır olduğunda Chat'i kullanabilirsiniz."}</p>
    <ol className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{steps.map((step, index) => <li key={step.label} className="flex items-center gap-3 rounded-xl bg-cloud p-3 text-sm"><span className="text-cyan">{step.done ? <CheckCircle2 size={19} /> : <Circle size={19} />}</span><span className="min-w-0 flex-1"><span className="mr-2 text-slate-400">{index + 1}.</span>{step.label}</span>{step.to && !step.done && <Link to={step.to} className="text-cyan" aria-label={`${step.label} adımına git`}><ArrowRight size={17} /></Link>}</li>)}</ol>
  </section>;
}
