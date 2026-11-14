/**
 * In-memory session (ADR-0008): the access token never touches Web Storage, so an XSS
 * bug cannot read it from disk-backed storage. The refresh token is an httpOnly cookie
 * scoped to /api/v1/auth that only the server can read; reloading the page restores the
 * session by calling /auth/refresh once.
 */
import { readJson, remove, writeJson } from '@/lib/storage';

import type { TokenResponse, User } from './types';

type Listener = (user: User | null) => void;

/** A non-secret hint that a refresh cookie probably exists, so anonymous visitors do not
 * trigger a (failing, 401) refresh call on every page load. */
const HINT = 'hcrag.signedIn';

export function hasSessionHint(): boolean {
  return readJson<boolean>('local', HINT, false);
}

let accessToken: string | null = null;
let currentUser: User | null = null;
const listeners = new Set<Listener>();

export function getAccessToken(): string | null {
  return accessToken;
}

export function getUser(): User | null {
  return currentUser;
}

export function setSession(tokens: Pick<TokenResponse, 'access_token' | 'user'>): void {
  accessToken = tokens.access_token;
  currentUser = tokens.user;
  writeJson('local', HINT, true);
  for (const listener of listeners) listener(currentUser);
}

export function clearSession(): void {
  accessToken = null;
  currentUser = null;
  remove('local', HINT);
  for (const listener of listeners) listener(null);
}

export function subscribe(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
