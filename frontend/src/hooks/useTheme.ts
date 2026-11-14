import { useCallback, useEffect, useState } from 'react';

import { readJson, writeJson } from '@/lib/storage';

export type Theme = 'light' | 'dark';
const KEY = 'hcrag.theme';

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

export function applyTheme(theme: Theme): void {
  document.documentElement.classList.toggle('dark', theme === 'dark');
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
