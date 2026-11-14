/** Chart colours readable on both themes (≥ 3:1 against the card background). */
export const CHART = {
  primary: 'var(--primary)',
  success: 'var(--success)',
  warning: 'var(--warning)',
  grid: 'var(--border)',
  text: 'var(--muted-foreground)',
} as const;

/** First-render size before the container is measured (also used in jsdom tests). */
export const CHART_SIZE = { width: 560, height: 224 } as const;

/**
 * Shared chart props. Charts sit inside an aria-hidden wrapper (the data is offered as a
 * table), so Recharts' keyboard layer is switched off: hidden content must not take focus.
 */
export const CHART_PROPS = { accessibilityLayer: false } as const;

/** Tooltip styled with the theme tokens, so it stays readable in dark mode. */
export const TOOLTIP_PROPS = {
  contentStyle: {
    background: 'var(--card)',
    border: '1px solid var(--border)',
    borderRadius: 6,
    color: 'var(--foreground)',
  },
  labelStyle: { color: 'var(--foreground)', fontWeight: 600 },
  itemStyle: { color: 'var(--foreground)' },
} as const;
