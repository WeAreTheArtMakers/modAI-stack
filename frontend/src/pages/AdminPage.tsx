import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, CheckCircle2, ClipboardList, KeyRound, ShieldAlert } from "lucide-react";
import { createAdminOrganization, createAdminWorkspace, createInvitation, createMembership, getPlatformStatus, listAdminOrganizations, listAdminUsers, listAdminWorkspaces, listAuditEvents, listInvitations, listMemberships, removeMembership, revokeInvitation, updateMembership, updatePlatformRole } from "../api/admin";
import { getErrorMessage } from "../api/client";
import { PageHeader } from "../components/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "../components/State";
import { useAuth } from "../auth/AuthContext";
import type { Role } from "../types";

export type AdminSection = "users" | "organizations" | "workspaces" | "memberships" | "invitations" | "audit" | "platform";

const labels: Record<AdminSection, { eyebrow: string; title: string; description: string }> = {
  users: { eyebrow: "Platform yönetimi", title: "Kullanıcılar", description: "Platform rollerini ve güvenli kullanıcı dizinini yönetin." },
  organizations: { eyebrow: "Tenant yönetimi", title: "Organization'lar", description: "Organization kapsamlarını ve kaynak sayılarını görüntüleyin." },
  workspaces: { eyebrow: "Tenant yönetimi", title: "Workspaceler", description: "Organization içindeki çalışma alanlarını oluşturun ve düzenleyin." },
  memberships: { eyebrow: "Tenant yönetimi", title: "Üyelikler", description: "Tenant üyelik rollerini yönetin; platform rolü bu ekrandan değiştirilemez." },
  invitations: { eyebrow: "Tenant yönetimi", title: "Davetler", description: "Tek kullanımlık erişim bağlantısı oluşturun ve seçtiğiniz kanaldan güvenle iletin." },
  audit: { eyebrow: "Platform yönetimi", title: "Denetim günlüğü", description: "Yönetim işlemleri için filtrelenebilir, hassas veri içermeyen kayıtlar." },
  platform: { eyebrow: "Platform yönetimi", title: "Platform", description: "Kayıt politikası, sağlayıcı yapılandırması ve hazır olma durumu." },
};

function roleSelect(value: Role, onChange: (role: Role) => void, disabled = false) {
  return <select aria-label="Tenant rolü" className="field max-w-32 py-2" value={value} onChange={(event) => onChange(event.target.value as Role)} disabled={disabled}>{["user", "manager", "admin"].map((role) => <option value={role} key={role}>{role}</option>)}</select>;
}

function TenantPicker({ value, onChange }: { value: number | undefined; onChange: (id: number) => void }) {
  const organizations = useQuery({ queryKey: ["admin-organizations"], queryFn: listAdminOrganizations });
  useEffect(() => { if (value === undefined && organizations.data?.length) onChange(organizations.data[0].id); }, [value, organizations.data, onChange]);
  if (organizations.isLoading) return <LoadingState label="Organization'lar yükleniyor" />;
  if (organizations.error) return <ErrorState error={organizations.error} />;
  if (!organizations.data?.length) return <EmptyState icon={<Building2 size={22} />} title="Yönetilebilir organization yok" description="Bu alan yalnızca platform yöneticileri ve ilgili tenant yöneticileri içindir." />;
  return <label className="mb-6 block max-w-sm"><span className="mb-2 block text-sm font-semibold">Organization</span><select aria-label="Organization seç" className="field" value={value ?? organizations.data[0].id} onChange={(event) => onChange(Number(event.target.value))}>{organizations.data.map((organization) => <option key={organization.id} value={organization.id}>{organization.name}</option>)}</select></label>;
}

export function AdminPage({ section }: { section: AdminSection }) {
  const { user } = useAuth();
  const [organizationId, setOrganizationId] = useState<number | undefined>(user?.organizations[0]?.id);
  const platformOnly = section === "users" || section === "audit" || section === "platform";
  if (platformOnly && user?.role !== "admin") return <><PageHeader {...labels[section]} /><EmptyState icon={<ShieldAlert size={22} />} title="Platform yetkisi gerekli" description="Bu bölüm yalnızca platform yöneticileri tarafından görüntülenebilir." /></>;
  return <><PageHeader {...labels[section]} />
    {section === "users" && <UsersSection />}
    {section === "organizations" && <OrganizationsSection />}
    {section === "workspaces" && <TenantPicker value={organizationId} onChange={setOrganizationId} />}{section === "workspaces" && organizationId && <WorkspacesSection organizationId={organizationId} />}
    {section === "memberships" && <TenantPicker value={organizationId} onChange={setOrganizationId} />}{section === "memberships" && organizationId && <MembershipsSection organizationId={organizationId} />}
    {section === "invitations" && <TenantPicker value={organizationId} onChange={setOrganizationId} />}{section === "invitations" && organizationId && <InvitationsSection organizationId={organizationId} />}
    {section === "audit" && <AuditSection />}
    {section === "platform" && <PlatformSection />}
  </>;
}

