import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUpRight, BookOpen, Plus, ShieldCheck } from "lucide-react";
import { Link } from "react-router";
import { createKnowledgeBase, listKnowledgeBases } from "../api/knowledgeBases";
import { getErrorMessage } from "../api/client";
import { PageHeader } from "../components/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "../components/State";
import { useWorkspace } from "../workspace/WorkspaceContext";
import { canManage } from "../lib";

export function KnowledgeBasesPage() {
  const { current } = useWorkspace();
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["knowledge-bases"], queryFn: listKnowledgeBases });
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState(""); const [description, setDescription] = useState(""); const [error, setError] = useState<string | null>(null);
  const mutation = useMutation({ mutationFn: () => createKnowledgeBase(current!.id, { name, description }), onSuccess: async () => { setCreating(false); setName(""); setDescription(""); await queryClient.invalidateQueries({ queryKey: ["knowledge-bases"] }); }, onError: (reason) => setError(getErrorMessage(reason)) });
  if (query.isLoading) return <LoadingState />;
  if (query.error) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  const items = query.data?.filter((kb) => kb.workspace_id === current?.id) ?? [];
  const canCreate = canManage(current?.membership_role);
  return <><PageHeader eyebrow="Bilgi tabanları" title="Kurumsal hafızanız" description="Belgelerinizi çalışma alanınızın Knowledge Base'lerinde organize edin." action={canCreate && <button className="button-primary" onClick={() => { setCreating(!creating); setError(null); }}><Plus size={17} /> Yeni Knowledge Base</button>} />{creating && <form className="panel mb-6 grid gap-4 p-6 md:grid-cols-[1fr_1fr_auto] md:items-end" onSubmit={(event) => { event.preventDefault(); setError(null); mutation.mutate(); }}><label><span className="mb-2 block text-sm font-semibold">Ad</span><input className="field" value={name} onChange={(event) => setName(event.target.value)} placeholder="Engineering" required /></label><label><span className="mb-2 block text-sm font-semibold">Açıklama</span><input className="field" value={description} onChange={(event) => setDescription(event.target.value)} placeholder="Takım dokümantasyonu" /></label><button className="button-primary" disabled={mutation.isPending}>{mutation.isPending ? "Oluşturuluyor" : "Oluştur"}</button>{error && <p className="text-sm text-red-600 md:col-span-3">{error}</p>}</form>}{items.length ? <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">{items.map((kb) => <Link key={kb.id} to={`/knowledge-bases/${kb.id}`} className="panel group p-6 transition hover:-translate-y-0.5 hover:border-cyan/40"><div className="flex items-start justify-between"><span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-cyan/10 text-cyan"><BookOpen size={21} /></span><ArrowUpRight className="text-slate-300 transition group-hover:text-cyan" size={19} /></div><h2 className="mt-6 text-lg font-bold text-ink">{kb.name}</h2><p className="mt-2 min-h-10 text-sm leading-5 text-slate-500">{kb.description || "Bu bilgi tabanı için henüz açıklama eklenmedi."}</p><div className="mt-6 flex items-center justify-between border-t border-slate-100 pt-4 text-xs"><span className="text-slate-400">/{kb.slug}</span><span className="flex items-center gap-1.5 font-semibold text-slate-600"><ShieldCheck size={14} className="text-cyan" />{kb.membership_role}</span></div></Link>)}</div> : <EmptyState icon={<BookOpen size={22} />} title="Henüz Knowledge Base yok" description="Belgelerinizi düzenlemek ve RAG için kullanmak üzere ilk bilgi tabanınızı oluşturun." action={canCreate && <button className="button-primary" onClick={() => setCreating(true)}><Plus size={16} /> Oluştur</button>} />}</>;
}
