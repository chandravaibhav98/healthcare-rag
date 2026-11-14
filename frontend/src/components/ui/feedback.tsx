import { AlertTriangle, Info, Loader2 } from 'lucide-react';
import type { ReactNode } from 'react';

import { ApiError } from '@/api/client';
import { cn } from '@/lib/cn';

export function Spinner({ label = 'Loading' }: { label?: string }) {
  return (
    <span role="status" className="inline-flex items-center gap-2 text-sm text-muted-foreground">
      <Loader2 aria-hidden className="size-4 animate-spin" />
      {label}…
    </span>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cn('animate-pulse rounded-md bg-muted', className)} />;
}

export function Alert({
  tone = 'info',
  title,
  children,
  testId,
}: {
  tone?: 'info' | 'warning' | 'danger';
  title: string;
  children?: ReactNode;
  testId?: string;
}) {
  const Icon = tone === 'info' ? Info : AlertTriangle;
  return (
    <div
      role={tone === 'danger' ? 'alert' : 'status'}
      data-testid={testId}
      className={cn(
        'flex gap-3 rounded-md border p-3 text-sm',
        tone === 'info' && 'border-border bg-muted',
        tone === 'warning' && 'border-transparent bg-warning-bg text-warning',
        tone === 'danger' && 'border-transparent bg-danger-bg text-danger',
      )}
    >
      <Icon aria-hidden className="mt-0.5 size-4 shrink-0" />
      <div className="flex flex-col gap-1">
        <p className="font-semibold">{title}</p>
        {children ? <div>{children}</div> : null}
      </div>
    </div>
  );
}

/** Uniform rendering of a failed request, including the request ID for support. */
export function ErrorAlert({
  error,
  title = 'Something went wrong',
}: {
  error: unknown;
  title?: string;
}) {
  const message = error instanceof Error ? error.message : 'Unexpected error.';
  const requestId = error instanceof ApiError ? error.requestId : null;
  return (
    <Alert tone="danger" title={title} testId="error-alert">
      <p>{message}</p>
      {requestId ? <p className="text-xs">Reference: {requestId}</p> : null}
    </Alert>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div
      data-testid="empty-state"
      className="flex flex-col items-center gap-1 rounded-md border border-dashed border-border p-8 text-center"
    >
      <p className="font-medium">{title}</p>
      {children ? <div className="text-sm text-muted-foreground">{children}</div> : null}
    </div>
  );
}
