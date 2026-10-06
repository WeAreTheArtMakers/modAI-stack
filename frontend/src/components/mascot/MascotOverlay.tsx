import {
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type PointerEvent as ReactPointerEvent,
} from "react";

import {
  EyeOff,
  Sparkles,
} from "lucide-react";

import {
  MascotFace,
} from "./MascotFace";

import {
  MascotChatPanel,
} from "./MascotChatPanel";

import {
  loadMascotState,
  saveMascotState,
  type MascotPosition,
  type MascotState,
} from "./mascotState";

const BUTTON_SIZE = 64;
const VIEWPORT_MARGIN = 12;
const DRAG_THRESHOLD = 4;

type DragSession = {
  pointerId: number;
  startClientX: number;
  startClientY: number;
  startX: number;
  startY: number;
  moved: boolean;
};

export function clampMascotPosition(
  position: MascotPosition,
  viewportWidth = window.innerWidth,
  viewportHeight = window.innerHeight,
): MascotPosition {
  const maxX = Math.max(
    VIEWPORT_MARGIN,
    viewportWidth - BUTTON_SIZE - VIEWPORT_MARGIN,
  );

  const maxY = Math.max(
    VIEWPORT_MARGIN,
    viewportHeight - BUTTON_SIZE - VIEWPORT_MARGIN,
  );

  return {
    x: Math.min(
      Math.max(position.x, VIEWPORT_MARGIN),
      maxX,
    ),
    y: Math.min(
      Math.max(position.y, VIEWPORT_MARGIN),
      maxY,
    ),
  };
}

