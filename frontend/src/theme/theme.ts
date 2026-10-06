export const THEME_STORAGE_KEY = "modai.theme.v1";

export type Theme = "light" | "dark";

export function systemTheme(): Theme {
  if (
    typeof window !== "undefined"
    && window.matchMedia?.(
      "(prefers-color-scheme: dark)",
    ).matches
  ) {
    return "dark";
  }

  return "light";
}

export function loadTheme(
  storage: Storage = window.localStorage,
): Theme {
  try {
    const stored = storage.getItem(
      THEME_STORAGE_KEY,
    );

    if (
      stored === "light"
      || stored === "dark"
    ) {
      return stored;
    }
  } catch {
    // Theme persistence must never break the UI.
  }

  return systemTheme();
}

export function saveTheme(
  theme: Theme,
  storage: Storage = window.localStorage,
): void {
  try {
    storage.setItem(
      THEME_STORAGE_KEY,
      theme,
    );
  } catch {
    // Theme persistence must never break the UI.
  }
}

export function applyTheme(
  theme: Theme,
  root: HTMLElement = document.documentElement,
): void {
  root.classList.toggle(
    "dark",
    theme === "dark",
  );

  root.style.colorScheme = theme;

  document
    .querySelector(
      'meta[name="theme-color"]',
    )
    ?.setAttribute(
      "content",
      theme === "dark"
        ? "#0b1120"
        : "#f4f6f9",
    );
}
