import { useState, type SyntheticEvent } from 'react';

import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { EmptyState, ErrorAlert, Spinner } from '@/components/ui/feedback';
import { Input, Label } from '@/components/ui/input';
import { Pagination } from '@/components/ui/pagination';
import { Table, TBody, Td, Th, THead } from '@/components/ui/table';
import { usePageTitle } from '@/hooks/usePageTitle';
import { formatDateTime } from '@/lib/format';

import { PageHeader } from './AdminLayout';
import { useAuditLog, type AuditParams } from './queries';

const PAGE = 50;

export function AuditLogPage() {
  usePageTitle('Audit log');
  const [draft, setDraft] = useState({ action: '', actor: '', from: '', to: '' });
  const [params, setParams] = useState<AuditParams>({ limit: PAGE, offset: 0, order: 'desc' });
  const log = useAuditLog(params);

  const apply = (e: SyntheticEvent) => {
    e.preventDefault();
    setParams({
      limit: PAGE,
      offset: 0,
      order: 'desc',
      action: draft.action || undefined,
      actor_email: draft.actor || undefined,
      from: draft.from ? new Date(`${draft.from}T00:00:00`).toISOString() : undefined,
      to: draft.to ? new Date(`${draft.to}T23:59:59.999`).toISOString() : undefined,
    });
  };

  return (
    <div className="flex flex-col gap-4" data-testid="page-audit">
      <PageHeader
        title="Audit log"
        description="Sign-ins, reviews, settings changes, index activations and purges."
      />
      <Card>
        <CardContent className="pt-4">
          <form
            onSubmit={apply}
            className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5"
            aria-label="Audit filters"
          >
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="a-action">Action starts with</Label>
              <Input
                id="a-action"
                placeholder="e.g. config. or auth."
                data-testid="audit-action"
                value={draft.action}
                onChange={(e) => {
                  setDraft({ ...draft, action: e.target.value });
                }}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="a-actor">Actor e-mail</Label>
              <Input
                id="a-actor"
                type="email"
                value={draft.actor}
                onChange={(e) => {
                  setDraft({ ...draft, actor: e.target.value });
                }}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="a-from">From (date)</Label>
              <Input
                id="a-from"
                type="date"
                value={draft.from}
                onChange={(e) => {
                  setDraft({ ...draft, from: e.target.value });
                }}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="a-to">To (date)</Label>
              <Input
                id="a-to"
                type="date"
                value={draft.to}
                onChange={(e) => {
                  setDraft({ ...draft, to: e.target.value });
                }}
              />
            </div>
            <div className="flex items-end">
              <Button type="submit" data-testid="audit-apply">
                Apply
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
      {log.isError ? <ErrorAlert error={log.error} /> : null}
      {log.isPending ? <Spinner /> : null}
      {log.data?.items.length === 0 ? <EmptyState title="No audit entries match" /> : null}
      {log.data?.items.length ? (
        <>
          <Table label="Audit entries" data-testid="audit-table">
            <THead>
              <tr>
                <Th>When</Th>
                <Th>Actor</Th>
                <Th>Action</Th>
                <Th>Target</Th>
                <Th>Details</Th>
              </tr>
            </THead>
            <TBody>
              {log.data.items.map((entry) => (
                <tr key={entry.id} data-testid="audit-row">
                  <Td className="whitespace-nowrap">{formatDateTime(entry.created_at)}</Td>
                  <Td>{entry.actor_email ?? 'system'}</Td>
                  <Td className="font-mono">{entry.action}</Td>
                  <Td>
                    {entry.target_type ? `${entry.target_type} ${entry.target_id ?? ''}` : '—'}
                  </Td>
                  <Td>
                    <code className="block max-w-md whitespace-pre-wrap break-all text-xs">
                      {JSON.stringify(entry.details)}
                    </code>
                  </Td>
                </tr>
              ))}
            </TBody>
          </Table>
          <Pagination
            total={log.data.total}
            limit={log.data.limit}
            offset={log.data.offset}
            onChange={(offset) => {
              setParams({ ...params, offset });
            }}
          />
        </>
      ) : null}
    </div>
  );
}
