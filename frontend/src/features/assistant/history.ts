import { readJson, remove, writeJson } from '@/lib/storage';

import type { QAResponse } from '@/api/types';

/** Answers asked in this browser tab (sessionStorage: gone when the tab closes). */
export interface HistoryEntry {
  id: string;
  question: string;
  topK: number;
  askedAt: string;
  response: QAResponse;
}

const KEY = 'hcrag.history';
export const HISTORY_LIMIT = 20;

export function loadHistory(): HistoryEntry[] {
  const value = readJson<unknown>('session', KEY, []);
  return Array.isArray(value) ? (value as HistoryEntry[]) : [];
}

export function saveHistory(entries: HistoryEntry[]): void {
  writeJson('session', KEY, entries.slice(0, HISTORY_LIMIT));
}

export function clearHistory(): void {
  remove('session', KEY);
}