export function MascotOverlay() {
  const [state, setState] = useState<MascotState>(
    () => loadMascotState(),
  );

  const dragRef = useRef<DragSession | null>(null);
  const suppressClickRef = useRef(false);

  useEffect(() => {
    saveMascotState(state);
  }, [state]);

  useEffect(() => {
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key !== "Escape") {
        return;
      }

      setState((current) => {
        if (!current.panelOpen) {
          return current;
        }

        return {
          ...current,
          panelOpen: false,
        };
      });
    }

    window.addEventListener(
      "keydown",
      closeOnEscape,
    );

    return () => {
      window.removeEventListener(
        "keydown",
        closeOnEscape,
      );
    };
  }, []);

  useEffect(() => {
    function clampOnResize() {
      setState((current) => {
        if (current.position === null) {
          return current;
        }

        const position = clampMascotPosition(
          current.position,
        );

        if (
          position.x === current.position.x
          && position.y === current.position.y
        ) {
          return current;
        }

        return {
          ...current,
          position,
        };
      });
    }

    window.addEventListener(
      "resize",
      clampOnResize,
    );

    return () => {
      window.removeEventListener(
        "resize",
        clampOnResize,
      );
    };
  }, []);

  function handlePointerDown(
    event: ReactPointerEvent<HTMLButtonElement>,
  ) {
    if (event.button !== 0) {
      return;
    }

    const rect =
      event.currentTarget.getBoundingClientRect();

    dragRef.current = {
      pointerId: event.pointerId,
      startClientX: event.clientX,
      startClientY: event.clientY,
      startX: state.position?.x ?? rect.left,
      startY: state.position?.y ?? rect.top,
      moved: false,
    };

    event.currentTarget.setPointerCapture?.(
      event.pointerId,
    );
  }

  function handlePointerMove(
    event: ReactPointerEvent<HTMLButtonElement>,
  ) {
    const drag = dragRef.current;

    if (
      drag === null
      || drag.pointerId !== event.pointerId
    ) {
      return;
    }

    const deltaX =
      event.clientX - drag.startClientX;

    const deltaY =
      event.clientY - drag.startClientY;

    if (
      !drag.moved
      && Math.hypot(deltaX, deltaY)
        < DRAG_THRESHOLD
    ) {
      return;
    }

    drag.moved = true;

    const position = clampMascotPosition({
      x: drag.startX + deltaX,
      y: drag.startY + deltaY,
    });

    setState((current) => ({
      ...current,
      position,
    }));
  }

  function handlePointerUp(
    event: ReactPointerEvent<HTMLButtonElement>,
  ) {
    const drag = dragRef.current;

    if (
      drag === null
      || drag.pointerId !== event.pointerId
    ) {
      return;
    }

    event.currentTarget.releasePointerCapture?.(
      event.pointerId,
    );

    suppressClickRef.current = drag.moved;
    dragRef.current = null;
  }

  function togglePanel() {
    if (suppressClickRef.current) {
      suppressClickRef.current = false;
      return;
    }

    setState((current) => ({
      ...current,
      panelOpen: !current.panelOpen,
    }));
  }

  function hideMascot() {
    setState((current) => ({
      ...current,
      visible: false,
      panelOpen: false,
    }));
  }

  function restoreMascot() {
    setState((current) => ({
      ...current,
      visible: true,
      panelOpen: false,
    }));
  }

  const mascotStyle: CSSProperties =
    state.position === null
      ? {
          right: 24,
          bottom: 24,
        }
      : {
          left: state.position.x,
          top: state.position.y,
        };

  const resolvedPosition =
    state.position ?? {
      x: window.innerWidth - BUTTON_SIZE - 24,
      y: window.innerHeight - BUTTON_SIZE - 24,
    };

  const openBelow =
    resolvedPosition.y + BUTTON_SIZE / 2
    < window.innerHeight / 2;

  const alignLeft =
    resolvedPosition.x + BUTTON_SIZE / 2
    < window.innerWidth / 2;

  const panelPlacement = [
    openBelow ? "below" : "above",
    alignLeft ? "left" : "right",
  ].join("-");

  if (!state.visible) {
    return (
      <div className="pointer-events-none fixed inset-0 z-[60]">
        <button
          type="button"
          aria-label="Maskotu göster"
          title="modAI Assistant'ı göster"
          className="pointer-events-auto fixed bottom-6 right-6 flex h-11 w-11 items-center justify-center rounded-full border border-slate-200 bg-white text-ink shadow-lg transition hover:-translate-y-0.5 hover:border-cyan/40 hover:text-cyan"
          onClick={restoreMascot}
        >
          <Sparkles size={18} />
        </button>
      </div>
    );
  }

  return (
    <div className="pointer-events-none fixed inset-0 z-[60]">
      <div
        className="pointer-events-auto fixed"
        style={mascotStyle}
      >
        <div className="relative">
          {state.panelOpen && (
            <div
              data-testid="mascot-panel-anchor"
              data-placement={panelPlacement}
              className={[
                "absolute z-10",
                openBelow
                  ? "top-[calc(100%+12px)]"
                  : "bottom-[calc(100%+12px)]",
                alignLeft
                  ? "left-0"
                  : "right-0",
              ].join(" ")}
            >
              <MascotChatPanel
                onClose={() => {
                  setState((current) => ({
                    ...current,
                    panelOpen: false,
                  }));
                }}
              />
            </div>
          )}
          <button
            type="button"
            aria-label="modAI Assistant"
            aria-expanded={state.panelOpen}
            title="modAI Assistant"
            className="group relative flex h-16 w-16 touch-none select-none items-center justify-center rounded-[22px] border border-white/70 bg-ink text-white shadow-2xl outline-none transition hover:-translate-y-0.5 focus-visible:ring-4 focus-visible:ring-cyan/20"
            onClick={togglePanel}
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={handlePointerUp}
            onPointerCancel={() => {
              dragRef.current = null;
            }}
          >
            <span className="absolute inset-1 rounded-[18px] bg-gradient-to-br from-cyan/25 via-transparent to-white/10" />

            <MascotFace active={state.panelOpen} />
          </button>

          <button
            type="button"
            aria-label="Maskotu gizle"
            title="Maskotu gizle"
            className="absolute -left-2 -top-2 flex h-7 w-7 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-400 shadow-md transition hover:text-ink"
            onPointerDown={(event) => {
              event.stopPropagation();
            }}
            onClick={(event) => {
              event.stopPropagation();
              hideMascot();
            }}
          >
            <EyeOff size={13} />
          </button>
        </div>
      </div>
    </div>
  );
}
