import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ request: vi.fn() }));

vi.mock("./client", () => ({ request: mocks.request }));

import { archiveDocument, unarchiveDocument } from "./documents";

describe("document archive API", () => {
  beforeEach(() => vi.clearAllMocks());

  it("archives and restores a document with POST requests", async () => {
    mocks.request.mockResolvedValue({ id: 20, archived_at: null });

    await archiveDocument(20);
    await unarchiveDocument(20);

    expect(mocks.request).toHaveBeenNthCalledWith(1, "/documents/20/archive", { method: "POST" });
    expect(mocks.request).toHaveBeenNthCalledWith(2, "/documents/20/unarchive", { method: "POST" });
  });
});
