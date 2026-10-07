import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";

import userEvent from "@testing-library/user-event";

import {
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";

import type {
  RagEvent,
} from "../../types";

import {
  MascotChatPanel,
} from "./MascotChatPanel";

const mocks = vi.hoisted(() => ({
  listKnowledgeBases: vi.fn(),
  listAssistantConversations: vi.fn(),
  createAssistantConversation: vi.fn(),
  getAssistantConversation: vi.fn(),
  streamRag: vi.fn(),
}));

vi.mock("../../api/knowledgeBases", () => ({
  listKnowledgeBases:
    mocks.listKnowledgeBases,
}));

vi.mock("../../api/assistantConversations", () => ({
  listAssistantConversations:
    mocks.listAssistantConversations,
  createAssistantConversation:
    mocks.createAssistantConversation,
  getAssistantConversation:
    mocks.getAssistantConversation,
}));

vi.mock("../../api/websocket", () => ({
  streamRag: mocks.streamRag,
}));

beforeEach(() => {
  vi.clearAllMocks();

  mocks.listKnowledgeBases.mockResolvedValue([
    {
      id: 11,
      workspace_id: 7,
      name: "Engineering",
      slug: "engineering",
      description: null,
      membership_role: "admin",
    },
    {
      id: 12,
      workspace_id: 7,
      name: "Operations",
      slug: "operations",
      description: null,
      membership_role: "user",
    },
    {
      id: 99,
      workspace_id: 8,
      name: "Other Workspace",
      slug: "other",
      description: null,
      membership_role: "user",
    },
  ]);

  mocks.streamRag.mockResolvedValue(
    undefined,
  );

  mocks.listAssistantConversations.mockResolvedValue({
    items: [],
    total: 0,
    limit: 100,
    offset: 0,
  });
  mocks.createAssistantConversation.mockImplementation(
    async (workspaceId: number) => ({
      id: 100 + workspaceId,
      workspace_id: workspaceId,
      title: null,
      created_at: null,
      updated_at: null,
      archived_at: null,
    }),
  );
  mocks.getAssistantConversation.mockImplementation(
    async (id: number) => ({
      id,
      workspace_id: id - 100,
      title: null,
      created_at: null,
      updated_at: null,
      archived_at: null,
      messages: [],
      message_total: 0,
      message_limit: 100,
      message_offset: 0,
    }),
  );
});

describe("MascotChatPanel", () => {
  it(
    "loads authorized sources for the active workspace",
    async () => {
      render(
        <MascotChatPanel
          workspaceId={7}
          onClose={vi.fn()}
        />,
      );

      expect(
        screen.getByRole(
          "dialog",
          { name: "modAI Assistant" },
        ),
      ).toBeInTheDocument();

      expect(
        screen.getByText("Local RAG"),
      ).toBeInTheDocument();

      expect(
        await screen.findByText(
          "2 yetkili KB · kaynak destekli",
        ),
      ).toBeInTheDocument();
    },
  );

  it(
    "answers assistant identity locally without calling RAG",
    async () => {
      const user = userEvent.setup();

      render(
        <MascotChatPanel
          workspaceId={7}
          onClose={vi.fn()}
        />,
      );

      const input =
        await screen.findByRole(
          "textbox",
          { name: "Maskota mesaj yaz" },
        );

      await user.type(
        input,
        "merhaba sen kimsin?",
      );

      await user.click(
        screen.getByRole(
          "button",
          { name: "Mesaj gönder" },
        ),
      );

      expect(
        await screen.findByText(
          /modAI-stack içinde çalışan yerel yardımcınım/i,
        ),
      ).toBeInTheDocument();

      expect(
        mocks.streamRag,
      ).not.toHaveBeenCalled();
    },
  );

  it(
    "answers creator questions locally without calling RAG",
    async () => {
      const user = userEvent.setup();

      render(
        <MascotChatPanel
          workspaceId={7}
          onClose={vi.fn()}
        />,
      );

      const input =
        await screen.findByRole(
          "textbox",
          { name: "Maskota mesaj yaz" },
        );

      await user.type(
        input,
        "seni kim programladı?",
      );

      await user.click(
        screen.getByRole(
          "button",
          { name: "Mesaj gönder" },
        ),
      );

      expect(
        await screen.findByText(
          /We Are The Art Makers tarafından geliştiriliyor/i,
        ),
      ).toBeInTheDocument();

      expect(
        mocks.streamRag,
      ).not.toHaveBeenCalled();
    },
  );

  it(
    "scopes RAG to an explicitly named authorized knowledge base",
    async () => {
      const user = userEvent.setup();

      render(
        <MascotChatPanel
          workspaceId={7}
          onClose={vi.fn()}
        />,
      );

      expect(
        await screen.findByText(
          "2 yetkili KB · kaynak destekli",
        ),
      ).toBeInTheDocument();

      const input = screen.getByRole(
        "textbox",
        { name: "Maskota mesaj yaz" },
      );

      await user.type(
        input,
        "Operations içindeki çalışma prosedürü nedir?",
      );

      await user.click(
        screen.getByRole(
          "button",
          { name: "Mesaj gönder" },
        ),
      );

      await waitFor(() =>
        expect(
          mocks.streamRag,
        ).toHaveBeenCalledTimes(1),
      );

      const call =
        mocks.streamRag.mock.calls[0];

      expect(call[0]).toEqual([12]);
      expect(call[1]).toBe(
        "Operations içindeki çalışma prosedürü nedir?",
      );
    },
  );

  it(
    "stops an explicitly scoped RAG request when retrieval has no live sources",
    async () => {
      const user = userEvent.setup();

      mocks.streamRag.mockImplementation(
        async (
          _ids: number[],
          _question: string,
          onEvent: (
            event: RagEvent,
          ) => void,
        ) => {
          onEvent({
            type: "sources",
            data: [],
          });

          onEvent({
            type: "token",
            data: "Bu metin görünmemeli",
          });
        },
      );

      render(
        <MascotChatPanel
          workspaceId={7}
          onClose={vi.fn()}
        />,
      );

      expect(
        await screen.findByText(
          "2 yetkili KB · kaynak destekli",
        ),
      ).toBeInTheDocument();

      const input = screen.getByRole(
        "textbox",
        { name: "Maskota mesaj yaz" },
      );

      await user.type(
        input,
        "Operations içindeki kaynak ne diyor?",
      );

      await user.click(
        screen.getByRole(
          "button",
          { name: "Mesaj gönder" },
        ),
      );

      expect(
        await screen.findByText(
          "Bu Knowledge Base içinde kullanılabilir bir kaynak bulunamadı.",
        ),
      ).toBeInTheDocument();

      expect(
        screen.queryByText(
          "Bu metin görünmemeli",
        ),
      ).not.toBeInTheDocument();

      const call =
        mocks.streamRag.mock.calls[0];

      expect(call[0]).toEqual([12]);

      expect(
        (call[3] as AbortSignal).aborted,
      ).toBe(true);
    },
  );

  it(
    "streams a source-backed RAG answer",
    async () => {
      const user = userEvent.setup();

      mocks.streamRag.mockImplementation(
        async (
          _ids: number[],
          _question: string,
          onEvent: (
            event: RagEvent,
          ) => void,
        ) => {
          onEvent({
            type: "sources",
            data: [
              {
                document: "guide.pdf",
                score: 0.92,
                document_id: 3,
                chunk_index: 1,
                text: "source text",
              },
            ],
          });

          onEvent({
            type: "token",
            data: "Yerel model ",
          });

          onEvent({
            type: "token",
            data: "yanıtı",
          });

          onEvent({
            type: "complete",
          });
        },
      );

      render(
        <MascotChatPanel
          workspaceId={7}
          onClose={vi.fn()}
        />,
      );

      const input =
        await screen.findByRole(
          "textbox",
          { name: "Maskota mesaj yaz" },
        );

      await user.type(
        input,
        "Politikamız nedir?",
      );

      await user.click(
        screen.getByRole(
          "button",
          { name: "Mesaj gönder" },
        ),
      );

      expect(
        await screen.findByText(
          "Yerel model yanıtı",
        ),
      ).toBeInTheDocument();

      expect(
        screen.getByText("1 kaynak"),
      ).toBeInTheDocument();

      const call =
        mocks.streamRag.mock.calls[0];

      expect(call[0]).toEqual([11, 12]);
      expect(call[1]).toBe(
        "Politikamız nedir?",
      );
      expect(call[2]).toEqual(
        expect.any(Function),
      );
      expect(call[3]).toBeInstanceOf(
        AbortSignal,
      );
      expect(call[4]).toEqual({ conversationId: 107 });
      expect(mocks.createAssistantConversation)
        .toHaveBeenCalledWith(7);

      expect(input).toHaveValue("");
    },
  );

  it(
    "hydrates the active conversation in chronological order and continues it",
    async () => {
      const user = userEvent.setup();
      mocks.listAssistantConversations.mockResolvedValue({
        items: [{
          id: 42,
          workspace_id: 7,
          title: null,
          created_at: null,
          updated_at: null,
          archived_at: null,
        }],
        total: 1,
        limit: 100,
        offset: 0,
      });
      mocks.getAssistantConversation.mockResolvedValue({
        id: 42,
        workspace_id: 7,
        title: null,
        created_at: null,
        updated_at: null,
        archived_at: null,
        messages: [
          {
            id: 8,
            role: "user",
            content: "Earlier question",
            sources: [],
            created_at: null,
          },
          {
            id: 9,
            role: "assistant",
            content: "Earlier answer",
            sources: [{
              document: "policy.pdf",
              score: 0.9,
              document_id: 5,
              chunk_index: 2,
            }],
            created_at: null,
          },
        ],
        message_total: 2,
        message_limit: 100,
        message_offset: 0,
      });

      render(
        <MascotChatPanel
          workspaceId={7}
          onClose={vi.fn()}
        />,
      );

      expect(await screen.findByText("Earlier question"))
        .toBeInTheDocument();
      expect(screen.getByText("Earlier answer"))
        .toBeInTheDocument();
      expect(screen.getByText("1 kaynak"))
        .toBeInTheDocument();

      const input = screen.getByRole(
        "textbox",
        { name: "Maskota mesaj yaz" },
      );
      await user.type(input, "Follow-up question");
      await user.click(screen.getByRole(
        "button",
        { name: "Mesaj gönder" },
      ));

      await waitFor(() => expect(mocks.streamRag).toHaveBeenCalledTimes(1));
      expect(mocks.createAssistantConversation)
        .not.toHaveBeenCalled();
      expect(mocks.streamRag.mock.calls[0][4])
        .toEqual({ conversationId: 42 });
    },
  );

  it(
    "creates only one conversation when two submit events arrive concurrently",
    async () => {
      let finishCreate!: (conversation: {
        id: number;
        workspace_id: number;
        title: null;
        created_at: null;
        updated_at: null;
        archived_at: null;
      }) => void;
      mocks.createAssistantConversation.mockImplementation(
        () => new Promise((resolve) => {
          finishCreate = resolve;
        }),
      );

      render(
        <MascotChatPanel
          workspaceId={7}
          onClose={vi.fn()}
        />,
      );
      const input = await screen.findByRole(
        "textbox",
        { name: "Maskota mesaj yaz" },
      );
      await userEvent.setup().type(input, "Concurrent submission");
      const form = input.closest("form");
      expect(form).not.toBeNull();
      fireEvent.submit(form!);
      fireEvent.submit(form!);

      await waitFor(() => expect(
        mocks.createAssistantConversation,
      ).toHaveBeenCalledTimes(1));
      await act(async () => finishCreate({
        id: 107,
        workspace_id: 7,
        title: null,
        created_at: null,
        updated_at: null,
        archived_at: null,
      }));
      await waitFor(() => expect(mocks.streamRag).toHaveBeenCalledTimes(1));
    },
  );

  it(
    "uses only the newly selected workspace conversation after a workspace switch",
    async () => {
      const user = userEvent.setup();
      mocks.listAssistantConversations.mockImplementation(
        async (workspaceId: number) => ({
          items: [{
            id: workspaceId === 7 ? 42 : 84,
            workspace_id: workspaceId,
            title: null,
            created_at: null,
            updated_at: null,
            archived_at: null,
          }],
          total: 1,
          limit: 100,
          offset: 0,
        }),
      );
      mocks.getAssistantConversation.mockImplementation(
        async (id: number) => ({
          id,
          workspace_id: id === 42 ? 7 : 8,
          title: null,
          created_at: null,
          updated_at: null,
          archived_at: null,
          messages: [{
            id,
            role: "assistant",
            content: id === 42 ? "Workspace seven history" : "Workspace eight history",
            sources: [],
            created_at: null,
          }],
          message_total: 1,
          message_limit: 100,
          message_offset: 0,
        }),
      );

      const view = render(
        <MascotChatPanel
          workspaceId={7}
          onClose={vi.fn()}
        />,
      );
      expect(await screen.findByText("Workspace seven history"))
        .toBeInTheDocument();

      view.rerender(
        <MascotChatPanel
          workspaceId={8}
          onClose={vi.fn()}
        />,
      );
      expect(await screen.findByText("Workspace eight history"))
        .toBeInTheDocument();
      expect(screen.queryByText("Workspace seven history"))
        .not.toBeInTheDocument();

      const input = await screen.findByRole(
        "textbox",
        { name: "Maskota mesaj yaz" },
      );
      await user.type(input, "Question in workspace eight");
      await user.click(screen.getByRole(
        "button",
        { name: "Mesaj gönder" },
      ));

      await waitFor(() => expect(mocks.streamRag).toHaveBeenCalledTimes(1));
      expect(mocks.streamRag.mock.calls[0][0]).toEqual([99]);
      expect(mocks.streamRag.mock.calls[0][4])
        .toEqual({ conversationId: 84 });
    },
  );

  it(
    "ignores a stale conversation-list response from the previous workspace",
    async () => {
      let resolveOldList!: (value: {
        items: Array<{
          id: number;
          workspace_id: number;
          title: null;
          created_at: null;
          updated_at: null;
          archived_at: null;
        }>;
        total: number;
        limit: number;
        offset: number;
      }) => void;
      mocks.listAssistantConversations.mockImplementation(
        (workspaceId: number) => {
          if (workspaceId === 7) {
            return new Promise((resolve) => {
              resolveOldList = resolve;
            });
          }
          return Promise.resolve({
            items: [{
              id: 84,
              workspace_id: 8,
              title: null,
              created_at: null,
              updated_at: null,
              archived_at: null,
            }],
            total: 1,
            limit: 100,
            offset: 0,
          });
        },
      );
      mocks.getAssistantConversation.mockImplementation(
        async (id: number) => ({
          id,
          workspace_id: id === 42 ? 7 : 8,
          title: null,
          created_at: null,
          updated_at: null,
          archived_at: null,
          messages: [{
            id,
            role: "assistant",
            content: id === 42 ? "Stale workspace result" : "Current workspace result",
            sources: [],
            created_at: null,
          }],
          message_total: 1,
          message_limit: 100,
          message_offset: 0,
        }),
      );

      const view = render(
        <MascotChatPanel
          workspaceId={7}
          onClose={vi.fn()}
        />,
      );
      view.rerender(
        <MascotChatPanel
          workspaceId={8}
          onClose={vi.fn()}
        />,
      );
      expect(await screen.findByText("Current workspace result"))
        .toBeInTheDocument();

      await act(async () => {
        resolveOldList({
          items: [{
            id: 42,
            workspace_id: 7,
            title: null,
            created_at: null,
            updated_at: null,
            archived_at: null,
          }],
          total: 1,
          limit: 100,
          offset: 0,
        });
      });

      expect(mocks.getAssistantConversation)
        .toHaveBeenCalledTimes(1);
      expect(mocks.getAssistantConversation)
        .toHaveBeenCalledWith(84);
      expect(screen.queryByText("Stale workspace result"))
        .not.toBeInTheDocument();
      expect(screen.getByText("Current workspace result"))
        .toBeInTheDocument();
    },
  );

  it(
    "ignores a stale conversation-detail response after switching workspaces",
    async () => {
      let resolveOldDetail!: (detail: {
        id: number;
        workspace_id: number;
        title: null;
        created_at: null;
        updated_at: null;
        archived_at: null;
        messages: Array<{
          id: number;
          role: "assistant";
          content: string;
          sources: [];
          created_at: null;
        }>;
        message_total: number;
        message_limit: number;
        message_offset: number;
      }) => void;
      mocks.listAssistantConversations.mockImplementation(
        async (workspaceId: number) => ({
          items: [{
            id: workspaceId === 7 ? 42 : 84,
            workspace_id: workspaceId,
            title: null,
            created_at: null,
            updated_at: null,
            archived_at: null,
          }],
          total: 1,
          limit: 100,
          offset: 0,
        }),
      );
      mocks.getAssistantConversation.mockImplementation(
        (id: number) => id === 42
          ? new Promise((resolve) => {
              resolveOldDetail = resolve;
            })
          : Promise.resolve({
              id: 84,
              workspace_id: 8,
              title: null,
              created_at: null,
              updated_at: null,
              archived_at: null,
              messages: [{
                id: 84,
                role: "assistant" as const,
                content: "Current workspace detail",
                sources: [],
                created_at: null,
              }],
              message_total: 1,
              message_limit: 100,
              message_offset: 0,
            }),
      );

      const view = render(
        <MascotChatPanel
          workspaceId={7}
          onClose={vi.fn()}
        />,
      );
      await waitFor(() => expect(
        mocks.getAssistantConversation,
      ).toHaveBeenCalledWith(42));
      view.rerender(
        <MascotChatPanel
          workspaceId={8}
          onClose={vi.fn()}
        />,
      );
      expect(await screen.findByText("Current workspace detail"))
        .toBeInTheDocument();

      await act(async () => resolveOldDetail({
        id: 42,
        workspace_id: 7,
        title: null,
        created_at: null,
        updated_at: null,
        archived_at: null,
        messages: [{
          id: 42,
          role: "assistant",
          content: "Stale workspace detail",
          sources: [],
          created_at: null,
        }],
        message_total: 1,
        message_limit: 100,
        message_offset: 0,
      }));

      expect(screen.queryByText("Stale workspace detail"))
        .not.toBeInTheDocument();
      expect(screen.getByText("Current workspace detail"))
        .toBeInTheDocument();
    },
  );

  it(
    "aborts an active RAG stream when the workspace changes",
    async () => {
      const user = userEvent.setup();
      let activeSignal: AbortSignal | undefined;
      mocks.streamRag.mockImplementation(
        (
          _ids: number[],
          _question: string,
          _onEvent: (event: RagEvent) => void,
          signal?: AbortSignal,
        ) => {
          activeSignal = signal;
          return new Promise<void>((_resolve, reject) => {
            signal?.addEventListener("abort", () => {
              const error = new Error("aborted");
              error.name = "AbortError";
              reject(error);
            }, { once: true });
          });
        },
      );
      const view = render(
        <MascotChatPanel
          workspaceId={7}
          onClose={vi.fn()}
        />,
      );
      const input = await screen.findByRole(
        "textbox",
        { name: "Maskota mesaj yaz" },
      );
      await user.type(input, "Abort on workspace switch");
      await user.click(screen.getByRole("button", { name: "Mesaj gönder" }));
      await waitFor(() => expect(mocks.streamRag).toHaveBeenCalledTimes(1));

      view.rerender(
        <MascotChatPanel
          workspaceId={8}
          onClose={vi.fn()}
        />,
      );
      await waitFor(() => expect(activeSignal?.aborted).toBe(true));
    },
  );

  it(
    "shows RAG errors without fabricating an answer",
    async () => {
      const user = userEvent.setup();

      mocks.streamRag.mockImplementation(
        async (
          _ids: number[],
          _question: string,
          onEvent: (
            event: RagEvent,
          ) => void,
        ) => {
          onEvent({
            type: "error",
            data: "RAG request failed",
          });
        },
      );

      render(
        <MascotChatPanel
          workspaceId={7}
          onClose={vi.fn()}
        />,
      );

      const input =
        await screen.findByRole(
          "textbox",
          { name: "Maskota mesaj yaz" },
        );

      await user.type(input, "Test");

      await user.click(
        screen.getByRole(
          "button",
          { name: "Mesaj gönder" },
        ),
      );

      expect(
        await screen.findByRole("alert"),
      ).toHaveTextContent(
        "RAG request failed",
      );
    },
  );

  it(
    "disables RAG when the workspace has no knowledge base",
    async () => {
      mocks.listKnowledgeBases
        .mockResolvedValue([
          {
            id: 99,
            workspace_id: 8,
            name: "Other",
            slug: "other",
            description: null,
            membership_role: "user",
          },
        ]);

      render(
        <MascotChatPanel
          workspaceId={7}
          onClose={vi.fn()}
        />,
      );

      expect(
        await screen.findByText(
          "Bu Workspace'te KB yok",
        ),
      ).toBeInTheDocument();

      const input = screen.getByRole(
        "textbox",
        { name: "Maskota mesaj yaz" },
      );

      expect(input).toBeEnabled();

      await userEvent.setup().type(
        input,
        "Şirket politikamız nedir?",
      );

      await userEvent.setup().click(
        screen.getByRole(
          "button",
          { name: "Mesaj gönder" },
        ),
      );

      expect(
        await screen.findByText(
          /erişebildiğiniz bir Knowledge Base yok/i,
        ),
      ).toBeInTheDocument();

      expect(
        mocks.streamRag,
      ).not.toHaveBeenCalled();
    },
  );

  it(
    "does not silently truncate more than 20 sources",
    async () => {
      mocks.listKnowledgeBases
        .mockResolvedValue(
          Array.from(
            { length: 21 },
            (_, index) => ({
              id: index + 1,
              workspace_id: 7,
              name: `KB ${index + 1}`,
              slug: `kb-${index + 1}`,
              description: null,
              membership_role: "user",
            }),
          ),
        );

      render(
        <MascotChatPanel
          workspaceId={7}
          onClose={vi.fn()}
        />,
      );

      expect(
        await screen.findByText(
          "21 yetkili KB · RAG Chat'ten seçim gerekli",
        ),
      ).toBeInTheDocument();

      const input = screen.getByRole(
        "textbox",
        { name: "Maskota mesaj yaz" },
      );

      expect(input).toBeEnabled();

      await userEvent.setup().type(
        input,
        "Kurumsal kayıtları özetle",
      );

      await userEvent.setup().click(
        screen.getByRole(
          "button",
          { name: "Mesaj gönder" },
        ),
      );

      expect(
        await screen.findByText(
          /20'den fazla yetkili Knowledge Base var/i,
        ),
      ).toBeInTheDocument();

      expect(
        mocks.streamRag,
      ).not.toHaveBeenCalled();
    },
  );

  it(
    "aborts an in-flight answer",
    async () => {
      const user = userEvent.setup();

      let signal:
        | AbortSignal
        | undefined;

      mocks.streamRag.mockImplementation(
        (
          _ids: number[],
          _question: string,
          _onEvent: (
            event: RagEvent,
          ) => void,
          currentSignal?: AbortSignal,
        ) => {
          signal = currentSignal;

          return new Promise<void>(
            (_resolve, reject) => {
              currentSignal
                ?.addEventListener(
                  "abort",
                  () => {
                    const error =
                      new Error("aborted");

                    error.name =
                      "AbortError";

                    reject(error);
                  },
                  { once: true },
                );
            },
          );
        },
      );

      render(
        <MascotChatPanel
          workspaceId={7}
          onClose={vi.fn()}
        />,
      );

      const input =
        await screen.findByRole(
          "textbox",
          { name: "Maskota mesaj yaz" },
        );

      await user.type(
        input,
        "Uzun bir soru",
      );

      await user.click(
        screen.getByRole(
          "button",
          { name: "Mesaj gönder" },
        ),
      );

      await user.click(
        await screen.findByRole(
          "button",
          { name: "Yanıtı durdur" },
        ),
      );

      await waitFor(() => {
        expect(signal?.aborted).toBe(true);
      });

      expect(
        screen.queryByRole("alert"),
      ).not.toBeInTheDocument();
    },
  );

  it(
    "calls onClose from the close control",
    async () => {
      const user = userEvent.setup();
      const onClose = vi.fn();

      render(
        <MascotChatPanel
          workspaceId={7}
          onClose={onClose}
        />,
      );

      await user.click(
        screen.getByRole(
          "button",
          {
            name:
              "Maskot sohbetini kapat",
          },
        ),
      );

      expect(onClose)
        .toHaveBeenCalledTimes(1);
    },
  );
});