function UsersSection() {
  const client = useQueryClient(); const [search, setSearch] = useState("");
  const query = useQuery({ queryKey: ["admin-users", search], queryFn: () => listAdminUsers(search) });
  const mutation = useMutation({ mutationFn: ({ id, role }: { id: number; role: "admin" | "user" }) => updatePlatformRole(id, role), onSuccess: () => void client.invalidateQueries({ queryKey: ["admin-users"] }) });
  if (query.isLoading) return <LoadingState />; if (query.error) return <ErrorState error={query.error} />;
  return <><label className="mb-5 block max-w-md"><span className="sr-only">Kullanıcı ara</span><input className="field" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="E-posta ile ara" /></label><div className="panel overflow-x-auto"><table className="w-full min-w-[620px] text-left text-sm"><thead className="bg-cloud text-xs uppercase tracking-wide text-slate-500"><tr><th className="p-4">Kullanıcı</th><th className="p-4">Platform rolü</th><th className="p-4">Oluşturulma</th></tr></thead><tbody>{query.data?.map((account) => <tr className="border-t border-slate-100" key={account.id}><td className="p-4 font-medium">{account.email}</td><td className="p-4"><select aria-label={`${account.email} platform rolü`} className="field max-w-32 py-2" value={account.role} onChange={(event) => mutation.mutate({ id: account.id, role: event.target.value as "admin" | "user" })}><option value="user">user</option><option value="admin">admin</option></select></td><td className="p-4 text-slate-500">{account.created_at ? new Date(account.created_at).toLocaleDateString("tr-TR") : "—"}</td></tr>)}</tbody></table></div>{mutation.error && <p className="mt-3 text-sm text-red-600">{getErrorMessage(mutation.error)}</p>}</>;
}

function OrganizationsSection() {
  const { user } = useAuth();
  const client = useQueryClient();
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [formOpen, setFormOpen] = useState(false);
  const query = useQuery({ queryKey: ["admin-organizations"], queryFn: listAdminOrganizations });
  const create = useMutation({ mutationFn: () => createAdminOrganization({ name, slug }), onSuccess: () => { setName(""); setSlug(""); setFormOpen(false); void client.invalidateQueries({ queryKey: ["admin-organizations"] }); } });
  if (query.isLoading) return <LoadingState />; if (query.error) return <ErrorState error={query.error} />;
  return <>
    {user?.role === "admin" && <><button className="button-primary mb-5" onClick={() => setFormOpen(!formOpen)}>Yeni organization</button>{formOpen && <form className="panel mb-5 flex flex-wrap gap-3 p-5" onSubmit={(event) => { event.preventDefault(); create.mutate(); }}><input aria-label="Organization adı" className="field max-w-sm" value={name} onChange={(event) => setName(event.target.value)} required placeholder="Şirket adı" /><input aria-label="Organization slug" className="field max-w-sm" value={slug} onChange={(event) => setSlug(event.target.value)} required pattern="[a-z0-9]+(-[a-z0-9]+)*" placeholder="sirket-slug" /><button className="button-primary" disabled={create.isPending}>Oluştur</button>{create.error && <p className="w-full text-sm text-red-700">{getErrorMessage(create.error)}</p>}</form>}</>}
    {query.data?.length ? <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{query.data.map((organization) => <article className="panel p-5" key={organization.id}><div className="flex items-center gap-3"><span className="rounded-xl bg-cyan/10 p-2.5 text-cyan"><Building2 size={19} /></span><div><h2 className="font-bold">{organization.name}</h2><p className="text-xs text-slate-500">/{organization.slug}</p></div></div><dl className="mt-5 grid grid-cols-2 gap-3 text-sm"><div><dt className="text-slate-500">Workspace</dt><dd className="mt-1 font-bold">{organization.workspace_count}</dd></div><div><dt className="text-slate-500">Üye</dt><dd className="mt-1 font-bold">{organization.member_count}</dd></div><div><dt className="text-slate-500">Knowledge Base</dt><dd className="mt-1 font-bold">{organization.knowledge_base_count}</dd></div><div><dt className="text-slate-500">Belge</dt><dd className="mt-1 font-bold">{organization.document_count}</dd></div></dl></article>)}</div> : <EmptyState icon={<Building2 size={22} />} title="Organization bulunamadı" description="Erişebildiğiniz organization'lar burada görünür." />}
  </>;
}

