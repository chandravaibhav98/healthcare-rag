import { zodResolver } from '@hookform/resolvers/zod';
import { useEffect } from 'react';
import { useForm, useWatch } from 'react-hook-form';
import { z } from 'zod';

import { ApiError } from '@/api/client';
import type { ConfigOut } from '@/api/types';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert, ErrorAlert, Spinner } from '@/components/ui/feedback';
import { FieldError, Input, Label, Textarea } from '@/components/ui/input';
import { useAuth } from '@/features/auth/useAuth';
import { usePageTitle } from '@/hooks/usePageTitle';
import { formatDateTime, formatPercent } from '@/lib/format';

import { PageHeader } from './AdminLayout';
import { nearestPoint, summaryWeights, thresholdCurve } from './evalSummary';
import { useConfig, useEvalRun, useEvalRuns, useUpdateConfig } from './queries';

const unit = z.number({ error: 'Enter a number.' }).min(0, 'Must be ≥ 0.').max(1, 'Must be ≤ 1.');

const schema = z
  .object({
    threshold: unit,
    retrieval_floor: unit,
    coverage: unit,
    query_support: unit,
    retrieval: unit,
    comment: z
      .string()
      .trim()
      .min(3, 'Say why (at least 3 characters); it goes in the audit log.')
      .max(500),
  })
  .refine((v) => Math.abs(v.coverage + v.query_support + v.retrieval - 1) < 1e-6, {
    message: 'The three weights must add up to 1.',
    path: ['retrieval'],
  });
type Values = z.infer<typeof schema>;

function toValues(config: ConfigOut): Values {
  return {
    threshold: config.values.threshold,
    retrieval_floor: config.values.retrieval_floor,
    coverage: config.values.weights.coverage,
    query_support: config.values.weights.query_support,
    retrieval: config.values.weights.retrieval,
    comment: '',
  };
}

function NumberField({
  id,
  label,
  error,
  disabled,
  register,
}: {
  id: keyof Values;
  label: string;
  error?: string | undefined;
  disabled: boolean;
  register: ReturnType<typeof useForm<Values>>['register'];
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={`cfg-${id}`}>{label}</Label>
      <Input
        id={`cfg-${id}`}
        type="number"
        step="0.01"
        min={0}
        max={1}
        disabled={disabled}
        data-testid={`cfg-${id}`}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `cfg-${id}-error` : undefined}
        {...register(id, { valueAsNumber: true })}
      />
      <FieldError id={`cfg-${id}-error`} message={error} />
    </div>
  );
}

