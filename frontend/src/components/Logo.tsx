import { Sparkles } from "lucide-react";

export function Logo({ compact = false }: { compact?: boolean }) {
  return <div className="flex items-center gap-3">
    <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-ink text-white shadow-sm"><Sparkles size={17} strokeWidth={1.8} /></span>
    {!compact && <span className="text-lg font-bold tracking-tight text-ink">modAI<span className="text-coral">.</span></span>}
  </div>;
}
