import {
  render,
  screen,
} from "@testing-library/react";

import userEvent from "@testing-library/user-event";
import {
  describe,
  expect,
  it,
  vi,
} from "vitest";

import {
  MascotChatPanel,
} from "./MascotChatPanel";

describe("MascotChatPanel", () => {
  it("renders the prototype assistant", () => {
    render(
      <MascotChatPanel onClose={vi.fn()} />,
    );

    expect(
      screen.getByRole(
        "dialog",
        { name: "modAI Assistant" },
      ),
    ).toBeInTheDocument();

    expect(
      screen.getByText("Prototype"),
    ).toBeInTheDocument();

    expect(
      screen.queryByText(
        /henüz gerçek modele bağlı değil/i,
      ),
    ).not.toBeInTheDocument();
  });

  it("sends a message and returns a deterministic mock reply", async () => {
    const user = userEvent.setup();

    render(
      <MascotChatPanel onClose={vi.fn()} />,
    );

    const input = screen.getByRole(
      "textbox",
      { name: "Maskota mesaj yaz" },
    );

    await user.type(
      input,
      "Knowledge Base nedir?",
    );

    await user.click(
      screen.getByRole(
        "button",
        { name: "Mesaj gönder" },
      ),
    );

    expect(
      screen.getByText(
        "Knowledge Base nedir?",
      ),
    ).toBeInTheDocument();

    expect(
      screen.getByText(
        /Knowledge Base'ler bölümünde/i,
      ),
    ).toBeInTheDocument();

    expect(input).toHaveValue("");
  });

  it("uses the fallback reply for unknown questions", async () => {
    const user = userEvent.setup();

    render(
      <MascotChatPanel onClose={vi.fn()} />,
    );

    await user.type(
      screen.getByRole(
        "textbox",
        { name: "Maskota mesaj yaz" },
      ),
      "xyz",
    );

    await user.click(
      screen.getByRole(
        "button",
        { name: "Mesaj gönder" },
      ),
    );

    expect(
      screen.getByText(
        /henüz gerçek modele bağlı değil/i,
      ),
    ).toBeInTheDocument();
  });

  it("does not submit an empty message", async () => {
    render(
      <MascotChatPanel onClose={vi.fn()} />,
    );

    expect(
      screen.getByRole(
        "button",
        { name: "Mesaj gönder" },
      ),
    ).toBeDisabled();
  });

  it("calls onClose from the close control", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();

    render(
      <MascotChatPanel onClose={onClose} />,
    );

    await user.click(
      screen.getByRole(
        "button",
        { name: "Maskot sohbetini kapat" },
      ),
    );

    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
