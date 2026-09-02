/**
 * Typed fetch wrappers for the backend `/api` surface.
 *
 * Every call sends the auth cookie (`credentials: "include"`). Non-2xx responses
 * throw an {@link ApiError} carrying the status so callers can distinguish 401
 * (unauthenticated) from other failures. Mirrors `backend/app/routers/*`.
 */

import type {
  ChatMessageRequest,
  ChatMessageResponse,
  ConfigResponse,
  ConversationHistoryResponse,
  SessionResponse,
  SetupStatus,
  UploadDescriptor,
  User,
} from "./types";

const API_BASE = "/api";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body && typeof body.detail === "string") detail = body.detail;
    } catch {
      /* non-JSON error body — keep statusText */
    }
    throw new ApiError(res.status, detail);
  }
  // 204/empty bodies → undefined; callers that expect a body type won't hit this.
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  // --- setup (first-run wizard) ---
  /** GET /api/setup/status — unauthenticated; true until the first admin exists. */
  setupStatus(): Promise<SetupStatus> {
    return request<SetupStatus>("/setup/status");
  },

  /** POST /api/setup/bootstrap — creates the first admin account and logs it in
   * (sets the session cookie, same as login). Throws ApiError(409) if setup has
   * already been completed. */
  async bootstrap(username: string, password: string): Promise<User> {
    const body = await request<{ user: User }>("/setup/bootstrap", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    return body.user;
  },

  // --- auth ---
  async login(username: string, password: string): Promise<User> {
    const body = await request<{ user: User }>("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    return body.user;
  },

  logout(): Promise<void> {
    return request<void>("/auth/logout", { method: "POST" });
  },

  /** GET /api/auth/me — resolves to the user, or throws ApiError(401) if not authed. */
  me(): Promise<User> {
    return request<User>("/auth/me");
  },

  // --- config / session ---
  getConfig(): Promise<ConfigResponse> {
    return request<ConfigResponse>("/config");
  },

  createSession(profile?: string): Promise<SessionResponse> {
    return request<SessionResponse>("/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(profile ? { profile } : {}),
    });
  },

  // --- chat turn ---
  sendMessage(body: ChatMessageRequest): Promise<ChatMessageResponse> {
    return request<ChatMessageResponse>("/chat/messages", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  },

  // --- uploads ---
  uploadFile(file: File): Promise<UploadDescriptor> {
    const form = new FormData();
    form.append("file", file, file.name);
    return request<UploadDescriptor>("/uploads", { method: "POST", body: form });
  },

  // --- history ---
  getRecentConversations(limit = 20): Promise<ConversationHistoryResponse> {
    return request<ConversationHistoryResponse>(`/conversations/recent?limit=${limit}`);
  },

  /** URL for an artifact's bytes; used directly as an <img>/<embed> src or fetch target. */
  artifactContentUrl(artifactId: string): string {
    return `${API_BASE}/artifacts/${encodeURIComponent(artifactId)}/content`;
  },
};
