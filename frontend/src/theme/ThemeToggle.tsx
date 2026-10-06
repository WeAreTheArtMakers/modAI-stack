import {
  Moon,
  Sun,
} from "lucide-react";

import {
  useTheme,
} from "./ThemeProvider";

export function ThemeToggle() {
  const {
    theme,
    toggleTheme,
  } = useTheme();

  const dark = theme === "dark";

  return (
    <button
      type="button"
      role="switch"
      aria-checked={dark}
      aria-label={
        dark
          ? "Açık temaya geç"
          : "Koyu temaya geç"
      }
      title={
        dark
          ? "Açık tema"
          : "Koyu tema"
      }
      className="theme-toggle"
      onClick={toggleTheme}
    >
      <span
        className="theme-toggle-icon"
        aria-hidden="true"
      >
        <Sun size={13} />
      </span>

      <span
        className="theme-toggle-track"
        aria-hidden="true"
      >
        <span
          className={[
            "theme-toggle-thumb",
            dark ? "is-dark" : "",
          ].join(" ")}
        />
      </span>

      <span
        className="theme-toggle-icon"
        aria-hidden="true"
      >
        <Moon size={13} />
      </span>
    </button>
  );
}