export function SettingsPage() {
  usePageTitle('Settings');
  const { hasRole } = useAuth();
  const canEdit = hasRole('admin');
  const config = useConfig();
  const update = useUpdateConfig();
  const runs = useEvalRuns();
  const latest = runs.data?.items.find((r) => r.status === 'succeeded') ?? null;
  const latestDetail = useEvalRun(latest?.id ?? null);
  const curve = thresholdCurve(latestDetail.data);
  const runWeights = summaryWeights(latestDetail.data);

  const {
    register,
    handleSubmit,
    control,
    reset,
    formState: { errors, isDirty },
  } = useForm<Values>({ resolver: zodResolver(schema) });

  useEffect(() => {
    if (config.data) reset(toValues(config.data));
  }, [config.data, reset]);

  const threshold = useWatch({ control, name: 'threshold' });
  const [wc, wq, wr] = [
    useWatch({ control, name: 'coverage' }),
    useWatch({ control, name: 'query_support' }),
    useWatch({ control, name: 'retrieval' }),
  ];
  const current = config.data ? nearestPoint(curve, config.data.values.threshold) : null;
  const proposed = Number.isFinite(threshold) ? nearestPoint(curve, threshold) : null;
  const weightsDiffer =
    runWeights !== null && [wc, wq, wr].some((w, i) => Math.abs(w - (runWeights[i] ?? 0)) > 1e-6);

  const onSubmit = handleSubmit((v) => {
    if (!config.data) return;
    update.mutate({
      expected_version: config.data.version,
      values: {
        threshold: v.threshold,
        retrieval_floor: v.retrieval_floor,
        weights: { coverage: v.coverage, query_support: v.query_support, retrieval: v.retrieval },
      },
      comment: v.comment,
    });
  });

  return (
    <div className="flex flex-col gap-4" data-testid="page-settings">
      <PageHeader
        title="Settings"
        description="Decision threshold and confidence weights used by every API pod. Changes are versioned and audited."
      />
      {config.isPending ? <Spinner /> : null}
      {config.isError ? <ErrorAlert error={config.error} /> : null}
      {config.data ? (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_22rem]">
          <Card>
            <CardHeader>
              <CardTitle>Validation settings</CardTitle>
              <CardDescription data-testid="config-version">
                Version {config.data.version}
                {config.data.version === 0
                  ? ' (environment defaults, never changed here)'
                  : ` · changed ${formatDateTime(config.data.updated_at)}${config.data.comment ? ` · “${config.data.comment}”` : ''}`}
              </CardDescription>
            </CardHeader>
            <CardContent>
              {!canEdit ? (
                <Alert tone="info" title="Read only">
                  Only administrators can change these settings.
                </Alert>
              ) : null}
              <form
                className="mt-3 flex flex-col gap-4"
                onSubmit={(e) => void onSubmit(e)}
                data-testid="config-form"
              >
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <NumberField
                    id="threshold"
                    label="Confidence threshold τ"
                    error={errors.threshold?.message}
                    disabled={!canEdit}
                    register={register}
                  />
                  <NumberField
                    id="retrieval_floor"
                    label="Retrieval floor"
                    error={errors.retrieval_floor?.message}
                    disabled={!canEdit}
                    register={register}
                  />
                </div>
                <fieldset className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                  <legend className="mb-2 text-sm font-semibold">
                    Confidence weights (sum to 1)
                  </legend>
                  <NumberField
                    id="coverage"
                    label="Coverage"
                    error={errors.coverage?.message}
                    disabled={!canEdit}
                    register={register}
                  />
                  <NumberField
                    id="query_support"
                    label="Query support"
                    error={errors.query_support?.message}
                    disabled={!canEdit}
                    register={register}
                  />
                  <NumberField
                    id="retrieval"
                    label="Retrieval"
                    error={errors.retrieval?.message}
                    disabled={!canEdit}
                    register={register}
                  />
                </fieldset>
                {canEdit ? (
                  <>
                    <div className="flex flex-col gap-1.5">
                      <Label htmlFor="cfg-comment">Reason for the change</Label>
                      <Textarea
                        id="cfg-comment"
                        data-testid="cfg-comment"
                        aria-invalid={errors.comment ? true : undefined}
                        aria-describedby={errors.comment ? 'cfg-comment-error' : undefined}
                        {...register('comment')}
                      />
                      <FieldError id="cfg-comment-error" message={errors.comment?.message} />
                    </div>
                    {update.isError ? (
                      <ErrorAlert
                        error={update.error}
                        title={
                          update.error instanceof ApiError && update.error.status === 409
                            ? 'Someone else changed the settings. Reload the page and try again.'
                            : 'Settings not saved'
                        }
                      />
                    ) : null}
                    {update.isSuccess && !isDirty ? (
                      <Alert
                        tone="info"
                        title={`Saved as version ${update.data.version.toString()}.`}
                        testId="config-saved"
                      />
                    ) : null}
                    <div>
                      <Button
                        type="submit"
                        disabled={update.isPending || !isDirty}
                        data-testid="config-save"
                      >
                        {update.isPending ? 'Saving…' : 'Save settings'}
                      </Button>
                    </div>
                  </>
                ) : null}
              </form>
            </CardContent>
          </Card>
          <Card data-testid="impact-preview">
            <CardHeader>
              <CardTitle>Impact preview</CardTitle>
              <CardDescription>
                From the latest evaluation run’s threshold sweep (dev pool).
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-3 text-sm">
              {curve.length === 0 ? (
                <p className="text-muted-foreground">
                  Run an evaluation to see the effect of a threshold.
                </p>
              ) : (
                <>
                  <dl className="grid grid-cols-[1fr_auto_auto] gap-x-3 gap-y-1">
                    <dt />
                    <dd className="font-semibold">Now</dd>
                    <dd className="font-semibold">Proposed</dd>
                    <dt>Threshold</dt>
                    <dd>{current?.threshold.toFixed(2) ?? '—'}</dd>
                    <dd data-testid="preview-threshold">{proposed?.threshold.toFixed(2) ?? '—'}</dd>
                    <dt>Pass rate (answerable)</dt>
                    <dd>{formatPercent(current?.pass_rate)}</dd>
                    <dd data-testid="preview-pass-rate">{formatPercent(proposed?.pass_rate)}</dd>
                    <dt>False validations</dt>
                    <dd>{formatPercent(current?.false_validation_rate)}</dd>
                    <dd data-testid="preview-false-validation">
                      {formatPercent(proposed?.false_validation_rate)}
                    </dd>
                  </dl>
                  {weightsDiffer ? (
                    <Alert tone="warning" title="Weights differ from the evaluated run">
                      The preview assumes the run’s weights. Run an evaluation after saving to
                      measure the new ones.
                    </Alert>
                  ) : null}
                </>
              )}
            </CardContent>
          </Card>
        </div>
      ) : null}
    </div>
  );
}
