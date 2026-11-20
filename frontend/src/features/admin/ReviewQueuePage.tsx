import { zodResolver } from '@hookform/resolvers/zod';
import { useState } from 'react';
import { useForm, useWatch } from 'react-hook-form';
import { z } from 'zod';

import type { QueryDetail, ReviewQueueItem } from '@/api/types';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert, EmptyState, ErrorAlert, Spinner } from '@/components/ui/feedback';
import { FieldError, Input, Label, Select, Textarea } from '@/components/ui/input';
import { Pagination } from '@/components/ui/pagination';
import { StatusBadge } from '@/components/ui/status';
import { reasonText } from '@/features/assistant/reasons';
import { usePageTitle } from '@/hooks/usePageTitle';
import { cn } from '@/lib/cn';
import { checkEvidence } from '@/lib/evidence';
import { formatDateTime, formatScore } from '@/lib/format';

import { PageHeader } from './AdminLayout';
import { useQueryDetail, useReviewQueue, useSubmitReview, type ReviewsParams } from './queries';

const PAGE = 20;

/** Citation fields arrive as JSON values (stored rows); render only strings and numbers. */
function str(value: unknown): string {
  return typeof value === 'string' || typeof value === 'number' ? String(value) : '';
}

const reviewSchema = z
  .object({
    verdict: z.enum(['approve', 'reject', 'correct']),
    note: z.string().max(4000),
    corrected: z.array(z.string()),
    extra: z.string(),
    promote: z.boolean(),
  })
  .refine((v) => v.verdict !== 'correct' || v.corrected.length > 0 || v.extra.trim() !== '', {
    message: 'A correction needs at least one chunk id.',
    path: ['extra'],
  });
type ReviewValues = z.infer<typeof reviewSchema>;

