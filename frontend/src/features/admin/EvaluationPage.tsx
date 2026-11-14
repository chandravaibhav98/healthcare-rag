import { Play } from 'lucide-react';
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip as ChartTooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { EmptyState, ErrorAlert, Spinner } from '@/components/ui/feedback';
import { Table, TBody, Td, Th, THead } from '@/components/ui/table';
import { useAuth } from '@/features/auth/useAuth';
import { usePageTitle } from '@/hooks/usePageTitle';
import { formatDateTime, formatPercent, formatScore } from '@/lib/format';

import { PageHeader } from './AdminLayout';
import { ChartFigure } from './ChartFigure';
import { CHART, CHART_PROPS, CHART_SIZE, TOOLTIP_PROPS } from './chartTheme';
import { lowConfidence, scoreOf, thresholdCurve } from './evalSummary';
import { useEvalRun, useEvalRuns, useStartEval } from './queries';

const STATUS_TONE = {
  succeeded: 'success',
  failed: 'danger',
  running: 'info',
  queued: 'neutral',
} as const;

export function EvaluationPage() {
  usePageTitle('Evaluation');
  const { hasRole } = useAuth();
  const runs = useEvalRuns();
  const start = useStartEval();
  const items = runs.data?.items ?? [];
  const latest = items.find((r) => r.status === 'succeeded') ?? null;
  const latestDetail = useEvalRun(latest?.id ?? null);
  const curve = thresholdCurve(latestDetail.data);
  const low = lowConfidence(latestDetail.data);
  const trend = items
    .filter((r) => r.status === 'succeeded')
    .slice()
    .reverse()
    .map((r) => ({
      when: formatDateTime(r.created_at),
      p5: scoreOf(r.scorecard, 'p@5'),
      passRate: scoreOf(r.scorecard, 'pass_rate'),
    }));
  const busy = items.some((r) => r.status === 'queued' || r.status === 'running');

  return (
    <div className="flex flex-col gap-4" data-testid="page-evaluation">
      <PageHeader
        title="Evaluation"
        description="Retrieval precision and validation pass rate on the dev question pool, using the active index and live settings. The held-out test set is never run from here."
        actions={
          hasRole('admin') ? (
            <Button
              onClick={() => {
                start.mutate();
              }}
              disabled={start.isPending || busy}
              data-testid="run-evaluation"
            >
              <Play aria-hidden className="size-4" />
              {busy ? 'Evaluation running…' : 'Run evaluation'}
            </Button>
          ) : undefined
        }
      />
      {start.isError ? (
        <ErrorAlert error={start.error} title="Could not start the evaluation" />
      ) : null}
      {runs.isError ? <ErrorAlert error={runs.error} /> : null}
      {runs.isPending ? <Spinner /> : null}
      {runs.data && items.length === 0 ? (
        <EmptyState title="No evaluation runs yet">
          {hasRole('admin') ? 'Run one to see the scorecard.' : 'An administrator can start one.'}
        </EmptyState>
      ) : null}
      {items.length > 0 ? (
        <>
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            <Card>
              <CardContent className="pt-4">
                <ChartFigure
                  title="P@5 and pass rate over runs"
                  description="Targets: P@5 ≥ 0.65 (SC2), pass rate ≥ 0.80 (SC3)."
                  columns={['Run', 'P@5', 'Pass rate']}
                  rows={trend.map((t) => [t.when, formatScore(t.p5), formatScore(t.passRate)])}
                  testId="chart-eval-trend"
                >
                  <ResponsiveContainer initialDimension={CHART_SIZE}>
                    <LineChart {...CHART_PROPS} data={trend}>
                      <CartesianGrid stroke={CHART.grid} strokeDasharray="3 3" />
                      <XAxis dataKey="when" stroke={CHART.text} fontSize={11} />
                      <YAxis domain={[0, 1]} stroke={CHART.text} fontSize={12} />
                      <ChartTooltip {...TOOLTIP_PROPS} />
                      <Legend />
                      <Line dataKey="p5" name="P@5" stroke={CHART.primary} strokeWidth={2} />
                      <Line
                        dataKey="passRate"
                        name="Pass rate"
                        stroke={CHART.success}
                        strokeWidth={2}
                        strokeDasharray="5 3"
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </ChartFigure>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-4">
                {curve.length > 0 ? (
                  <ChartFigure
                    title="Threshold sweep (latest run)"
                    description="Pass rate on answerable questions and false validations on unanswerable ones, by threshold τ."
                    columns={['Threshold', 'Pass rate', 'False validation rate']}
                    rows={curve.map((p) => [
                      p.threshold.toFixed(2),
                      formatPercent(p.pass_rate),
                      formatPercent(p.false_validation_rate),
                    ])}
                    testId="chart-threshold-sweep"
                  >
                    <ResponsiveContainer initialDimension={CHART_SIZE}>
                      <LineChart {...CHART_PROPS} data={curve}>
                        <CartesianGrid stroke={CHART.grid} strokeDasharray="3 3" />
                        <XAxis
                          dataKey="threshold"
                          type="number"
                          domain={[0.3, 0.9]}
                          stroke={CHART.text}
                          fontSize={12}
                        />
                        <YAxis domain={[0, 1]} stroke={CHART.text} fontSize={12} />
                        <ChartTooltip {...TOOLTIP_PROPS} />
                        <Legend />
                        <ReferenceLine
                          x={0.6}
                          stroke={CHART.text}
                          strokeDasharray="4 4"
                          label="τ 0.6"
                        />
                        <Line
                          dataKey="pass_rate"
                          name="Pass rate"
                          stroke={CHART.success}
                          strokeWidth={2}
                          dot={false}
                        />
                        <Line
                          dataKey="false_validation_rate"
                          name="False validation"
                          stroke={CHART.warning}
                          strokeWidth={2}
                          strokeDasharray="5 3"
                          dot={false}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </ChartFigure>
                ) : (
                  <p className="text-sm text-muted-foreground">The latest run has no sweep data.</p>
                )}
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Run history</CardTitle>
            </CardHeader>
            <CardContent>
              <Table label="Evaluation runs" data-testid="eval-runs-table">
                <THead>
                  <tr>
                    <Th>Started</Th>
                    <Th>Status</Th>
                    <Th>Index</Th>
                    <Th>P@5</Th>
                    <Th>Hit@5</Th>
                    <Th>Pass rate</Th>
                    <Th>False validations</Th>
                  </tr>
                </THead>
                <TBody>
                  {items.map((r) => (
                    <tr key={r.id} data-testid="eval-run-row">
                      <Td className="whitespace-nowrap">{formatDateTime(r.created_at)}</Td>
                      <Td>
                        <Badge tone={STATUS_TONE[r.status]}>{r.status}</Badge>
                        {r.error ? (
                          <span className="block text-xs text-danger">{r.error}</span>
                        ) : null}
                      </Td>
                      <Td className="font-mono">{r.index_version ?? '—'}</Td>
                      <Td>{formatScore(scoreOf(r.scorecard, 'p@5'))}</Td>
                      <Td>{formatScore(scoreOf(r.scorecard, 'hit@5'))}</Td>
                      <Td>{formatPercent(scoreOf(r.scorecard, 'pass_rate'))}</Td>
                      <Td>{formatPercent(scoreOf(r.scorecard, 'false_validation_rate'))}</Td>
                    </tr>
                  ))}
                </TBody>
              </Table>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Low-confidence list (latest run)</CardTitle>
              <CardDescription>
                Wrong decisions and validated answers close to the threshold, for analyst review.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {low.length === 0 ? (
                <p className="text-sm text-muted-foreground">Nothing flagged.</p>
              ) : (
                <Table label="Low-confidence questions" data-testid="low-confidence-table">
                  <THead>
                    <tr>
                      <Th>Question</Th>
                      <Th>Why flagged</Th>
                      <Th>Confidence</Th>
                      <Th>Topic</Th>
                    </tr>
                  </THead>
                  <TBody>
                    {low.map((item) => (
                      <tr key={item.id}>
                        <Td className="max-w-md">{item.question}</Td>
                        <Td>{item.why}</Td>
                        <Td className="font-mono">{formatScore(item.confidence)}</Td>
                        <Td>{item.topic}</Td>
                      </tr>
                    ))}
                  </TBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </>
      ) : null}
    </div>
  );
}
