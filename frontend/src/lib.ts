import type { Role } from "./types";

export function canManage(role: Role | null | undefined): boolean {
  return role === "admin" || role === "manager";
}

export function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 ** 2).toFixed(1)} MB`;
}

export function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("tr-TR", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

export function statusLabel(status: string): string {
  const labels: Record<string, string> = { queued: "Kuyrukta", processing: "İşleniyor", ready: "Hazır", failed: "Hatalı", extracting: "Metin çıkarılıyor", chunking: "Parçalanıyor", embedding: "Embedding", vector_indexing: "Vektörleniyor" };
  return labels[status] ?? status;
}

export function statusTone(status: string): string {
  if (status === "ready") return "bg-emerald-50 text-emerald-700";
  if (status === "failed") return "bg-red-50 text-red-700";
  if (status === "processing") return "bg-cyan/10 text-cyan";
  return "bg-amber-50 text-amber-700";
}
