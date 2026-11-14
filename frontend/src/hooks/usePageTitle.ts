import { useEffect } from 'react';

const APP = 'Healthcare Guidelines RAG Assistant';

/** Unique page titles help screen-reader and tab users know where they are (WCAG 2.4.2). */
export function usePageTitle(title: string): void {
  useEffect(() => {
    document.title = `${title} · ${APP}`;
  }, [title]);
}
