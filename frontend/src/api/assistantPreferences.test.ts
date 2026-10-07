import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ request: vi.fn() }));

vi.mock("./client", () => ({ request: mocks.request }));

import {
  DEFAULT_ASSISTANT_PREFERENCES,
  getAssistantPreferences,
  updateAssistantPreferences,
} from "./assistantPreferences";

beforeEach(() => vi.clearAllMocks());

describe("assistant preference API", () => {
  it("gets the current user's effective preferences", async () => {
    mocks.request.mockResolvedValueOnce(DEFAULT_ASSISTANT_PREFERENCES);
    await getAssistantPreferences();
    expect(mocks.request).toHaveBeenCalledWith("/assistant/preferences");
  });

  it("sends only the typed preference contract in PUT", async () => {
    const payload = {
      assistant_name: "Aurora",
      language: "tr" as const,
      tone: "friendly" as const,
      response_length: "short" as const,
    };
    mocks.request.mockResolvedValueOnce({ ...payload, updated_at: null });
    await updateAssistantPreferences(payload);
    expect(mocks.request).toHaveBeenCalledWith("/assistant/preferences", {
      method: "PUT",
      body: JSON.stringify(payload),
    });
  });
});
