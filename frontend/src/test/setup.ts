import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterAll, afterEach, beforeAll, vi } from 'vitest';

import { clearSession } from '@/api/session';

import { server } from './server';

// jsdom gaps used by Radix (ResizeObserver, pointer capture) and Recharts.
class ResizeObserverStub {
  observe(): void {
    // jsdom has no layout; nothing to observe
  }
  unobserve(): void {
    // nothing to release
  }
  disconnect(): void {
    // nothing to release
  }
}
function define(target: object, key: string, value: unknown): void {
  if (!(key in target))
    Object.defineProperty(target, key, { value, configurable: true, writable: true });
}
define(globalThis, 'ResizeObserver', ResizeObserverStub);
define(window, 'matchMedia', (query: string) => ({
  matches: false,
  media: query,
  onchange: null,
  addListener: vi.fn(),
  removeListener: vi.fn(),
  addEventListener: vi.fn(),
  removeEventListener: vi.fn(),
  dispatchEvent: vi.fn(),
}));
define(Element.prototype, 'scrollIntoView', vi.fn());
define(Element.prototype, 'hasPointerCapture', () => false);
define(Element.prototype, 'releasePointerCapture', vi.fn());

// jsdom has no layout, so Recharts warns that charts measure 0×0. That is expected here;
// any other warning still reaches the output.
const warn = console.warn.bind(console);
console.warn = (...args: unknown[]) => {
  if (typeof args[0] === 'string' && args[0].includes('of chart should be greater than 0')) return;
  warn(...args);
};

beforeAll(() => {
  server.listen({ onUnhandledFrame: 'error' });
});
afterEach(() => {
  cleanup();
  server.resetHandlers();
  clearSession();
  sessionStorage.clear();
  localStorage.clear();
});
afterAll(() => {
  server.close();
});
