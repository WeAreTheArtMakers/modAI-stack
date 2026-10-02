const API_PREFIX = import.meta.env.VITE_API_PREFIX ?? "/api";
const ACCESS_KEY = "modai.access_token";
type AuthFailureListener = () => void;
const authFailureListeners = new Set<AuthFailureListener>();

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export const tokenStore = {
  get access() {
    return localStorage.getItem(ACCESS_KEY);
  },
  get refresh() {
    return null;
  },
  set(access: string) {
    localStorage.setItem(ACCESS_KEY, access);
  },
  clear() {
    localStorage.removeItem(ACCESS_KEY);
  },
};

export function onAuthFailure(listener: AuthFailureListener): () => void {
  authFailureListeners.add(listener);
  return () => authFailureListeners.delete(listener);
}

function clearSessionAfterAuthFailure(): void {
  tokenStore.clear();
  authFailureListeners.forEach((listener) => listener());
}

function readableError(status: number, detail?: string): string {
  if (detail) return detail;
  const messages: Record<number, string> = {
    401: "Oturumunuz sona erdi. Lütfen yeniden giriş yapın.",
    403: "Bu işlem için yetkiniz bulunmuyor.",
    404: "İstenen kayıt bulunamadı.",
    409: "Bu işlem mevcut verilerle çakışıyor.",
    422: "Gönderilen bilgiler doğrulanamadı.",
    500: "Sunucuda beklenmeyen bir hata oluştu.",
    503: "Servis şu anda kullanılamıyor.",
  };
  return messages[status] ?? "İstek tamamlanamadı.";
}

async function refreshAccessToken(): Promise<boolean> {
  const response = await fetch(`${API_PREFIX}/auth/refresh`, {
    method: "POST",
    credentials: "same-origin",
  });
  if (!response.ok) {
    clearSessionAfterAuthFailure();
    return false;
  }
  const tokens = (await response.json()) as { access_token: string };
  tokenStore.set(tokens.access_token);
  return true;
}

export async function request<T>(
  path: string,
  options: Parameters<typeof fetch>[1] = {},
  allowRefresh = true,
): Promise<T> {
  const headers = new Headers(options.headers);
  if (!headers.has("Content-Type") && options.body && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const access = tokenStore.access;
  if (access) headers.set("Authorization", `Bearer ${access}`);

  const response = await fetch(`${API_PREFIX}${path}`, { ...options, headers, credentials: "same-origin" });
  if (response.status === 401 && allowRefresh && path !== "/auth/refresh" && (await refreshAccessToken())) {
    return request<T>(path, options, false);
  }
  if (!response.ok) {
    let detail: string | undefined;
    try {
      const body = (await response.json()) as { detail?: string };
      detail = body.detail;
    } catch {
      // The response may not contain JSON.
    }
    throw new ApiError(response.status, readableError(response.status, detail));
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function websocketUrl(path: string): string {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}${path}`;
}

export function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Beklenmeyen bir hata oluştu.";
}
