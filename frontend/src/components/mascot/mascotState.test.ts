import {
  beforeEach,
  describe,
  expect,
  it,
} from "vitest";

import {
  MASCOT_STORAGE_KEY,
  defaultMascotState,
  loadMascotState,
  saveMascotState,
  type MascotState,
} from "./mascotState";

beforeEach(() => {
  localStorage.clear();
});

describe("mascot state", () => {
  it("uses safe defaults when no state exists", () => {
    expect(loadMascotState()).toEqual(
      defaultMascotState(),
    );
  });

  it("persists and restores mascot state", () => {
    const state: MascotState = {
      visible: false,
      panelOpen: true,
      position: {
        x: 320,
        y: 180,
      },
    };

    saveMascotState(state);

    expect(loadMascotState()).toEqual(state);
  });

  it("recovers from invalid JSON", () => {
    localStorage.setItem(
      MASCOT_STORAGE_KEY,
      "{invalid-json",
    );

    expect(loadMascotState()).toEqual(
      defaultMascotState(),
    );
  });

  it("sanitizes invalid stored fields", () => {
    localStorage.setItem(
      MASCOT_STORAGE_KEY,
      JSON.stringify({
        visible: "no",
        panelOpen: 123,
        position: {
          x: "bad",
          y: 40,
        },
      }),
    );

    expect(loadMascotState()).toEqual(
      defaultMascotState(),
    );
  });

  it("accepts a valid stored position", () => {
    localStorage.setItem(
      MASCOT_STORAGE_KEY,
      JSON.stringify({
        visible: true,
        panelOpen: false,
        position: {
          x: 48,
          y: 96,
        },
      }),
    );

    expect(loadMascotState().position).toEqual({
      x: 48,
      y: 96,
    });
  });
});
