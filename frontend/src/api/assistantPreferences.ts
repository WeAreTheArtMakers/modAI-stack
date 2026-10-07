import { request } from "./client";

export type AssistantLanguage = "auto" | "en" | "tr";
export type AssistantTone = "professional" | "friendly" | "technical" | "concise";
export type AssistantResponseLength = "short" | "balanced" | "detailed";

export interface AssistantPreferences {
  assistant_name: string;
  language: AssistantLanguage;
  tone: AssistantTone;
  response_length: AssistantResponseLength;
  updated_at: string | null;
}

export type AssistantPreferencesUpdate = Omit<AssistantPreferences, "updated_at">;

export const DEFAULT_ASSISTANT_PREFERENCES: AssistantPreferences = {
  assistant_name: "modAI",
  language: "auto",
  tone: "professional",
  response_length: "balanced",
  updated_at: null,
};

export function getAssistantPreferences(): Promise<AssistantPreferences> {
  return request<AssistantPreferences>("/assistant/preferences");
}

export function updateAssistantPreferences(
  preferences: AssistantPreferencesUpdate,
): Promise<AssistantPreferences> {
  return request<AssistantPreferences>("/assistant/preferences", {
    method: "PUT",
    body: JSON.stringify(preferences),
  });
}
