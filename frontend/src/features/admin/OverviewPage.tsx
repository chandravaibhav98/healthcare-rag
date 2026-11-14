import { useMemo, useState } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip as ChartTooltip,
  XAxis,
  YAxis,
} from 'recharts';

import type { Stats } from '@/api/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { EmptyState, ErrorAlert, Skeleton } from '@/components/ui/feedback';
import { Label, Select } from '@/components/ui/input';
import { reasonText } from '@/features/assistant/reasons';
import { usePageTitle } from '@/hooks/usePageTitle';
import { formatDay, formatMs, formatPercent, formatScore } from '@/lib/format';

import { PageHeader } from './AdminLayout';
import { ChartFigure } from './ChartFigure';
import { CHART, CHART_PROPS, CHART_SIZE, TOOLTIP_PROPS } from './chartTheme';
import { useStats } from './queries';

const RANGES = [
  { days: 1, label: 'Last 24 hours' },
  { days: 7, label: 'Last 7 days' },
  { days: 30, label: 'Last 30 days' },
  { days: 90, label: 'Last 90 days' },
];

function Kpi({ label, value, testId }: { label: string; value: string; testId: string }) {
  return (
    <Card>
      <CardContent className="flex flex-col gap-1 pt-4">
        <span className="text-sm text-muted-foreground">{label}</span>
        <span className="text-2xl font-bold" data-testid={testId}>
          {value}
        </span>
      </CardContent>
    </Card>
  );
}

function windowFor(days: number): { from: string; to: string } {
  // Round up to the minute so the query key is stable across re-renders.
  const to = new Date(Math.ceil(Date.now() / 60_000) * 60_000);
  const from = new Date(to.getTime() - days * 86_400_000);
  return { from: from.toISOString(), to: to.toISOString() };
}

function TrendChart({ data }: { data: Stats }) {
  return (
    <ChartFigure
      title="Questions per day"
      description="Validated answers and abstentions (needs review)."
      columns={['Day', 'Validated', 'Needs review', 'Mean confidence']}
      rows={data.series.map((p) => [
        p.day,
        p.validated,
        p.needs_review,
        formatScore(p.mean_confidence),
      ])}
      testId="chart-trend"
    >
      <ResponsiveContainer initialDimension={CHART_SIZE}>
        <LineChart
          {...CHART_PROPS}
          data={data.series.map((p) => ({ ...p, label: formatDay(p.day) }))}
        >
          <CartesianGrid stroke={CHART.grid} strokeDasharray="3 3" />
          <XAxis dataKey="label" stroke={CHART.text} fontSize={12} />
          <YAxis allowDecimals={false} stroke={CHART.text} fontSize={12} />
          <ChartTooltip {...TOOLTIP_PROPS} />
          <Legend />
          <Line
            type="monotone"
            dataKey="validated"
            name="Validated"
            stroke={CHART.success}
            strokeWidth={2}
          />
          <Line
            type="monotone"
            dataKey="needs_review"
            name="Needs review"
            stroke={CHART.warning}
            strokeWidth={2}
            strokeDasharray="5 3"
          />
        </LineChart>
      </ResponsiveContainer>
    </ChartFigure>
  );
}

function ConfidenceChart({ data }: { data: Stats }) {
  return (
    <ChartFigure
      title="Confidence distribution"
      description="Answers per confidence band. The default threshold is 0.6."
      columns={['Band', 'Answers']}
      rows={data.confidence_histogram.map((b) => [
        `${b.lower.toFixed(1)}–${b.upper.toFixed(1)}`,
        b.count,
      ])}
      testId="chart-confidence"
    >
      <ResponsiveContainer initialDimension={CHART_SIZE}>
        <BarChart
          {...CHART_PROPS}
          data={data.confidence_histogram.map((b) => ({ ...b, band: b.lower.toFixed(1) }))}
        >
          <CartesianGrid stroke={CHART.grid} strokeDasharray="3 3" />
          <XAxis dataKey="band" stroke={CHART.text} fontSize={12} />
          <YAxis allowDecimals={false} stroke={CHART.text} fontSize={12} />
          <ChartTooltip {...TOOLTIP_PROPS} />
          <Bar dataKey="count" name="Answers" fill={CHART.primary} />
        </BarChart>
      </ResponsiveContainer>
    </ChartFigure>
  );
}

