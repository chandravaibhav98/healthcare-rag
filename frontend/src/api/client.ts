/**
 * Typed API client: `openapi-fetch` over types generated from backend/openapi.json
 * (`scripts/gen-client.*`), so a contract change fails `tsc` instead of failing in
 * production. Middleware adds the bearer token and, on a 401, refreshes the session
 * once (single flight) and retries the request.
 */
import createClient, { type Middleware } from 'openapi-fetch';

import type { paths } from './generated/schema';
import { clearSession, getAccessToken, setSession } from './session';
import type { ProblemDetails, TokenResponse } from './types';

/** Empty = same origin (Vite proxy in development, nginx in Phase 8). */
function baseUrl(): string {
  const configured: unknown = import.meta.env.VITE_API_BASE_URL;
  if (typeof configured === 'string' && configured !== '') return configured.replace(/\/$/, '');
  return window.location.origin;
}

export class ApiError extends Error {
  readonly status: number;
  readonly problem: ProblemDetails | null;
  readonly requestId: string | null;

  constructor(status: number, problem: ProblemDetails | null) {
    super(problem?.detail ?? problem?.title ?? `Request failed (${status.toString()})`);
    this.name = 'ApiError';
    this.status = status;
    this.problem = problem;
    this.requestId = problem?.request_id ?? null;
  }
}

const AUTH_PATHS = ['/api/v1/auth/login', '/api/v1/auth/refresh', '/api/v1/auth/logout'];
const pendingRetries = new Map<string, Request>();
let refreshInFlight: Promise<boolean> | null = null;

/** Exchange the refresh cookie for a new access token. Concurrent callers share one call. */
export function refreshSession(): Promise<boolean> {
  refreshInFlight ??= (async () => {
    try {
      const response = await globalThis.fetch(`${baseUrl()}/api/v1/auth/refresh`, {
        method: 'POST',
        credentials: 'same-origin',
      });
      if (!response.ok) {
        clearSession();
        return false;
      }
      setSession((await response.json()) as TokenResponse);
      return true;
    } catch {
      clearSession();
      return false;
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

const authMiddleware: Middleware = {
  onRequest({ request, id }) {
    const token = getAccessToken();
    if (token) request.headers.set('Authorization', `Bearer ${token}`);
    if (!AUTH_PATHS.some((path) => request.url.includes(path))) {
      pendingRetries.set(id, request.clone()); // a body can be read only once
    }
    return request;
  },
  async onResponse({ response, id }) {
    const original = pendingRetries.get(id);
    pendingRetries.delete(id);
    if (response.status !== 401 || !original || !getAccessToken()) return response;
    if (!(await refreshSession())) return response;
    const retry = new Request(original);
    retry.headers.set('Authorization', `Bearer ${getAccessToken() ?? ''}`);
    return globalThis.fetch(retry);
  },
  onError({ id }) {
    pendingRetries.delete(id);
  },
};

export const api = createClient<paths>({
  baseUrl: baseUrl(),
  credentials: 'same-origin',
  // Look `fetch` up at call time so test doubles installed later are used.
  fetch: (input: Request) => globalThis.fetch(input),
});
api.use(authMiddleware);

/** Unwrap an openapi-fetch result: return data or throw an ApiError with the problem body. */
export async function unwrap<T>(
  promise: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const { data, error, response } = await promise;
  if (response.ok && data !== undefined) return data;
  if (response.ok && response.status === 204) return undefined as T;
  throw new ApiError(response.status, isProblem(error) ? error : null);
}

function isProblem(value: unknown): value is ProblemDetails {
  return typeof value === 'object' && value !== null && 'status' in value && 'title' in value;
}
