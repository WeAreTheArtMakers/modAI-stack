import {
  render,
  screen,
} from "@testing-library/react";

import userEvent from "@testing-library/user-event";

import {
  beforeEach,
  describe,
  expect,
  it,
} from "vitest";

import {
  ThemeProvider,
} from "./ThemeProvider";

import {
  ThemeToggle,
} from "./ThemeToggle";

import {
  THEME_STORAGE_KEY,
} from "./theme";

beforeEach(() => {
  localStorage.clear();

  document.documentElement.classList.remove(
    "dark",
  );

  document.documentElement.style.colorScheme = "";
});

describe("ThemeProvider", () => {
  it("toggles between light and dark mode", async () => {
    const user = userEvent.setup();

    render(
      <ThemeProvider>
        <ThemeToggle />
      </ThemeProvider>,
    );

    const toggle = screen.getByRole(
      "switch",
    );

    expect(toggle).toHaveAttribute(
      "aria-checked",
      "false",
    );

    await user.click(toggle);

    expect(toggle).toHaveAttribute(
      "aria-checked",
      "true",
    );

    expect(
      document.documentElement,
    ).toHaveClass("dark");
  });

  it("persists the selected theme", async () => {
    const user = userEvent.setup();

    render(
      <ThemeProvider>
        <ThemeToggle />
      </ThemeProvider>,
    );

    await user.click(
      screen.getByRole("switch"),
    );

    expect(
      localStorage.getItem(
        THEME_STORAGE_KEY,
      ),
    ).toBe("dark");
  });

  it("restores a stored dark theme", () => {
    localStorage.setItem(
      THEME_STORAGE_KEY,
      "dark",
    );

    render(
      <ThemeProvider>
        <ThemeToggle />
      </ThemeProvider>,
    );

    expect(
      screen.getByRole("switch"),
    ).toHaveAttribute(
      "aria-checked",
      "true",
    );

    expect(
      document.documentElement,
    ).toHaveClass("dark");
  });
});
