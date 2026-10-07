import type {
  AssistantConversationDetail,
  AssistantConversationList,
  AssistantConversationSummary,
} from "../types";
import { request } from "./client";

export function listAssistantConversations(
  workspaceId: number,
): Promise<AssistantConversationList> {
  const search = new URLSearchParams({
    workspace_id: String(workspaceId),
    include_archived: "false",
    limit: "100",
    offset: "0",
  });
  return request<AssistantConversationList>(
    `/assistant/conversations?${search.toString()}`,
  );
}

export function createAssistantConversation(
  workspaceId: number,
): Promise<AssistantConversationSummary> {
  return request<AssistantConversationSummary>(
    "/assistant/conversations",
    {
      method: "POST",
      body: JSON.stringify({ workspace_id: workspaceId }),
    },
  );
}

export function getAssistantConversation(
  conversationId: number,
): Promise<AssistantConversationDetail> {
  const page = (offset: number) => {
    const search = new URLSearchParams({
      message_limit: "100",
      message_offset: String(offset),
    });
    return request<AssistantConversationDetail>(
      `/assistant/conversations/${conversationId}?${search.toString()}`,
    );
  };

  return page(0).then(async (latest) => {
    const olderPages: AssistantConversationDetail[] = [];
    for (let offset = latest.message_limit; offset < latest.message_total; offset += latest.message_limit) {
      olderPages.push(await page(offset));
    }
    return {
      ...latest,
      messages: [
        ...olderPages.reverse().flatMap((older) => older.messages),
        ...latest.messages,
      ],
    };
  });
}