function WorkspacesSection({ organizationId }: { organizationId: number }) {
  const client = useQueryClient(); const [name, setName] = useState(""); const [slug, setSlug] = useState(""); const [formOpen, setFormOpen] = useState(false);
  const query = useQuery({ queryKey: ["admin-workspaces", organizationId], queryFn: () => listAdminWorkspaces(organizationId) });
  const mutation = useMutation({ mutationFn: () => createAdminWorkspace({ organization_id: organizationId, name, slug }), onSuccess: () => { setName(""); setSlug(""); setFormOpen(false); void client.invalidateQueries({ queryKey: ["admin-workspaces", organizationId] }); } });
  if (query.isLoading) return <LoadingState />; if (query.error) return <ErrorState error={query.error} />;
  return <><button className="button-primary mb-5" onClick={() => setFormOpen(!formOpen)}>Yeni Workspace</button>{formOpen && <form className="panel mb-5 grid gap-3 p-5 md:grid-cols-3" onSubmit={(event) => { event.preventDefault(); mutation.mutate(); }}><input className="field" value={name} onChange={(event) => setName(event.target.value)} placeholder="Ad" required /><input className="field" value={slug} onChange={(event) => setSlug(event.target.value)} placeholder="slug" pattern="[a-z0-9]+(-[a-z0-9]+)*" required /><button className="button-primary" disabled={mutation.isPending}>Oluştur</button>{mutation.error && <p className="text-sm text-red-600 md:col-span-3">{getErrorMessage(mutation.error)}</p>}</form>}<div className="panel overflow-x-auto"><table className="w-full min-w-[460px] text-left text-sm"><thead className="bg-cloud text-xs uppercase text-slate-500"><tr><th className="p-4">Ad</th><th className="p-4">Slug</th><th className="p-4">ID</th></tr></thead><tbody>{query.data?.map((workspace) => <tr key={workspace.id} className="border-t border-slate-100"><td className="p-4 font-medium">{workspace.name}</td><td className="p-4 text-slate-500">/{workspace.slug}</td><td className="p-4 text-slate-500">{workspace.id}</td></tr>)}</tbody></table></div></>;
}

function MembershipsSection({ organizationId }: { organizationId: number }) {
  const client = useQueryClient(); const [userEmail, setUserEmail] = useState(""); const [role, setRole] = useState<Role>("user"); const [creating, setCreating] = useState(false);
  const query = useQuery({ queryKey: ["admin-memberships", organizationId], queryFn: () => listMemberships(organizationId) });
  const create = useMutation({ mutationFn: () => createMembership({ user_email: userEmail, organization_id: organizationId, role }), onSuccess: () => { setUserEmail(""); setCreating(false); void client.invalidateQueries({ queryKey: ["admin-memberships", organizationId] }); } });
  const update = useMutation({ mutationFn: ({ id, nextRole }: { id: number; nextRole: Role }) => updateMembership(id, nextRole), onSuccess: () => void client.invalidateQueries({ queryKey: ["admin-memberships", organizationId] }) });
  const remove = useMutation({ mutationFn: removeMembership, onSuccess: () => void client.invalidateQueries({ queryKey: ["admin-memberships", organizationId] }) });
  if (query.isLoading) return <LoadingState />; if (query.error) return <ErrorState error={query.error} />;
  return <><button className="button-primary mb-5" onClick={() => setCreating(!creating)}>Kayıtlı kullanıcıyı ekle</button>{creating && <form className="panel mb-5 flex flex-wrap gap-3 p-5" onSubmit={(event) => { event.preventDefault(); create.mutate(); }}><input aria-label="Kullanıcı e-postası" type="email" className="field max-w-sm" value={userEmail} onChange={(event) => setUserEmail(event.target.value)} placeholder="person@example.com" required />{roleSelect(role, setRole)}<button className="button-primary" disabled={create.isPending}>Ekle</button>{create.error && <p className="w-full text-sm text-red-600">{getErrorMessage(create.error)}</p>}</form>}<div className="panel overflow-x-auto"><table className="w-full min-w-[650px] text-left text-sm"><thead className="bg-cloud text-xs uppercase text-slate-500"><tr><th className="p-4">Kullanıcı</th><th className="p-4">Kapsam</th><th className="p-4">Tenant rolü</th><th className="p-4" /></tr></thead><tbody>{query.data?.map((membership) => <tr className="border-t border-slate-100" key={membership.id}><td className="p-4 font-medium">{membership.user_email}</td><td className="p-4 text-slate-500">{membership.workspace_id ? `Workspace #${membership.workspace_id}` : "Organization"}</td><td className="p-4">{roleSelect(membership.role, (nextRole) => update.mutate({ id: membership.id, nextRole }))}</td><td className="p-4"><button className="button-secondary py-2 text-red-700" onClick={() => { if (window.confirm("Bu üyelik kaldırılsın mı?")) remove.mutate(membership.id); }}>Kaldır</button></td></tr>)}</tbody></table></div>{(update.error || remove.error) && <p className="mt-3 text-sm text-red-600">{getErrorMessage(update.error ?? remove.error)}</p>}</>;
}

