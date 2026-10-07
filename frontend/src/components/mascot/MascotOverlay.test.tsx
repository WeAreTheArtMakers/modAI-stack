import {
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";

import userEvent from "@testing-library/user-event";

import {
  afterAll,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";

vi.mock("../../auth/AuthContext", () => ({
  useAuth: () => ({ user: { id: 5 } }),
}));

import {
  MascotOverlay,
  clampMascotPosition,
} from "./MascotOverlay";

import {
  MASCOT_STORAGE_KEY,
} from "./mascotState";

const originalPointerEvent = window.PointerEvent;

type TestPointerEventInit = {
  pointerId?: number;
  button?: number;
  clientX?: number;
  clientY?: number;
};

class TestPointerEvent extends MouseEvent {
  readonly pointerId: number;

  constructor(
    type: string,
    init: TestPointerEventInit = {},
  ) {
    super(type, init);
    this.pointerId = init.pointerId ?? 0;
  }
}

beforeAll(() => {
  Object.defineProperty(
    window,
    "PointerEvent",
    {
      configurable: true,
      writable: true,
      value: TestPointerEvent,
    },
  );
});

afterAll(() => {
  Object.defineProperty(
    window,
    "PointerEvent",
    {
      configurable: true,
      writable: true,
      value: originalPointerEvent,
    },
  );
});

beforeEach(() => {
  localStorage.clear();
});

describe("MascotOverlay", () => {
  it("opens and closes the mini chat", async () => {
    const user = userEvent.setup();

    render(<MascotOverlay />);

    const mascot = screen.getByRole(
      "button",
      { name: "modAI Assistant" },
    );

    expect(
      screen.queryByRole(
        "dialog",
        { name: "modAI Assistant" },
      ),
    ).not.toBeInTheDocument();

    await user.click(mascot);

    expect(
      screen.getByRole(
        "dialog",
        { name: "modAI Assistant" },
      ),
    ).toBeInTheDocument();

    await user.click(
      screen.getByRole(
        "button",
        { name: "Maskot sohbetini kapat" },
      ),
    );

    expect(
      screen.queryByRole(
        "dialog",
        { name: "modAI Assistant" },
      ),
    ).not.toBeInTheDocument();
  });

  it("hides and restores the mascot", async () => {
    const user = userEvent.setup();

    render(<MascotOverlay />);

    await user.click(
      screen.getByRole(
        "button",
        { name: "Maskotu gizle" },
      ),
    );

    expect(
      screen.queryByRole(
        "button",
        { name: "modAI Assistant" },
      ),
    ).not.toBeInTheDocument();

    const restore = screen.getByRole(
      "button",
      { name: "Maskotu göster" },
    );

    expect(restore).toBeInTheDocument();

    await user.click(restore);

    expect(
      screen.getByRole(
        "button",
        { name: "modAI Assistant" },
      ),
    ).toBeInTheDocument();
  });

  it("closes the panel with Escape", async () => {
    const user = userEvent.setup();

    render(<MascotOverlay />);

    await user.click(
      screen.getByRole(
        "button",
        { name: "modAI Assistant" },
      ),
    );

    expect(
      screen.getByRole(
        "dialog",
        { name: "modAI Assistant" },
      ),
    ).toBeInTheDocument();

    fireEvent.keyDown(
      window,
      { key: "Escape" },
    );

    expect(
      screen.queryByRole(
        "dialog",
        { name: "modAI Assistant" },
      ),
    ).not.toBeInTheDocument();
  });

  it("persists visibility state", async () => {
    const user = userEvent.setup();

    render(<MascotOverlay />);

    await user.click(
      screen.getByRole(
        "button",
        { name: "Maskotu gizle" },
      ),
    );

    await waitFor(() => {
      const stored = JSON.parse(
        localStorage.getItem(
          MASCOT_STORAGE_KEY,
        ) ?? "{}",
      );

      expect(stored.visible).toBe(false);
      expect(stored.panelOpen).toBe(false);
    });
  });

  it("persists a dragged position without opening chat", async () => {
    render(<MascotOverlay />);

    const mascot = screen.getByRole(
      "button",
      { name: "modAI Assistant" },
    );

    Object.defineProperty(
      mascot,
      "getBoundingClientRect",
      {
        configurable: true,
        value: () => ({
          x: 800,
          y: 600,
          left: 800,
          top: 600,
          right: 864,
          bottom: 664,
          width: 64,
          height: 64,
          toJSON: () => ({}),
        }),
      },
    );

    fireEvent.pointerDown(
      mascot,
      {
        button: 0,
        pointerId: 1,
        clientX: 820,
        clientY: 620,
      },
    );

    fireEvent.pointerMove(
      mascot,
      {
        pointerId: 1,
        clientX: 720,
        clientY: 520,
      },
    );

    fireEvent.pointerUp(
      mascot,
      {
        pointerId: 1,
        clientX: 720,
        clientY: 520,
      },
    );

    fireEvent.click(mascot);

    expect(
      screen.queryByRole(
        "dialog",
        { name: "modAI Assistant" },
      ),
    ).not.toBeInTheDocument();

    await waitFor(() => {
      const stored = JSON.parse(
        localStorage.getItem(
          MASCOT_STORAGE_KEY,
        ) ?? "{}",
      );

      expect(stored.position).toEqual({
        x: 700,
        y: 500,
      });
    });
  });

  it("positions the chat panel relative to the mascot", async () => {
    const user = userEvent.setup();

    localStorage.setItem(
      MASCOT_STORAGE_KEY,
      JSON.stringify({
        visible: true,
        panelOpen: false,
        position: {
          x: 24,
          y: 24,
        },
      }),
    );

    render(<MascotOverlay />);

    await user.click(
      screen.getByRole(
        "button",
        { name: "modAI Assistant" },
      ),
    );

    expect(
      screen.getByTestId(
        "mascot-panel-anchor",
      ),
    ).toHaveAttribute(
      "data-placement",
      "below-left",
    );
  });

  it("clamps stored coordinates to the viewport", () => {
    expect(
      clampMascotPosition(
        {
          x: -100,
          y: 1000,
        },
        400,
        300,
      ),
    ).toEqual({
      x: 12,
      y: 224,
    });
  });
});
