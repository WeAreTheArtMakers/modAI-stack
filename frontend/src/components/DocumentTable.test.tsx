import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { DocumentItem } from "../types";
import { DocumentTable } from "./DocumentTable";

const mocks = vi.hoisted(() => ({ archiveDocument: vi.fn(), unarchiveDocument: vi.fn() }));

vi.mock("../api/documents", () => ({
  archiveDocument: mocks.archiveDocument,
  unarchiveDocument: mocks.unarchiveDocument,
  deleteDocument: vi.fn(),
  listDocumentVersions: vi.fn(),
  reindexDocument: vi.fn(),
  replaceDocument: vi.fn(),
}));

const base: DocumentItem = {
  id: 21,
  filename: "destek-v3.md",
  knowledge_base_id: 4,
  file_size: 2048,
  active_version: 1,
  index_status: "ready",
  index_error: null,
  created_at: "2026-10-01T09:00:00Z",
  updated_at: "2026-10-01T09:00:00Z",
  archived_at: null,
};
const current = base;
const obsolete: DocumentItem = { ...base, id: 20, filename: "destek-v2.md", archived_at: "2026-10-09T12:00:00Z" };

function renderTable(documents: DocumentItem[], canManage: boolean, onChanged = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><DocumentTable documents={documents} canManage={canManage} onChanged={onChanged} /></QueryClientProvider>);
  return onChanged;
}

function row(filename: string) {
  return screen.getByText(filename).closest("tr") as HTMLElement;
}

describe("DocumentTable archive", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.archiveDocument.mockResolvedValue({ ...current, archived_at: "2026-10-10T08:00:00Z" });
    mocks.unarchiveDocument.mockResolvedValue({ ...obsolete, archived_at: null });
  });
  afterEach(() => vi.restoreAllMocks());

  it("marks only archived documents and keeps them listed for every role", () => {
    renderTable([current, obsolete], false);

    expect(within(row("destek-v2.md")).getByText("Arşivde")).toBeInTheDocument();
    expect(within(row("destek-v3.md")).queryByText("Arşivde")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Eski sürüm olarak arşivle" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Arşivden çıkar" })).not.toBeInTheDocument();
  });

  it("archives only after the manager confirms it will no longer be used in answers", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    const user = userEvent.setup();
    const onChanged = renderTable([current], true);

    await user.click(screen.getByRole("button", { name: "Eski sürüm olarak arşivle" }));

    expect(confirm).toHaveBeenCalledTimes(1);
    expect(confirm.mock.calls[0][0]).toMatch(/destek-v3\.md/);
    expect(confirm.mock.calls[0][0]).toMatch(/yanıtlarda kaynak olarak kullanılmaz/);
    expect(mocks.archiveDocument).not.toHaveBeenCalled();

    confirm.mockReturnValue(true);
    await user.click(screen.getByRole("button", { name: "Eski sürüm olarak arşivle" }));

    await waitFor(() => expect(mocks.archiveDocument).toHaveBeenCalledWith(21));
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
    expect(mocks.unarchiveDocument).not.toHaveBeenCalled();
  });

  it("restores an archived document without a confirmation", async () => {
    const confirm = vi.spyOn(window, "confirm");
    const user = userEvent.setup();
    const onChanged = renderTable([obsolete], true);

    expect(screen.queryByRole("button", { name: "Eski sürüm olarak arşivle" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Arşivden çıkar" }));

    await waitFor(() => expect(mocks.unarchiveDocument).toHaveBeenCalledWith(20));
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
    expect(confirm).not.toHaveBeenCalled();
    expect(mocks.archiveDocument).not.toHaveBeenCalled();
  });

  it("shows the API error on the row when archiving fails", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    mocks.archiveDocument.mockRejectedValue(new Error("Document access denied"));
    const user = userEvent.setup();
    const onChanged = renderTable([current], true);

    await user.click(screen.getByRole("button", { name: "Eski sürüm olarak arşivle" }));

    expect(await within(row("destek-v3.md")).findByText("Document access denied")).toBeInTheDocument();
    expect(onChanged).not.toHaveBeenCalled();
  });
});
