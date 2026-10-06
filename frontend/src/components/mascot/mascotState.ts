export const MASCOT_STORAGE_KEY = "modai.mascot.v1";

export type MascotPosition = {
  x: number;
  y: number;
};

export type MascotState = {
  visible: boolean;
  panelOpen: boolean;
  position: MascotPosition | null;
};

export function defaultMascotState(): MascotState {
  return {
    visible: true,
    panelOpen: false,
    position: null,
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return (
    typeof value === "object" &&
    value !== null &&
    !Array.isArray(value)
  );
}

function parsePosition(
  value: unknown,
): MascotPosition | null {
  if (value === null) {
    return null;
  }

  if (!isRecord(value)) {
    return null;
  }

  const { x, y } = value;

  if (
    typeof x !== "number" ||
    typeof y !== "number" ||
    !Number.isFinite(x) ||
    !Number.isFinite(y)
  ) {
    return null;
  }

  return { x, y };
}

export function loadMascotState(
  storage: Storage = window.localStorage,
): MascotState {
  const fallback = defaultMascotState();

  try {
    const raw = storage.getItem(MASCOT_STORAGE_KEY);

    if (!raw) {
      return fallback;
    }

    const parsed: unknown = JSON.parse(raw);

    if (!isRecord(parsed)) {
      return fallback;
    }

    return {
      visible:
        typeof parsed.visible === "boolean"
          ? parsed.visible
          : fallback.visible,
      panelOpen:
        typeof parsed.panelOpen === "boolean"
          ? parsed.panelOpen
          : fallback.panelOpen,
      position: parsePosition(parsed.position),
    };
  } catch {
    return fallback;
  }
}

export function saveMascotState(
  state: MascotState,
  storage: Storage = window.localStorage,
): void {
  try {
    storage.setItem(
      MASCOT_STORAGE_KEY,
      JSON.stringify(state),
    );
  } catch {
    // Mascot persistence must never break the application.
  }
}
