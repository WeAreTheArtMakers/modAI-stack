import { useEffect, useRef } from "react";
import type { VoicePhase } from "./useVoiceAssistant";

const PHASE_LABELS: Record<VoicePhase, string> = {
  idle: "Hazır",
  listening: "Dinliyorum…",
  transcribing: "Yazıya çeviriyorum…",
  thinking: "Belgelerde arıyorum…",
  speaking: "Yanıtlıyorum",
  error: "Bir sorun oluştu",
};

export function phaseLabel(phase: VoicePhase): string {
  return PHASE_LABELS[phase];
}

/**
 * The modAI robot, large and animated. `level()` returns 0..1 from the real microphone input
 * (listening) or audio output (speaking), or -1 when only a system voice without amplitude
 * data is speaking.
 */
export function VoiceMascot({ phase, level }: { phase: VoicePhase; level: () => number }) {
  const mouthRef = useRef<SVGEllipseElement>(null);
  const ringsRef = useRef<SVGGElement>(null);

  useEffect(() => {
    let frame = 0;
    let smooth = 0;
    const tick = (time: number) => {
      const raw = level();
      const target = raw < 0 ? 0.35 + 0.3 * Math.abs(Math.sin(time / 90)) : raw;
      smooth = smooth * 0.55 + target * 0.45;
      if (mouthRef.current) {
        const open = phase === "speaking" ? smooth : 0;
        mouthRef.current.setAttribute("ry", (1.5 + open * 13).toFixed(2));
        mouthRef.current.setAttribute("rx", (15 - open * 3).toFixed(2));
      }
      if (ringsRef.current) ringsRef.current.style.setProperty("--voice-level", phase === "listening" ? smooth.toFixed(3) : "0");
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [level, phase]);

  return (
    <div className={`voice-mascot is-${phase}`} data-phase={phase} role="img" aria-label={`modAI asistanı: ${phaseLabel(phase)}`}>
      <svg viewBox="0 0 240 240" aria-hidden="true">
        <defs>
          <radialGradient id="voice-glow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="var(--voice-accent)" stopOpacity="0.45" />
            <stop offset="100%" stopColor="var(--voice-accent)" stopOpacity="0" />
          </radialGradient>
          <linearGradient id="voice-head" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#1f2a44" />
            <stop offset="100%" stopColor="#0b1120" />
          </linearGradient>
          <linearGradient id="voice-screen" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#22d3ee" stopOpacity="0.2" />
            <stop offset="100%" stopColor="#22d3ee" stopOpacity="0.05" />
          </linearGradient>
        </defs>
        <circle className="voice-mascot-glow" cx="120" cy="128" r="112" fill="url(#voice-glow)" />
        <g ref={ringsRef} className="voice-mascot-rings">
          <circle cx="120" cy="126" r="92" />
          <circle cx="120" cy="126" r="104" />
        </g>
        <g className="voice-mascot-body">
          <line className="voice-mascot-antenna" x1="120" y1="58" x2="120" y2="34" />
          <circle className="voice-mascot-antenna-dot" cx="120" cy="30" r="7" />
          <rect className="voice-mascot-ear" x="26" y="104" width="18" height="44" rx="9" />
          <rect className="voice-mascot-ear" x="196" y="104" width="18" height="44" rx="9" />
          <rect x="40" y="58" width="160" height="136" rx="46" fill="url(#voice-head)" stroke="rgba(255,255,255,0.14)" />
          <rect x="58" y="78" width="124" height="96" rx="32" fill="url(#voice-screen)" stroke="rgba(103,232,249,0.18)" />
          <g className="voice-mascot-eyes">
            <rect className="voice-mascot-eye" x="88" y="104" width="16" height="22" rx="8" />
            <rect className="voice-mascot-eye" x="136" y="104" width="16" height="22" rx="8" />
          </g>
          <g className="voice-mascot-error-eyes">
            <path d="M88 106 l16 18 M104 106 l-16 18" />
            <path d="M136 106 l16 18 M152 106 l-16 18" />
          </g>
          <ellipse ref={mouthRef} className="voice-mascot-mouth" cx="120" cy="150" rx="15" ry="1.5" />
          <path className="voice-mascot-smile" d="M106 146 q14 12 28 0" />
        </g>
        <g className="voice-mascot-thinking">
          <circle cx="186" cy="46" r="4" />
          <circle cx="200" cy="31" r="5.5" />
          <circle cx="217" cy="15" r="7" />
        </g>
      </svg>
    </div>
  );
}
