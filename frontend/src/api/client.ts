const API_PREFIX = import.meta.env.VITE_API_PREFIX ?? "/api";
const ACCESS_KEY = "modai.access_token";
const REFRESH_KEY = "modai.refresh_token";

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
    return localStorage.getItem(REFRESH_KEY);
  },
  set(access: string, refresh: string) {
    localStorage.setItem(ACCESS_KEY, access);
    localStorage.setItem(REFRESH_KEY, refresh);
  },
  clear() {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },
};

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
  const refresh = tokenStore.refresh;
  if (!refresh) return false;
  const response = await fetch(`${API_PREFIX}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refresh }),
  });
  if (!response.ok) {
    tokenStore.clear();
    return false;
  }
  const tokens = (await response.json()) as { access_token: string; refresh_token: string };
  tokenStore.set(tokens.access_token, tokens.refresh_token);
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

  const response = await fetch(`${API_PREFIX}${path}`, { ...options, headers });
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