function TopTopics({ data }: { data: Stats }) {
  const max = data.top_topics[0]?.count ?? 1;
  return (
    <ol className="flex flex-col gap-2" data-testid="top-topics">
      {data.top_topics.map((t) => (
        <li key={t.topic} className="grid grid-cols-[10rem_1fr_3rem] items-center gap-2 text-sm">
          <span className="truncate">{t.topic}</span>
          <span
            aria-hidden
            className="h-2 rounded-full bg-primary"
            style={{ width: `${((t.count / max) * 100).toString()}%` }}
          />
          <span className="text-right font-mono">{t.count}</span>
        </li>
      ))}
    </ol>
  );
}

export function OverviewPage() {
  usePageTitle('Dashboard overview');
  const [days, setDays] = useState(7);
  const { from, to } = useMemo(() => windowFor(days), [days]);
  const stats = useStats(from, to);
  const data = stats.data;

  return (
    <div className="flex flex-col gap-4" data-testid="page-overview">
      <PageHeader
        title="Overview"
        description="How the assistant is answering: volume, validation and speed."
        actions={
          <div className="flex items-center gap-2">
            <Label htmlFor="range">Period</Label>
            <Select
              id="range"
              value={days}
              className="w-40"
              data-testid="range-select"
              onChange={(e) => {
                setDays(Number(e.target.value));
              }}
            >
              {RANGES.map((r) => (
                <option key={r.days} value={r.days}>
                  {r.label}
                </option>
              ))}
            </Select>
          </div>
        }
      />
      {stats.isError ? <ErrorAlert error={stats.error} title="Could not load statistics" /> : null}
      {stats.isPending ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
          {Array.from({ length: 5 }, (_, i) => (
            <Skeleton key={i} className="h-20" />
          ))}
        </div>
      ) : null}
      {data ? (
        <>
          <section
            aria-label="Key figures"
            className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5"
          >
            <Kpi label="Questions" value={data.total.toLocaleString()} testId="kpi-total" />
            <Kpi
              label="Pass rate (validated)"
              value={formatPercent(data.pass_rate)}
              testId="kpi-pass-rate"
            />
            <Kpi
              label="Mean confidence"
              value={formatScore(data.mean_confidence)}
              testId="kpi-confidence"
            />
            <Kpi
              label="Abstention rate"
              value={formatPercent(data.abstention_rate)}
              testId="kpi-abstention"
            />
            <Kpi label="p95 latency" value={formatMs(data.latency_p95_ms)} testId="kpi-p95" />
          </section>
          {data.total === 0 ? (
            <EmptyState title="No questions in this period">
              Ask something in the assistant, or run <code>scripts/seed.sh --demo</code>.
            </EmptyState>
          ) : (
            <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
              <Card>
                <CardContent className="pt-4">
                  <TrendChart data={data} />
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-4">
                  <ConfidenceChart data={data} />
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle>Top topics</CardTitle>
                </CardHeader>
                <CardContent>
                  <TopTopics data={data} />
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle>Why answers were withheld</CardTitle>
                </CardHeader>
                <CardContent>
                  {Object.keys(data.reasons).length === 0 ? (
                    <p className="text-sm text-muted-foreground">No abstentions in this period.</p>
                  ) : (
                    <dl className="flex flex-col gap-2 text-sm" data-testid="abstention-reasons">
                      {Object.entries(data.reasons).map(([reason, count]) => (
                        <div key={reason} className="flex justify-between gap-4">
                          <dt>{reasonText(reason)}</dt>
                          <dd className="font-mono">{count}</dd>
                        </div>
                      ))}
                    </dl>
                  )}
                </CardContent>
              </Card>
            </div>
          )}
        </>
      ) : null}
    </div>
  );
}