function InvitationsSection({ organizationId }: { organizationId: number }) {
  const client = useQueryClient();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("user");
  const [workspaceId, setWorkspaceId] = useState<number | undefined>();
  const [link, setLink] = useState<string | null>(null);
  const [copyStatus, setCopyStatus] = useState("");
  const [formOpen, setFormOpen] = useState(false);
  useEffect(() => { setWorkspaceId(undefined); setLink(null); }, [organizationId]);
  const query = useQuery({ queryKey: ["admin-invitations", organizationId], queryFn: () => listInvitations(organizationId) });
  const workspaces = useQuery({ queryKey: ["admin-workspaces", organizationId], queryFn: () => listAdminWorkspaces(organizationId) });
  const create = useMutation({
    mutationFn: () => createInvitation({ email, organization_id: organizationId, workspace_id: workspaceId, role }),
    onSuccess: (result) => {
      const url = new URL("/invite/accept", window.location.origin);
      url.hash = new URLSearchParams({ token: result.delivery_token }).toString();
      setLink(url.toString()); setCopyStatus(""); setEmail(""); setFormOpen(false);
      void client.invalidateQueries({ queryKey: ["admin-invitations", organizationId] });
    },
  });
  const revoke = useMutation({ mutationFn: revokeInvitation, onSuccess: () => void client.invalidateQueries({ queryKey: ["admin-invitations", organizationId] }) });
  if (query.isLoading || workspaces.isLoading) return <LoadingState />;
  if (query.error || workspaces.error) return <ErrorState error={query.error ?? workspaces.error} />;
  return <>
    <button className="button-primary mb-5" onClick={() => setFormOpen(!formOpen)}>Yeni kullanıcı davet et</button>
    {formOpen && <form className="panel mb-5 flex flex-wrap gap-3 p-5" onSubmit={(event) => { event.preventDefault(); create.mutate(); }}>
      <input aria-label="Davet e-postası" type="email" className="field max-w-sm" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="person@example.com" required />
      {roleSelect(role, setRole)}
      <select aria-label="Davet workspace kapsamı" className="field max-w-xs" value={workspaceId ?? ""} onChange={(event) => setWorkspaceId(event.target.value ? Number(event.target.value) : undefined)}><option value="">Tüm organization</option>{workspaces.data?.map((workspace) => <option key={workspace.id} value={workspace.id}>{workspace.name}</option>)}</select>
      <button className="button-primary" disabled={create.isPending}>Davet bağlantısı oluştur</button>
      {create.error && <p className="w-full text-sm text-red-600">{getErrorMessage(create.error)}</p>}
    </form>}
    {link && <div className="mb-5 rounded-2xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-950"><div className="flex gap-3"><KeyRound className="shrink-0" size={18} /><div className="min-w-0"><p className="font-bold">Davet bağlantısını güvenle iletin</p><p className="mt-1 text-amber-800">Bağlantı yalnızca şimdi gösterilir; sunucu ham token saklamaz.</p><code className="mt-3 block break-all rounded-lg bg-white p-3 text-xs">{link}</code><button className="button-secondary mt-3" onClick={() => { if (!navigator.clipboard?.writeText) { setCopyStatus("Kopyalama kullanılamıyor; bağlantıyı elle kopyalayın."); return; } void navigator.clipboard.writeText(link).then(() => setCopyStatus("Bağlantı kopyalandı.")).catch(() => setCopyStatus("Kopyalama kullanılamıyor; bağlantıyı elle kopyalayın.")); }}>Davet bağlantısını kopyala</button>{copyStatus && <p role="status" className="mt-2">{copyStatus}</p>}</div></div></div>}
    <div className="panel overflow-x-auto"><table className="w-full min-w-[700px] text-left text-sm"><thead className="bg-cloud text-xs uppercase text-slate-500"><tr><th className="p-4">E-posta</th><th className="p-4">Rol / kapsam</th><th className="p-4">Bitiş</th><th className="p-4">Durum</th><th className="p-4" /></tr></thead><tbody>{query.data?.map((invitation) => <tr key={invitation.id} className="border-t border-slate-100"><td className="p-4 font-medium">{invitation.email}</td><td className="p-4">{invitation.role} · {invitation.workspace_id ? `Workspace #${invitation.workspace_id}` : "Organization"}</td><td className="p-4 text-slate-500">{new Date(invitation.expires_at).toLocaleString("tr-TR")}</td><td className="p-4">{invitation.accepted_at ? <span className="text-emerald-700">Kabul edildi</span> : new Date(invitation.expires_at).getTime() <= Date.now() ? <span className="text-amber-700">Süresi doldu</span> : <span className="text-amber-700">Bekliyor</span>}</td><td className="p-4">{!invitation.accepted_at && <button className="button-secondary py-2 text-red-700" onClick={() => { if (window.confirm("Davet iptal edilsin mi?")) revoke.mutate(invitation.id); }}>İptal</button>}</td></tr>)}</tbody></table></div>
    {revoke.error && <p className="mt-3 text-sm text-red-600">{getErrorMessage(revoke.error)}</p>}
  </>;
}

