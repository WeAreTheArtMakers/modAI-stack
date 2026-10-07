import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ request: vi.fn() }));

vi.mock("./client", () => ({ request: mocks.request }));

import {
  getAssistantConversation,
  listAssistantConversations,
} from "./assistantConversations";

describe("assistant conversation API", () => {
  beforeEach(() => vi.clearAllMocks());

  it("lists only non-archived conversations for the requested workspace", async () => {
    mocks.request.mockResolvedValue({ items: [], total: 0, limit: 100, offset: 0 });

    await listAssistantConversations(7);

    expect(mocks.request).toHaveBeenCalledWith(
      "/assistant/conversations?workspace_id=7&include_archived=false&limit=100&offset=0",
    );
  });

  it("combines newest-first API pages into one chronological transcript", async () => {
    const makePage = (ids: number[], offset: number) => ({
      id: 42,
      workspace_id: 7,
      title: null,
      created_at: null,
      updated_at: null,
      archived_at: null,
      messages: ids.map((id) => ({
        id,
        role: "user" as const,
        content: `message ${id}`,
        sources: [],
        created_at: null,
      })),
      message_total: 205,
      message_limit: 100,
      message_offset: offset,
    });
    mocks.request
      .mockResolvedValueOnce(makePage(
        Array.from({ length: 100 }, (_, index) => 106 + index),
        0,
      ))
      .mockResolvedValueOnce(makePage(
        Array.from({ length: 100 }, (_, index) => 6 + index),
        100,
      ))
      .mockResolvedValueOnce(makePage(
        Array.from({ length: 5 }, (_, index) => index + 1),
        200,
      ));

    const transcript = await getAssistantConversation(42);

    expect(transcript.messages.map((message) => message.id)).toEqual(
      Array.from({ length: 205 }, (_, index) => index + 1),
    );
    expect(mocks.request).toHaveBeenNthCalledWith(
      1,
      "/assistant/conversations/42?message_limit=100&message_offset=0",
    );
    expect(mocks.request).toHaveBeenNthCalledWith(
      3,
      "/assistant/conversations/42?message_limit=100&message_offset=200",
    );
  });
});
