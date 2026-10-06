type MascotFaceProps = {
  active?: boolean;
  compact?: boolean;
};

export function MascotFace({
  active = false,
  compact = false,
}: MascotFaceProps) {
  return (
    <span
      aria-hidden="true"
      className={[
        "modai-mascot-face",
        active ? "is-active" : "",
        compact ? "is-compact" : "",
      ].join(" ")}
    >
      <span className="modai-mascot-antenna">
        <span className="modai-mascot-antenna-dot" />
      </span>

      <span className="modai-mascot-head">
        <span className="modai-mascot-screen">
          <span className="modai-mascot-eyes">
            <span className="modai-mascot-eye" />
            <span className="modai-mascot-eye" />
          </span>

          <span className="modai-mascot-mouth" />
        </span>

        <span className="modai-mascot-ear modai-mascot-ear-left" />
        <span className="modai-mascot-ear modai-mascot-ear-right" />
      </span>

      <span className="modai-mascot-glow" />
    </span>
  );
}