function Evidence({ detail }: { detail: QueryDetail }) {
  const compare = detail.candidate_answer ?? detail.answer;
  return (
    <ol className="flex flex-col gap-3" data-testid="review-evidence">
      {detail.citations.map((c) => {
        const id = str(c.id);
        const snippet = str(c.snippet);
        const check = checkEvidence(compare, snippet);
        return (
          <li key={id} className="rounded-md border border-border p-3 text-sm">
            <p className="font-medium">
              [{id}] {str(c.title)}{' '}
              <span className="text-muted-foreground">
                {str(c.source_org)} · {str(c.section_path)}
              </span>
            </p>
            <p className="text-xs text-muted-foreground">{str(c.chunk_id)}</p>
            {/* A scroll container must be keyboard-reachable (WCAG 2.1.1; axe
                scrollable-region-focusable, found by the Phase 7 a11y gate). */}
            <div
              tabIndex={0}
              role="region"
              aria-label={`Text of source ${id}`}
              className="mt-2 max-h-40 overflow-y-auto whitespace-pre-wrap rounded-sm leading-relaxed focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
            >
              {check.segments.map((s, i) =>
                s.match ? (
                  <mark key={i} className="rounded bg-highlight px-0.5 text-foreground">
                    {s.text}
                  </mark>
                ) : (
                  <span key={i}>{s.text}</span>
                ),
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

function ReviewForm({
  detail,
  submit,
  onDone,
}: {
  detail: QueryDetail;
  submit: ReturnType<typeof useSubmitReview>;
  onDone: () => void;
}) {
  const chunkIds = detail.citations.map((c) => str(c.chunk_id));
  // The form is keyed by the item id (see the page), so its defaults are computed once per
  // item at mount. Resetting from an effect instead raced user input whenever the detail
  // query swapped from the previous item's placeholder data (found by the E2E suite).
  const {
    register,
    handleSubmit,
    control,
    formState: { errors },
  } = useForm<ReviewValues>({
    resolver: zodResolver(reviewSchema),
    defaultValues: {
      verdict: detail.review?.verdict ?? (detail.status === 'validated' ? 'approve' : 'correct'),
      note: detail.review?.note ?? '',
      corrected: detail.review?.corrected_citations.filter((id) => chunkIds.includes(id)) ?? [],
      extra: '',
      promote: detail.review?.promote_to_gold ?? false,
    },
  });
  const verdict = useWatch({ control, name: 'verdict' });

  const onSubmit = handleSubmit((values) => {
    const corrected = [...values.corrected, ...values.extra.split(/[\s,]+/).filter(Boolean)];
    submit.mutate(
      {
        queryId: detail.id,
        body: {
          verdict: values.verdict,
          note: values.note,
          corrected_citations: values.verdict === 'approve' ? [] : corrected,
          promote_to_gold: values.promote,
        },
      },
      { onSuccess: onDone },
    );
  });

  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => void onSubmit(e)}
      data-testid="review-form"
    >
      <fieldset className="flex flex-col gap-2">
        <legend className="text-sm font-semibold">Verdict</legend>
        {(
          [
            ['approve', 'Approve: the cited evidence supports the answer'],
            ['reject', 'Reject: the answer or its sources are wrong'],
            ['correct', 'Correct: the right evidence is a different chunk'],
          ] as const
        ).map(([value, label]) => (
          <label key={value} className="flex items-center gap-2 text-sm">
            <input
              type="radio"
              value={value}
              {...register('verdict')}
              data-testid={`verdict-${value}`}
            />
            {label}
          </label>
        ))}
      </fieldset>
      {verdict !== 'approve' ? (
        <fieldset className="flex flex-col gap-2">
          <legend className="text-sm font-semibold">Correct evidence (chunk ids)</legend>
          {chunkIds.map((id) => (
            <label key={id} className="flex items-center gap-2 text-xs">
              <input type="checkbox" value={id} {...register('corrected')} />
              <code>{id}</code>
            </label>
          ))}
          <Label htmlFor="extra-chunks">Other chunk ids (comma separated)</Label>
          <Input
            id="extra-chunks"
            data-testid="extra-chunks"
            aria-invalid={errors.extra ? true : undefined}
            aria-describedby={errors.extra ? 'extra-error' : undefined}
            {...register('extra')}
          />
          <FieldError id="extra-error" message={errors.extra?.message} />
        </fieldset>
      ) : null}
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="review-note">Note</Label>
        <Textarea id="review-note" data-testid="review-note" {...register('note')} />
      </div>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" {...register('promote')} data-testid="promote-to-gold" />
        Promote to the gold dev set (exported as a candidate for the evaluation team)
      </label>
      {submit.isError ? <ErrorAlert error={submit.error} title="Review not saved" /> : null}
      <Button type="submit" disabled={submit.isPending} data-testid="review-submit">
        {submit.isPending ? 'Saving…' : 'Save review'}
      </Button>
    </form>
  );
}

export function ReviewQueuePage() {
  usePageTitle('Review queue');
  const [params, setParams] = useState<ReviewsParams>({
    status: 'pending',
    limit: PAGE,
    offset: 0,
    order: 'desc',
  });
  const [selected, setSelected] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const queue = useReviewQueue(params);
  // Owned by the page, not the form: saving moves the queue to the next item, which
  // unmounts the form, and a mutation's per-call callbacks only run while its observer
  // is mounted (found by the Phase 7 E2E suite).
  const submit = useSubmitReview();

  const items: ReviewQueueItem[] = queue.data?.items ?? [];
  // The selection follows the list: if the chosen item left the queue, show the first one.
  const current = items.some((i) => i.query.id === selected)
    ? selected
    : (items[0]?.query.id ?? null);
  const detail = useQueryDetail(current);

  return (
    <div className="flex flex-col gap-4" data-testid="page-review">
      <PageHeader
        title="Review queue"
        description="Withheld answers and answers users escalated. Check the evidence, record a verdict, and promote good examples to the gold set."
        actions={
          <div className="flex items-center gap-2">
            <Label htmlFor="queue-status">Show</Label>
            <Select
              id="queue-status"
              className="w-40"
              value={params.status}
              data-testid="queue-status"
              onChange={(e) => {
                setParams({
                  ...params,
                  status: e.target.value as ReviewsParams['status'],
                  offset: 0,
                });
              }}
            >
              <option value="pending">Pending</option>
              <option value="reviewed">Reviewed</option>
              <option value="all">All</option>
            </Select>
          </div>
        }
      />
      {saved ? <Alert tone="info" title="Review saved." testId="review-saved" /> : null}
      {queue.isError ? <ErrorAlert error={queue.error} /> : null}
      {queue.isPending ? <Spinner /> : null}
      {queue.data && items.length === 0 ? (
        <EmptyState title="Nothing to review">
          Every withheld or escalated answer has a verdict.
        </EmptyState>
      ) : null}
      {items.length > 0 ? (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[20rem_1fr]">
          <div className="flex flex-col gap-2">
            <ul className="flex flex-col gap-1" data-testid="queue-list">
              {items.map(({ query, review }) => (
                <li key={query.id}>
                  <button
                    type="button"
                    aria-current={current === query.id ? 'true' : undefined}
                    onClick={() => {
                      setSelected(query.id);
                      setSaved(false);
                    }}
                    data-testid="queue-item"
                    className={cn(
                      'flex w-full flex-col gap-1 rounded-md border border-border p-2 text-left text-sm hover:bg-muted',
                      current === query.id && 'border-primary bg-muted',
                    )}
                  >
                    <span className="line-clamp-2 font-medium">{query.question}</span>
                    <span className="flex flex-wrap gap-1">
                      <StatusBadge status={query.status} />
                      {query.escalated_at ? <Badge tone="danger">Escalated</Badge> : null}
                      {review ? <Badge>{review.verdict}</Badge> : null}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {formatDateTime(query.created_at)}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
            {queue.data ? (
              <Pagination
                total={queue.data.total}
                limit={queue.data.limit}
                offset={queue.data.offset}
                onChange={(offset) => {
                  setParams({ ...params, offset });
                }}
              />
            ) : null}
          </div>
          <div className="min-w-0">
            {detail.isPending && current ? <Spinner label="Loading the item" /> : null}
            {detail.isError ? <ErrorAlert error={detail.error} /> : null}
            {detail.data ? (
              <div className="grid grid-cols-1 gap-4 xl:grid-cols-2" data-testid="review-detail">
                <Card>
                  <CardHeader>
                    <CardTitle>Question and answer</CardTitle>
                  </CardHeader>
                  <CardContent className="flex flex-col gap-3 text-sm">
                    <p data-testid="review-question">
                      <strong>Question:</strong> {detail.data.question}
                    </p>
                    <div className="flex flex-wrap items-center gap-2">
                      <StatusBadge status={detail.data.status} />
                      <span>confidence {formatScore(detail.data.confidence)}</span>
                      {detail.data.reason ? (
                        <span className="text-muted-foreground">
                          {reasonText(detail.data.reason)}
                        </span>
                      ) : null}
                    </div>
                    <div>
                      <strong>
                        {detail.data.candidate_answer
                          ? 'Withheld candidate answer'
                          : 'Answer shown to the user'}
                        :
                      </strong>
                      <p className="mt-1 rounded-md bg-muted p-2" data-testid="candidate-answer">
                        {detail.data.candidate_answer ?? detail.data.answer}
                      </p>
                    </div>
                    {detail.data.escalation_note ? (
                      <Alert tone="warning" title="User’s escalation note">
                        {detail.data.escalation_note}
                      </Alert>
                    ) : null}
                    <ReviewForm
                      key={detail.data.id}
                      detail={detail.data}
                      submit={submit}
                      onDone={() => {
                        setSaved(true);
                      }}
                    />
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader>
                    <CardTitle>Evidence</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <Evidence detail={detail.data} />
                  </CardContent>
                </Card>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
