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

function ProtectedRoute() {
  const { user, loading } = useAuth();
  if (loading) return <LoadingState label="Oturum doğrulanıyor" />;
  return user ? <Outlet /> : <Navigate to="/login" replace />;
}

export default function App() {
  return <Routes><Route path="/login" element={<LoginPage />} /><Route element={<ProtectedRoute />}><Route element={<AppShell />}><Route index element={<DashboardPage />} /><Route path="knowledge-bases" element={<KnowledgeBasesPage />} /><Route path="knowledge-bases/:id" element={<KnowledgeBaseDetailPage />} /><Route path="documents" element={<DocumentsPage />} /><Route path="chat" element={<ChatPage />} /><Route path="models" element={<ModelsPage />} /><Route path="system" element={<SystemPage />} /></Route></Route><Route path="*" element={<Navigate to="/" replace />} /></Routes>;
}
