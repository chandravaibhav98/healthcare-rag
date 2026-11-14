import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import { tokens } from '@/test/fixtures';
import { server } from '@/test/server';

import { api, ApiError, unwrap } from './client';
import { clearSession, getAccessToken, getUser, hasSessionHint, setSession } from './session';

describe('api client', () => {
  it('sends the bearer token', async () => {
    setSession(tokens('admin'));
    let seen: string | null = null;
    server.use(
      http.get('*/api/v1/auth/me', ({ request }) => {
        seen = request.headers.get('authorization');
        return HttpResponse.json(tokens('admin').user);
      }),
    );
    await unwrap(api.GET('/api/v1/auth/me'));
    expect(seen).toBe('Bearer token-admin');
  });

  it('refreshes once on 401 and retries the request with the new token', async () => {
    setSession({ ...tokens('reviewer'), access_token: 'expired' });
    let refreshes = 0;
    server.use(
      http.post('*/api/v1/auth/refresh', () => {
        refreshes += 1;
        return HttpResponse.json({ ...tokens('reviewer'), access_token: 'fresh' });
      }),
      http.get('*/api/v1/admin/config', ({ request }) =>
        request.headers.get('authorization') === 'Bearer fresh'
          ? HttpResponse.json({ ok: true })
          : HttpResponse.json({ title: 'Unauthorized', status: 401 }, { status: 401 }),
      ),
    );
    await expect(unwrap(api.GET('/api/v1/admin/config'))).resolves.toEqual({ ok: true });
    expect(refreshes).toBe(1);
    expect(getAccessToken()).toBe('fresh');
  });

  it('signs the user out when the refresh fails', async () => {
    setSession({ ...tokens('reviewer'), access_token: 'expired' });
    server.use(
      http.get('*/api/v1/admin/config', () =>
        HttpResponse.json({ title: 'Unauthorized', status: 401 }, { status: 401 }),
      ),
    );
    await expect(unwrap(api.GET('/api/v1/admin/config'))).rejects.toBeInstanceOf(ApiError);
    expect(getUser()).toBeNull();
  });

  it('exposes problem details and the request id on errors', async () => {
    server.use(
      http.post('*/api/v1/qa', () =>
        HttpResponse.json(
          { title: 'Too Many Requests', status: 429, detail: 'Slow down.', request_id: 'abc' },
          { status: 429 },
        ),
      ),
    );
    const error = await unwrap(
      api.POST('/api/v1/qa', { body: { question: 'x?', top_k: 5 } }),
    ).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(429);
    expect((error as ApiError).requestId).toBe('abc');
    expect((error as ApiError).message).toBe('Slow down.');
  });

  it('keeps only a non-secret "signed in" hint in storage', () => {
    setSession(tokens('admin'));
    expect(hasSessionHint()).toBe(true);
    expect(JSON.stringify(localStorage)).not.toContain('token-admin');
    expect(JSON.stringify(sessionStorage)).not.toContain('token-admin');
    clearSession();
    expect(hasSessionHint()).toBe(false);
  });
});
