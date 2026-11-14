import { Hammer } from 'lucide-react';
import { useState } from 'react';

import type { IndexVersion } from '@/api/types';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Dialog, DialogContent } from '@/components/ui/dialog';
import { Alert, ErrorAlert, Spinner } from '@/components/ui/feedback';
import { Input, Label, Select } from '@/components/ui/input';
import { Pagination } from '@/components/ui/pagination';
import { Table, TBody, Td, Th, THead } from '@/components/ui/table';
import { useAuth } from '@/features/auth/useAuth';
import { usePageTitle } from '@/hooks/usePageTitle';
import { formatDateTime, shortHash } from '@/lib/format';

import { PageHeader } from './AdminLayout';
import {
  useActivateVersion,
  useDocuments,
  useIndexVersions,
  useRebuildStatus,
  useStartRebuild,
  type DocumentsParams,
} from './queries';

function ActivateDialog({
  version,
  onClose,
}: {
  version: IndexVersion | null;
  onClose: () => void;
}) {
  const activate = useActivateVersion();
  return (
    <Dialog
      open={version !== null}
      onOpenChange={(open) => {
        if (!open) {
          activate.reset();
          onClose();
        }
      }}
    >
      <DialogContent
        title={`Activate index ${version?.version ?? ''}?`}
        description="Its files are verified first. New questions use it immediately; other API pods follow within the poll interval. The change is recorded in the audit log."
        testId="activate-dialog"
      >
        {activate.isError ? <ErrorAlert error={activate.error} title="Activation failed" /> : null}
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            data-testid="activate-confirm"
            disabled={activate.isPending}
            onClick={() => {
              if (version) activate.mutate(version.version, { onSuccess: onClose });
            }}
          >
            {activate.isPending ? 'Verifying…' : 'Activate'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function Versions() {
  const { hasRole } = useAuth();
  const isAdmin = hasRole('admin');
  const versions = useIndexVersions();
  const rebuild = useRebuildStatus(isAdmin);
  const startRebuild = useStartRebuild();
  const [toActivate, setToActivate] = useState<IndexVersion | null>(null);

  return (
    <Card>
      <CardHeader className="flex-row flex-wrap items-start justify-between gap-3">
        <div>
          <CardTitle>Index versions</CardTitle>
          <CardDescription>
            Each version is identified by the hash of its corpus and build settings (SC1).
          </CardDescription>
        </div>
        {isAdmin && rebuild.data?.allowed ? (
          <Button
            variant="outline"
            onClick={() => {
              startRebuild.mutate();
            }}
            disabled={rebuild.data.running || startRebuild.isPending}
            data-testid="rebuild-index"
          >
            <Hammer aria-hidden className="size-4" />
            {rebuild.data.running ? 'Rebuilding…' : 'Rebuild from corpus (dev)'}
          </Button>
        ) : null}
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {rebuild.data?.last_error ? (
          <Alert tone="danger" title="Last rebuild failed">
            {rebuild.data.last_error}
          </Alert>
        ) : null}
        {rebuild.data?.last_version && !rebuild.data.running ? (
          <Alert tone="info" title={`Last rebuild produced ${rebuild.data.last_version}`}>
            Rebuilt versions are not activated automatically.
          </Alert>
        ) : null}
        {startRebuild.isError ? <ErrorAlert error={startRebuild.error} /> : null}
        {versions.isPending ? <Spinner /> : null}
        {versions.isError ? <ErrorAlert error={versions.error} /> : null}
        {versions.data ? (
          <Table label="Index versions" data-testid="versions-table">
            <THead>
              <tr>
                <Th>Version</Th>
                <Th>Source</Th>
                <Th>Documents</Th>
                <Th>Chunks</Th>
                <Th>Corpus hash</Th>
                <Th>Config hash</Th>
                <Th>Registered</Th>
                <Th>
                  <span className="sr-only">Actions</span>
                </Th>
              </tr>
            </THead>
            <TBody>
              {versions.data.items.map((v) => (
                <tr key={v.version} data-testid="version-row">
                  <Td className="font-mono">
                    {v.version}
                    {v.is_active ? (
                      <Badge tone="success" className="ml-2">
                        Active
                      </Badge>
                    ) : null}
                  </Td>
                  <Td>{v.source}</Td>
                  <Td>{v.document_count}</Td>
                  <Td>{v.chunk_count}</Td>
                  <Td className="font-mono" title={v.corpus_hash ?? undefined}>
                    {shortHash(v.corpus_hash)}
                  </Td>
                  <Td className="font-mono" title={v.config_hash ?? undefined}>
                    {shortHash(v.config_hash)}
                  </Td>
                  <Td className="whitespace-nowrap">{formatDateTime(v.created_at)}</Td>
                  <Td>
                    {isAdmin && !v.is_active ? (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => {
                          setToActivate(v);
                        }}
                        aria-label={`Activate version ${v.version}`}
                        data-testid="activate-version"
                      >
                        Activate
                      </Button>
                    ) : null}
                  </Td>
                </tr>
              ))}
            </TBody>
          </Table>
        ) : null}
        <ActivateDialog
          version={toActivate}
          onClose={() => {
            setToActivate(null);
          }}
        />
      </CardContent>
    </Card>
  );
}

function Documents() {
  const [params, setParams] = useState<DocumentsParams>({
    limit: 25,
    offset: 0,
    sort: 'doc_id',
    order: 'asc',
  });
  const docs = useDocuments(params);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Corpus documents (active index)</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="doc-q">Title contains</Label>
            <Input
              id="doc-q"
              data-testid="doc-filter"
              value={params.q ?? ''}
              onChange={(e) => {
                setParams({ ...params, q: e.target.value || undefined, offset: 0 });
              }}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="doc-org">Source</Label>
            <Select
              id="doc-org"
              value={params.source_org ?? ''}
              onChange={(e) => {
                setParams({ ...params, source_org: e.target.value || undefined, offset: 0 });
              }}
            >
              <option value="">Any</option>
              <option value="WHO">WHO</option>
              <option value="NIH">NIH</option>
              <option value="CDC">CDC</option>
            </Select>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="doc-status">Status</Label>
            <Select
              id="doc-status"
              value={params.status ?? ''}
              onChange={(e) => {
                setParams({
                  ...params,
                  status: (e.target.value || undefined) as DocumentsParams['status'],
                  offset: 0,
                });
              }}
            >
              <option value="">Any</option>
              <option value="current">Current</option>
              <option value="superseded">Superseded</option>
            </Select>
          </div>
        </div>
        {docs.isError ? <ErrorAlert error={docs.error} /> : null}
        {docs.data ? (
          <>
            <Table label="Documents" data-testid="documents-table">
              <THead>
                <tr>
                  <Th>Document</Th>
                  <Th>Source</Th>
                  <Th>Version</Th>
                  <Th>Effective</Th>
                  <Th>Topics</Th>
                  <Th>Chunks</Th>
                </tr>
              </THead>
              <TBody>
                {docs.data.items.map((d) => (
                  <tr key={d.doc_id} data-testid="document-row">
                    <Td>
                      <span className="font-medium">{d.title}</span>
                      <span className="block font-mono text-xs text-muted-foreground">
                        {d.doc_id}
                      </span>
                      {d.status === 'superseded' ? <Badge tone="warning">Superseded</Badge> : null}
                    </Td>
                    <Td>{d.source_org}</Td>
                    <Td>{d.version}</Td>
                    <Td className="whitespace-nowrap">{d.effective_date}</Td>
                    <Td>{d.topics.join(', ')}</Td>
                    <Td>{d.chunk_count}</Td>
                  </tr>
                ))}
              </TBody>
            </Table>
            <Pagination
              total={docs.data.total}
              limit={docs.data.limit}
              offset={docs.data.offset}
              onChange={(offset) => {
                setParams({ ...params, offset });
              }}
            />
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}

export function IndexPage() {
  usePageTitle('Index and corpus');
  return (
    <div className="flex flex-col gap-4" data-testid="page-index">
      <PageHeader
        title="Index & corpus"
        description="Published index versions and the documents in the active one."
      />
      <Versions />
      <Documents />
    </div>
  );
}
