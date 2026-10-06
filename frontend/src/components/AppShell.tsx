import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { NavLink, Outlet, useNavigate } from "react-router";
import { Activity, BookOpen, ChevronDown, CircleHelp, Cpu, FileText, LayoutDashboard, LogOut, MessageSquare, Menu, Server, ShieldCheck, Users, X } from "lucide-react";
import { connectIndexing } from "../api/websocket";
import { Logo } from "./Logo";
import { MascotOverlay } from "./mascot/MascotOverlay";
import { useAuth } from "../auth/AuthContext";
import { WorkspaceProvider, useWorkspace } from "../workspace/WorkspaceContext";
import { ThemeToggle } from "../theme/ThemeToggle";

const navItems = [
  { to: "/", label: "Genel Bakış", icon: LayoutDashboard },
  { to: "/knowledge-bases", label: "Knowledge Base'ler", icon: BookOpen },
  { to: "/documents", label: "Belgeler", icon: FileText },
  { to: "/chat", label: "RAG Chat", icon: MessageSquare },
  { to: "/models", label: "Modeller", icon: Cpu },
  { to: "/system", label: "Sistem", icon: Server },
  { to: "/help", label: "Kullanım Rehberi", icon: CircleHelp },
];

const adminNavItems = [
  { to: "/admin/users", label: "Kullanıcılar", icon: Users, platformOnly: true },
  { to: "/admin/organizations", label: "Organization'lar", icon: ShieldCheck },
  { to: "/admin/workspaces", label: "Workspaceler", icon: ShieldCheck },
  { to: "/admin/memberships", label: "Üyelikler", icon: Users },
  { to: "/admin/invitations", label: "Davetler", icon: ShieldCheck },
  { to: "/admin/audit", label: "Denetim günlüğü", icon: ShieldCheck, platformOnly: true },
  { to: "/admin/platform", label: "Platform", icon: Server, platformOnly: true },
];

