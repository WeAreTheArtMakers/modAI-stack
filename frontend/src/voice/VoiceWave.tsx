import { useEffect, useRef } from "react";
import type { VoicePhase } from "./useVoiceAssistant";

const BARS = 28;

/** Live speech activity: microphone level while listening, real output level while speaking. */
export function VoiceWave({ phase, level }: { phase: VoicePhase; level: () => number }) {
  const barsRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    let frame = 0;
    let smooth = 0;
    const tick = (time: number) => {
      const raw = level();
      const busy = phase === "searching" || phase === "answering" || phase === "transcribing";
      const target = raw < 0 ? 0.35 + 0.25 * Math.abs(Math.sin(time / 110)) : busy ? 0.12 : raw;
      smooth = smooth * 0.6 + target * 0.4;
      const bars = barsRef.current?.children;
      if (bars) {
        for (let i = 0; i < bars.length; i++) {
          const wobble = reduced ? 1 : 0.55 + 0.45 * Math.abs(Math.sin(time / 140 + i * 0.7));
          const centre = 1 - Math.abs(i - (BARS - 1) / 2) / BARS;
          (bars[i] as HTMLElement).style.height = `${Math.max(4, Math.round(4 + smooth * 30 * wobble * centre))}px`;
        }
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [level, phase]);

  return <div ref={barsRef} className={`voice-wave is-${phase}`} aria-hidden="true">{Array.from({ length: BARS }, (_, index) => <span key={index} />)}</div>;
}
