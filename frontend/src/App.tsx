import { Navigate, Outlet, Route, Routes } from "react-router";
import { useAuth } from "./auth/AuthContext";
import AppShell from "./components/AppShell";
import { LoadingState } from "./components/State";
import { LoginPage } from "./pages/LoginPage";
import { DashboardPage } from "./pages/DashboardPage";
import { KnowledgeBasesPage } from "./pages/KnowledgeBasesPage";
import { KnowledgeBaseDetailPage } from "./pages/KnowledgeBaseDetailPage";
import { DocumentsPage } from "./pages/DocumentsPage";
import { ChatPage } from "./pages/ChatPage";
import { SystemPage } from "./pages/SystemPage";
import { ModelsPage } from "./pages/ModelsPage";
import { AdminPage } from "./pages/AdminPage";

function ProtectedRoute() {
  const { user, loading } = useAuth();
  if (loading) return <LoadingState label="Oturum doğrulanıyor" />;
  return user ? <Outlet /> : <Navigate to="/login" replace />;
}

export default function App() {
  return <Routes><Route path="/login" element={<LoginPage />} /><Route element={<ProtectedRoute />}><Route element={<AppShell />}><Route index element={<DashboardPage />} /><Route path="knowledge-bases" element={<KnowledgeBasesPage />} /><Route path="knowledge-bases/:id" element={<KnowledgeBaseDetailPage />} /><Route path="documents" element={<DocumentsPage />} /><Route path="chat" element={<ChatPage />} /><Route path="models" element={<ModelsPage />} /><Route path="system" element={<SystemPage />} /><Route path="admin/users" element={<AdminPage section="users" />} /><Route path="admin/organizations" element={<AdminPage section="organizations" />} /><Route path="admin/workspaces" element={<AdminPage section="workspaces" />} /><Route path="admin/memberships" element={<AdminPage section="memberships" />} /><Route path="admin/invitations" element={<AdminPage section="invitations" />} /><Route path="admin/audit" element={<AdminPage section="audit" />} /><Route path="admin/platform" element={<AdminPage section="platform" />} /></Route></Route><Route path="*" element={<Navigate to="/" replace />} /></Routes>;
}