function AuditSection() {
  const query = useQuery({ queryKey: ["audit-events"], queryFn: listAuditEvents });
  if (query.isLoading) return <LoadingState />; if (query.error) return <ErrorState error={query.error} />;
  return <div className="panel overflow-x-auto"><table className="w-full min-w-[720px] text-left text-sm"><thead className="bg-cloud text-xs uppercase text-slate-500"><tr><th className="p-4">Zaman</th><th className="p-4">İşlem</th><th className="p-4">Kaynak</th><th className="p-4">Aktör</th><th className="p-4">Sonuç</th></tr></thead><tbody>{query.data?.map((event) => <tr key={event.id} className="border-t border-slate-100"><td className="p-4 text-slate-500">{event.timestamp ? new Date(event.timestamp).toLocaleString("tr-TR") : "—"}</td><td className="p-4 font-medium">{event.action}</td><td className="p-4 text-slate-500">{event.resource_type} {event.resource_id ? `#${event.resource_id}` : ""}</td><td className="p-4 text-slate-500">{event.actor_user_id ?? "Sistem"}</td><td className="p-4">{event.success ? <span className="text-emerald-700">Başarılı</span> : <span className="text-red-700">Başarısız</span>}</td></tr>)}</tbody></table></div>;
}

function PlatformSection() {
  const query = useQuery({ queryKey: ["platform-status"], queryFn: getPlatformStatus, refetchInterval: 30_000 });
  if (query.isLoading) return <LoadingState />; if (query.error) return <ErrorState error={query.error} />;
  const status = query.data!; const dependencies = Object.entries(status.readiness.dependencies ?? {});
  return <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3"><section className="panel p-5"><p className="eyebrow">Kayıt politikası</p><p className="mt-3 text-lg font-bold">{status.registration_enabled ? "Açık" : "Kapalı"}</p><p className="mt-2 text-sm text-slate-500">Yeni kullanıcı kaydı {status.registration_enabled ? "izinli" : "devre dışı"}.</p></section><section className="panel p-5"><p className="eyebrow">Yerel model</p><p className="mt-3 break-all font-bold">{status.configured_model}</p><p className="mt-2 text-sm text-slate-500">{status.configured_provider} · {status.embedding_model}</p></section><section className="panel p-5"><p className="eyebrow">Hazır olma</p><p className="mt-3 flex items-center gap-2 text-lg font-bold">{status.readiness.ready ? <CheckCircle2 className="text-emerald-600" size={19} /> : <ShieldAlert className="text-amber-600" size={19} />}{status.readiness.status}</p><p className="mt-2 text-sm text-slate-500">Metrikler: {status.metrics_endpoint}</p></section>{dependencies.map(([name, ready]) => <section className="panel p-5" key={name}><p className="eyebrow">{name}</p><p className={`mt-3 text-lg font-bold ${ready ? "text-emerald-700" : "text-red-700"}`}>{ready ? "Hazır" : "Ulaşılamıyor"}</p></section>)}<section className="panel p-5 md:col-span-2 xl:col-span-3"><div className="flex gap-3"><ClipboardList className="shrink-0 text-cyan" size={19} /><p className="text-sm leading-6 text-slate-600">Aktif oturumların ayrıntılı görüntülemesi bu sürümde bilinçli olarak sunulmaz; erişim token’ları, cookie’ler ve diğer oturum sırları hiçbir yönetim görünümüne taşınmaz.</p></div></section></div>;
}
