import { useState, type SyntheticEvent } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Dialog, DialogContent } from '@/components/ui/dialog';
import { EmptyState, ErrorAlert, Spinner } from '@/components/ui/feedback';
import { Input, Label, Select } from '@/components/ui/input';
import { Pagination } from '@/components/ui/pagination';
import { StatusBadge } from '@/components/ui/status';
import { Table, TBody, Td, Th, THead } from '@/components/ui/table';
import { usePageTitle } from '@/hooks/usePageTitle';
import { formatDateTime, formatMs, formatScore } from '@/lib/format';

import { PageHeader } from './AdminLayout';
import { useQueryDetail, useQueryList, type QueriesParams } from './queries';

const PAGE = 25;

interface Filters {
  status: '' | 'validated' | 'needs_review';
  minConfidence: string;
  maxConfidence: string;
  from: string;
  to: string;
  indexVersion: string;
  text: string;
}

const EMPTY: Filters = {
  status: '',
  minConfidence: '',
  maxConfidence: '',
  from: '',
  to: '',
  indexVersion: '',
  text: '',
};

function toParams(
  f: Filters,
  offset: number,
  sort: QueriesParams['sort'],
  order: 'asc' | 'desc',
): QueriesParams {
  const params: QueriesParams = { limit: PAGE, offset, sort, order };
  if (f.status) params.status = f.status;
  if (f.minConfidence !== '') params.min_confidence = Number(f.minConfidence);
  if (f.maxConfidence !== '') params.max_confidence = Number(f.maxConfidence);
  // Dates from <input type="date"> are local days; send UTC instants that cover them.
  if (f.from) params.from = new Date(`${f.from}T00:00:00`).toISOString();
  if (f.to) params.to = new Date(`${f.to}T23:59:59.999`).toISOString();
  if (f.indexVersion) params.index_version = f.indexVersion.trim();
  if (f.text) params.q = f.text.trim();
  return params;
}

