import { useCallback, useEffect, useState } from 'react';

import { readJson, writeJson } from '@/lib/storage';

export type Theme = 'light' | 'dark';
const KEY = 'hcrag.theme';
const SWITCHING_CLASS = 'theme-switching';

function systemTheme(): Theme {
  try {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  } catch {
    return 'light';
  }
}

export function initialTheme(): Theme {
  const stored = readJson<Theme | null>('local', KEY, null);
  return stored ?? systemTheme();
}

/**
 * Apply a theme instantly.
 *
 * Without suppression, every `transition-colors` element fades between palettes for
 * ~150 ms and passes through low-contrast blends (a WCAG 1.4.3 dip users can see).
 * We disable transitions, swap the class, force a style flush so the new colours are
 * committed while transitions are off, then re-enable them on the next task.
 */
export function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  const isDark = theme === 'dark';
  if (root.classList.contains('dark') === isDark) return; // nothing to change

  root.classList.add(SWITCHING_CLASS);
  root.classList.toggle('dark', isDark);
  // Reading a computed value makes the browser recalculate styles right now, so the new
  // palette takes effect while transitions are still switched off.
  window.getComputedStyle(document.body).getPropertyValue('color');
  window.setTimeout(() => {
    root.classList.remove(SWITCHING_CLASS);
  }, 0);
}

export function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(initialTheme);
  useEffect(() => {
    applyTheme(theme);
  }, [theme]);
  const toggle = useCallback(() => {
    setTheme((current) => {
      const next = current === 'dark' ? 'light' : 'dark';
      writeJson('local', KEY, next);
      return next;
    });
  }, []);
  return [theme, toggle];
}
