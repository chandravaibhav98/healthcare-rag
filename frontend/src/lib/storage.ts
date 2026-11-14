/**
 * Browser storage that never throws: storage can be disabled, full, or unavailable
 * (private modes, sandboxed frames). Callers get the fallback instead of a crash.
 * Nothing sensitive is stored here: tokens live in memory (access) and in an httpOnly
 * cookie (refresh), never in Web Storage (ADR-0008).
 */
type Area = 'local' | 'session';

function area(kind: Area): Storage | null {
  try {
    return kind === 'local' ? window.localStorage : window.sessionStorage;
  } catch {
    return null;
  }
}

export function readJson<T>(kind: Area, key: string, fallback: T): T {
  try {
    const raw = area(kind)?.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

export function writeJson(kind: Area, key: string, value: unknown): void {
  try {
    area(kind)?.setItem(key, JSON.stringify(value));
  } catch {
    // Storage full or disabled: the feature degrades to in-memory only.
  }
}

export function remove(kind: Area, key: string): void {
  try {
    area(kind)?.removeItem(key);
  } catch {
    // ignore
  }
}