function QueryDrawer({ id, onClose }: { id: string | null; onClose: () => void }) {
  const detail = useQueryDetail(id);
  const d = detail.data;
  return (
    <Dialog
      open={id !== null}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent variant="sheet" title="Query detail" testId="query-drawer">
        {detail.isPending ? <Spinner /> : null}
        {detail.isError ? <ErrorAlert error={detail.error} /> : null}
        {d ? (
          <div className="flex flex-col gap-4 text-sm">
            <p className="text-base font-medium">{d.question}</p>
            <div className="flex flex-wrap gap-2">
              <StatusBadge status={d.status} />
              {d.escalated_at ? <Badge tone="danger">Escalated</Badge> : null}
              {d.redactions > 0 ? <Badge>{d.redactions} redaction(s)</Badge> : null}
              {d.review ? <Badge>Reviewed: {d.review.verdict}</Badge> : null}
            </div>
            <dl className="grid grid-cols-[10rem_1fr] gap-x-3 gap-y-1">
              <dt className="text-muted-foreground">Asked</dt>
              <dd>{formatDateTime(d.created_at)}</dd>
              <dt className="text-muted-foreground">Confidence</dt>
              <dd>{formatScore(d.confidence)}</dd>
              {Object.entries(d.signals).map(([key, value]) => (
                <div key={key} className="contents">
                  <dt className="text-muted-foreground">{key}</dt>
                  <dd>{typeof value === 'number' ? formatScore(value) : String(value)}</dd>
                </div>
              ))}
              <dt className="text-muted-foreground">Reason</dt>
              <dd>{d.reason ?? '—'}</dd>
              <dt className="text-muted-foreground">Latency</dt>
              <dd>{formatMs(d.latency_ms)}</dd>
              <dt className="text-muted-foreground">Index version</dt>
              <dd className="font-mono">{d.index_version}</dd>
              <dt className="text-muted-foreground">Request ID</dt>
              <dd className="break-all font-mono">{d.request_id}</dd>
              <dt className="text-muted-foreground">Topics</dt>
              <dd>{d.topics.join(', ') || '—'}</dd>
            </dl>
            <div>
              <h3 className="font-semibold">Answer shown</h3>
              <p className="mt-1 rounded-md bg-muted p-2">{d.answer}</p>
            </div>
            {d.candidate_answer ? (
              <div>
                <h3 className="font-semibold">Withheld candidate answer</h3>
                <p className="mt-1 rounded-md bg-muted p-2">{d.candidate_answer}</p>
              </div>
            ) : null}
            <div>
              <h3 className="font-semibold">Citations</h3>
              <ul className="mt-1 flex flex-col gap-1">
                {d.citations.map((c) => (
                  <li key={String(c.chunk_id)}>
                    [{String(c.id)}] {String(c.title)} ·{' '}
                    <code className="text-xs">{String(c.chunk_id)}</code>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}

const SORTS = ['created_at', 'confidence', 'latency_ms'] as const satisfies readonly NonNullable<
  QueriesParams['sort']
>[];

export function QueryExplorerPage() {
  usePageTitle('Query explorer');
  const [draft, setDraft] = useState<Filters>(EMPTY);
  const [filters, setFilters] = useState<Filters>(EMPTY);
  const [offset, setOffset] = useState(0);
  const [sort, setSort] = useState<QueriesParams['sort']>('created_at');
  const [order, setOrder] = useState<'asc' | 'desc'>('desc');
  const [open, setOpen] = useState<string | null>(null);
  const list = useQueryList(toParams(filters, offset, sort, order));

  const apply = (event: SyntheticEvent) => {
    event.preventDefault();
    setFilters(draft);
    setOffset(0);
  };
  const field = (key: keyof Filters) => ({
    value: draft[key],
    onChange: (e: { target: { value: string } }) => {
      setDraft({ ...draft, [key]: e.target.value });
    },
  });

  return (
    <div className="flex flex-col gap-4" data-testid="page-queries">
      <PageHeader
        title="Query explorer"
        description="Every logged question (redacted), with its decision and evidence."
      />
      <Card>
        <CardContent className="pt-4">
          <form
            onSubmit={apply}
            className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4"
            aria-label="Filters"
            data-testid="query-filters"
          >
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="f-status">Status</Label>
              <Select id="f-status" data-testid="filter-status" {...field('status')}>
                <option value="">Any</option>
                <option value="validated">Validated</option>
                <option value="needs_review">Needs review</option>
              </Select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="f-min">Min confidence</Label>
              <Input
                id="f-min"
                type="number"
                step="0.05"
                min={0}
                max={1}
                data-testid="filter-min"
                {...field('minConfidence')}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="f-max">Max confidence</Label>
              <Input
                id="f-max"
                type="number"
                step="0.05"
                min={0}
                max={1}
                data-testid="filter-max"
                {...field('maxConfidence')}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="f-text">Question contains</Label>
              <Input id="f-text" data-testid="filter-text" {...field('text')} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="f-from">From (date)</Label>
              <Input id="f-from" type="date" {...field('from')} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="f-to">To (date)</Label>
              <Input id="f-to" type="date" {...field('to')} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="f-index">Index version</Label>
              <Input id="f-index" placeholder="e.g. 6ce73ffaf982" {...field('indexVersion')} />
            </div>
            <div className="flex items-end gap-2">
              <Button type="submit" data-testid="filter-apply">
                Apply
              </Button>
              <Button
                variant="outline"
                onClick={() => {
                  setDraft(EMPTY);
                  setFilters(EMPTY);
                  setOffset(0);
                }}
              >
                Reset
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <Label htmlFor="sort">Sort by</Label>
        <Select
          id="sort"
          className="w-40"
          value={sort}
          onChange={(e) => {
            // The API documents the sortable columns as an enum (Phase 7), so narrow the
            // free-text <select> value to it rather than casting.
            const value = SORTS.find((s) => s === e.target.value);
            if (value) setSort(value);
          }}
        >
          <option value="created_at">Time</option>
          <option value="confidence">Confidence</option>
          <option value="latency_ms">Latency</option>
        </Select>
        <Select
          aria-label="Sort order"
          className="w-32"
          value={order}
          onChange={(e) => {
            setOrder(e.target.value as 'asc' | 'desc');
          }}
        >
          <option value="desc">Descending</option>
          <option value="asc">Ascending</option>
        </Select>
      </div>
      {list.isError ? <ErrorAlert error={list.error} /> : null}
      {list.isPending ? <Spinner /> : null}
      {list.data?.items.length === 0 ? <EmptyState title="No queries match these filters" /> : null}
      {list.data?.items.length ? (
        <>
          <Table label="Queries" data-testid="queries-table">
            <THead>
              <tr>
                <Th>Question</Th>
                <Th>Status</Th>
                <Th>Confidence</Th>
                <Th>Latency</Th>
                <Th>Asked</Th>
              </tr>
            </THead>
            <TBody>
              {list.data.items.map((q) => (
                <tr key={q.id} className="hover:bg-muted/60" data-testid="query-row">
                  <Td className="max-w-md">
                    <button
                      type="button"
                      className="text-left text-primary underline-offset-2 hover:underline"
                      onClick={() => {
                        setOpen(q.id);
                      }}
                    >
                      {q.question}
                    </button>
                    {q.escalated_at ? (
                      <Badge tone="danger" className="ml-2">
                        Escalated
                      </Badge>
                    ) : null}
                  </Td>
                  <Td>
                    <StatusBadge status={q.status} />
                  </Td>
                  <Td className="font-mono">{formatScore(q.confidence)}</Td>
                  <Td>{formatMs(q.latency_ms)}</Td>
                  <Td className="whitespace-nowrap">{formatDateTime(q.created_at)}</Td>
                </tr>
              ))}
            </TBody>
          </Table>
          <Pagination
            total={list.data.total}
            limit={list.data.limit}
            offset={list.data.offset}
            onChange={setOffset}
          />
        </>
      ) : null}
      <QueryDrawer
        id={open}
        onClose={() => {
          setOpen(null);
        }}
      />
    </div>
  );
}