function ShellContent() {
  const { user, logout } = useAuth();
  const { current, workspaces, setCurrentId } = useWorkspace();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [socketState, setSocketState] = useState<"connecting" | "open" | "closed">("closed");
  const canAdministerTenant = user?.role === "admin" || user?.organizations.some((organization) => organization.organization_admin);
  const visibleAdminItems = adminNavItems.filter((item) => !item.platformOnly || user?.role === "admin");

  useEffect(() => {
    if (!current) return;
    return connectIndexing(current.id, () => {
      void queryClient.invalidateQueries({ queryKey: ["documents"] });
    }, setSocketState);
  }, [current, queryClient]);

  const sidebar = <aside className={`${mobileOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"} fixed inset-y-0 left-0 z-40 flex w-72 flex-col border-r border-slate-200 bg-white px-5 py-6 transition-transform lg:static lg:shrink-0`}>
    <div className="flex items-center justify-between"><Logo /><button className="rounded-lg p-2 text-slate-500 lg:hidden" onClick={() => setMobileOpen(false)} aria-label="Menüyü kapat"><X size={19} /></button></div>
    <div className="mt-9"><p className="eyebrow px-3">Çalışma alanı</p>{workspaces.length ? <><label className="relative mt-2 block"><select aria-label="Workspace seç" className="field appearance-none pr-9" value={current?.id ?? workspaces[0].id} onChange={(event) => setCurrentId(Number(event.target.value))}>{workspaces.map((workspace) => <option key={workspace.id} value={workspace.id}>{workspace.name}</option>)}</select><ChevronDown className="pointer-events-none absolute right-3 top-3.5 text-slate-400" size={16} /></label>{current && <p className="mt-2 px-1 text-xs text-slate-500">{user?.organizations.find((org) => org.id === current.organization_id)?.name ?? "Organization"} · {current.membership_role}</p>}</> : <div className="mt-2 rounded-xl bg-cloud p-3 text-xs leading-5 text-slate-600"><p className="font-semibold text-ink">Henüz erişilebilir Workspace yok.</p>{user?.role === "admin" ? <p className="mt-1">Önce Organization üyeliğinizi ve Workspace'i hazırlayın. <NavLink to="/admin/memberships" className="font-semibold text-cyan underline">Üyeliklere git</NavLink> · <NavLink to="/admin/workspaces" className="font-semibold text-cyan underline">Workspace oluştur</NavLink></p> : canAdministerTenant ? <p className="mt-1">Organization yöneticisi olarak <NavLink to="/admin/workspaces" className="font-semibold text-cyan underline">Workspace oluşturun</NavLink>.</p> : <p className="mt-1">Erişim için Organization yöneticinizle iletişime geçin.</p>}</div>}</div>
    <nav className="mt-9 space-y-1" aria-label="Ana menü">{navItems.map(({ to, label, icon: Icon }) => <NavLink key={to} to={to} onClick={() => setMobileOpen(false)} className={({ isActive }) => `flex items-center gap-3 rounded-xl px-3 py-3 text-sm font-medium transition ${isActive ? "bg-ink text-white shadow-sm" : "text-slate-600 hover:bg-cloud hover:text-ink"}`}><Icon size={18} strokeWidth={1.8} />{label}</NavLink>)}{canAdministerTenant && <><p className="eyebrow px-3 pt-6">Yönetim</p>{visibleAdminItems.map(({ to, label, icon: Icon }) => <NavLink key={to} to={to} onClick={() => setMobileOpen(false)} className={({ isActive }) => `flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition ${isActive ? "bg-ink text-white shadow-sm" : "text-slate-600 hover:bg-cloud hover:text-ink"}`}><Icon size={17} strokeWidth={1.8} />{label}</NavLink>)}</>}</nav>
    <div className="mt-auto border-t border-slate-100 pt-5"><div className="flex items-center gap-3 px-2"><div className="flex h-9 w-9 items-center justify-center rounded-full bg-cyan/10 text-sm font-bold text-cyan">{user?.email.slice(0, 1).toUpperCase()}</div><div className="min-w-0 flex-1"><p className="truncate text-sm font-semibold text-ink">{user?.email}</p><p className="text-xs text-slate-500">{current?.membership_role ?? user?.role}</p></div><button className="rounded-lg p-2 text-slate-400 hover:bg-cloud hover:text-ink" title="Çıkış yap" onClick={() => { logout(); navigate("/login"); }}><LogOut size={17} /></button></div></div>
  </aside>;

  return <div className="flex min-h-screen bg-cloud">{sidebar}{mobileOpen && <button className="fixed inset-0 z-30 bg-ink/20 lg:hidden" onClick={() => setMobileOpen(false)} aria-label="Menüyü kapat" />}
    <main className="min-w-0 flex-1"><header className="flex h-20 items-center justify-between border-b border-slate-200/80 bg-white/80 px-5 backdrop-blur lg:px-10"><button className="rounded-xl p-2 text-slate-500 hover:bg-cloud lg:hidden" onClick={() => setMobileOpen(true)} aria-label="Menüyü aç"><Menu size={21} /></button><div className="hidden items-center gap-2 text-sm text-slate-500 lg:flex"><Activity size={16} className="text-cyan" /> Local-first enterprise AI</div><div className="ml-auto flex items-center gap-3"><ThemeToggle /><div className="flex items-center gap-2 text-xs text-slate-500"><span className={`h-2 w-2 rounded-full ${socketState === "open" ? "bg-emerald-500" : socketState === "connecting" ? "bg-amber-400 pulse-soft" : "bg-slate-300"}`} /> {socketState === "open" ? "İndeks akışı aktif" : socketState === "connecting" ? "Bağlanıyor" : "İndeks akışı beklemede"}</div></div></header><div className="mx-auto max-w-[1500px] px-5 py-8 lg:px-10"><Outlet context={{ currentWorkspace: current }} /></div></main>
    <MascotOverlay workspaceId={current?.id ?? null} />
  </div>;
}

export default function AppShell() { return <WorkspaceProvider><ShellContent /></WorkspaceProvider>; }
