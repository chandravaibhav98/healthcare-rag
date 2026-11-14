import { CheckCircle2, ShieldAlert } from 'lucide-react';
import { useId } from 'react';

import type { QAResponse, Signals } from '@/api/types';
import { cn } from '@/lib/cn';
import { formatScore } from '@/lib/format';

import { Badge } from './badge';
import { Tooltip } from './tooltip';

export function StatusBadge({ status }: { status: QAResponse['status'] }) {
  return status === 'validated' ? (
    <Badge tone="success" data-testid="status-badge">
      <CheckCircle2 aria-hidden className="size-3.5" />
      Validated
    </Badge>
  ) : (
    <Badge tone="warning" data-testid="status-badge">
      <ShieldAlert aria-hidden className="size-3.5" />
      Needs review
    </Badge>
  );
}

const SIGNAL_LABELS: Record<keyof Omit<Signals, 'numeric_ok'>, string> = {
  query_support: 'Query support: the question’s key terms found in the cited evidence',
  coverage: 'Coverage: answer words that come from the cited evidence',
  retrieval_score: 'Retrieval: how strongly the evidence matched the question',
};

/** Confidence as a labelled meter, with the evidence signals behind it in a tooltip. */
export function ConfidenceMeter({
  confidence,
  threshold,
  signals,
}: {
  confidence: number;
  threshold?: number;
  signals?: Signals | undefined;
}) {
  const labelId = useId();
  const pct = Math.round(confidence * 100);
  const passes = threshold === undefined || confidence >= threshold;
  const meter = (
    <div
      className="flex min-w-48 flex-col gap-1"
      data-testid="confidence-meter"
      tabIndex={signals ? 0 : undefined}
      aria-label={signals ? `Confidence ${pct.toString()}%. Show signal breakdown` : undefined}
    >
      <div className="flex justify-between text-xs">
        <span id={labelId} className="font-medium">
          Confidence
        </span>
        <span>{pct}%</span>
      </div>
      <div
        role="meter"
        aria-labelledby={labelId}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct}
        className="relative h-2.5 w-full overflow-hidden rounded-full bg-muted"
      >
        <div
          className={cn('h-full rounded-full', passes ? 'bg-success' : 'bg-warning')}
          style={{ width: `${pct.toString()}%` }}
        />
        {threshold !== undefined ? (
          <div
            aria-hidden
            className="absolute inset-y-0 w-0.5 bg-foreground"
            style={{ left: `${(threshold * 100).toString()}%` }}
          />
        ) : null}
      </div>
    </div>
  );
  if (!signals) return meter;
  return (
    <Tooltip
      content={
        <dl className="grid grid-cols-[1fr_auto] gap-x-3 gap-y-1" data-testid="signal-breakdown">
          {(Object.keys(SIGNAL_LABELS) as (keyof typeof SIGNAL_LABELS)[]).map((key) => (
            <div key={key} className="contents">
              <dt>{SIGNAL_LABELS[key]}</dt>
              <dd className="font-mono">{formatScore(signals[key])}</dd>
            </div>
          ))}
          <dt>Numbers match the evidence</dt>
          <dd>{signals.numeric_ok ? 'yes' : 'no'}</dd>
        </dl>
      }
    >
      {meter}
    </Tooltip>
  );
}
