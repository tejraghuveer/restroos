import type { SessionOut } from "./types";

const API_BASE = import.meta.env.VITE_API_URL ?? "/api/v1";

export interface ProblemDetail {
  type?: string;
  title?: string;
  status?: number;
  detail?: string;
  code?: string;
  instance?: string;
  errors?: { field: string; message: string; type: string }[];
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly problem: ProblemDetail;

  constructor(status: number, problem: ProblemDetail) {
    super(problem.detail ?? problem.title ?? "Request failed");
    this.name = "ApiError";
    this.status = status;
    this.code = problem.code ?? "request_failed";
    this.problem = problem;
  }

  fieldErrors(): Record<string, string> {
    const result: Record<string, string> = {};
    for (const error of this.problem.errors ?? []) {
      if (error.field && !result[error.field]) result[error.field] = error.message;
    }
    return result;
  }
}

export const AUTH_EXPIRED_EVENT = "restroos:auth-expired";

type RequestOptions = Omit<RequestInit, "body"> & {
  body?: unknown;
  skipRefresh?: boolean;
};

function buildProblem(status: number, fallback: string, payload: unknown): ProblemDetail {
  if (payload && typeof payload === "object") {
    return payload as ProblemDetail;
  }
  return { status, detail: fallback, code: "request_failed" };
}

class ApiClient {
  private token: string | null = null;

  setToken(token: string | null) {
    this.token = token;
  }

  getToken() {
    return this.token;
  }

  private headers(options: RequestOptions): Headers {
    const headers = new Headers(options.headers);
    if (options.body !== undefined) headers.set("Content-Type", "application/json");
    if (this.token) headers.set("Authorization", `Bearer ${this.token}`);
    return headers;
  }

  private async parse<T>(response: Response): Promise<T> {
    if (response.status === 204) return undefined as T;
    const text = await response.text();
    const payload = text ? JSON.parse(text) : null;
    if (!response.ok) {
      throw new ApiError(
        response.status,
        buildProblem(response.status, response.statusText, payload),
      );
    }
    return payload as T;
  }

  private async rawRefresh(): Promise<SessionOut | null> {
    // The refresh token lives in an HttpOnly cookie scoped to /api/v1/auth.
    const response = await fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      credentials: "include",
    });
    if (!response.ok) return null;
    return (await response.json()) as SessionOut;
  }

  async refreshSession(): Promise<SessionOut | null> {
    const session = await this.rawRefresh();
    if (session) this.setToken(session.access_token);
    return session;
  }

  async request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    const { body, skipRefresh, ...init } = options;
    const send = () =>
      fetch(`${API_BASE}${path}`, {
        ...init,
        credentials: "include",
        headers: this.headers(options),
        body: body === undefined ? undefined : JSON.stringify(body),
      });

    let response = await send();

    if (response.status === 401 && !skipRefresh) {
      const session = await this.refreshSession();
      if (session) {
        response = await send();
      } else {
        this.setToken(null);
        window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
      }
    }

    return this.parse<T>(response);
  }

  get<T>(path: string, options: RequestOptions = {}) {
    return this.request<T>(path, { ...options, method: "GET" });
  }

  post<T>(path: string, body?: unknown, options: RequestOptions = {}) {
    return this.request<T>(path, { ...options, method: "POST", body });
  }

  patch<T>(path: string, body?: unknown, options: RequestOptions = {}) {
    return this.request<T>(path, { ...options, method: "PATCH", body });
  }

  delete<T = void>(path: string, options: RequestOptions = {}) {
    return this.request<T>(path, { ...options, method: "DELETE" });
  }
}

export const api = new ApiClient();
