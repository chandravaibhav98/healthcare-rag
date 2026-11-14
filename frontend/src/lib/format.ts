const percentFormat = new Intl.NumberFormat(undefined, {
  style: 'percent',
  maximumFractionDigits: 1,
});
const dateTimeFormat = new Intl.DateTimeFormat(undefined, {
  dateStyle: 'medium',
  timeStyle: 'short',
});
const dayFormat = new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric' });

export function formatPercent(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : percentFormat.format(value);
}

export function formatScore(value: number | null | undefined, digits = 2): string {
  return value === null || value === undefined ? '—' : value.toFixed(digits);
}

export function formatMs(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return value < 10 ? `${value.toFixed(1)} ms` : `${Math.round(value).toString()} ms`;
}

export function formatDateTime(iso: string | null | undefined): string {
  return iso ? dateTimeFormat.format(new Date(iso)) : '—';
}

export function formatDay(iso: string): string {
  return dayFormat.format(new Date(iso));
}

export function shortHash(hash: string | null | undefined, length = 12): string {
  return hash ? hash.slice(0, length) : '—';
}
