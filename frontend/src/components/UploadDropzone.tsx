import { useRef, useState } from "react";
import { FileUp, LoaderCircle } from "lucide-react";
import { uploadDocuments } from "../api/documents";
import { getErrorMessage } from "../api/client";

export function UploadDropzone({ knowledgeBaseId, onUploaded }: { knowledgeBaseId: number; onUploaded: () => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const accept = ".pdf,.docx,.txt,.md,.markdown";
  async function handleFiles(files: File[]) {
    const supported = files.filter((file) => /\.(pdf|docx|txt|md|markdown)$/i.test(file.name));
    if (!supported.length) { setError("PDF, DOCX, TXT veya Markdown dosyası seçin."); return; }
    setError(null); setUploading(true);
    try { await uploadDocuments(supported, knowledgeBaseId); onUploaded(); }
    catch (reason) { setError(getErrorMessage(reason)); }
    finally { setUploading(false); }
  }
  return <div onDragOver={(event) => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={(event) => { event.preventDefault(); setDragging(false); void handleFiles(Array.from(event.dataTransfer.files)); }} className={`rounded-2xl border-2 border-dashed p-7 text-center transition ${dragging ? "border-cyan bg-cyan/5" : "border-slate-200 bg-white hover:border-slate-300"}`}><input ref={inputRef} className="hidden" type="file" multiple accept={accept} onChange={(event) => { void handleFiles(Array.from(event.target.files ?? [])); event.target.value = ""; }} /><div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-cyan/10 text-cyan">{uploading ? <LoaderCircle className="animate-spin" size={22} /> : <FileUp size={22} />}</div><h3 className="mt-4 font-semibold text-ink">Belgeleri buraya bırakın</h3><p className="mt-1 text-sm text-slate-500">Birden fazla dosyayı birlikte indeksleyin.</p><button type="button" className="button-secondary mt-4" disabled={uploading} onClick={() => inputRef.current?.click()}>{uploading ? "Yükleniyor..." : "Dosya seç"}</button><p className="mt-3 text-xs text-slate-400">PDF · DOCX · TXT · Markdown</p>{error && <p className="mt-3 text-sm text-red-600">{error}</p>}</div>;
}
