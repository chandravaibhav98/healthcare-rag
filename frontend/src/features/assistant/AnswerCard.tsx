import { Copy } from 'lucide-react';
import { useState } from 'react';

import type { Citation, QAResponse } from '@/api/types';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Alert } from '@/components/ui/feedback';
import { ConfidenceMeter, StatusBadge } from '@/components/ui/status';
import { cn } from '@/lib/cn';
import { parseAnswer } from '@/lib/evidence';
import { formatMs } from '@/lib/format';

import { formatAnswerForCopy } from './copy';
import { EscalateButton } from './EscalateButton';
import { reasonText } from './reasons';

interface Props {
  question: string;
  response: QAResponse;
  selectedCitation: number | null;
  onSelectCitation: (id: number) => void;
}

function CitationChip({
  citation,
  selected,
  onSelect,
}: {
  citation: Citation | undefined;
  selected: boolean;
  onSelect: () => void;
}) {
  if (!citation) return null;
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      aria-label={`Source ${citation.id.toString()}: ${citation.title}`}
      data-testid={`citation-chip-${citation.id.toString()}`}
      className={cn(
        'mx-0.5 inline-flex min-h-6 min-w-6 items-center justify-center rounded border border-primary px-1 align-baseline text-xs font-semibold text-primary hover:bg-muted',
        selected && 'bg-primary text-primary-foreground hover:bg-primary',
      )}
    >
      {citation.id}
    </button>
  );
}

export function AnswerCard({ question, response, selectedCitation, onSelectCitation }: Props) {
  const [copied, setCopied] = useState<'idle' | 'done' | 'failed'>('idle');
  const validated = response.status === 'validated';
  const byId = new Map(response.citations.map((c) => [c.id, c]));
  const reason = response.meta?.reason;

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(formatAnswerForCopy(question, response));
      setCopied('done');
    } catch {
      setCopied('failed');
    }
  };

  return (
    <Card data-testid="answer-card" aria-labelledby="answer-heading">
      <CardHeader className="flex-row flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <h2 id="answer-heading" className="text-base font-semibold">
            Answer
          </h2>
          <StatusBadge status={response.status} />
        </div>
        <ConfidenceMeter confidence={response.confidence} signals={response.meta?.signals} />
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {validated ? (
          <p className="leading-relaxed" data-testid="answer-text">
            {parseAnswer(response.answer).map((part, i) =>
              part.kind === 'text' ? (
                <span key={i}>{part.text}</span>
              ) : (
                <CitationChip
                  key={i}
                  citation={byId.get(part.id)}
                  selected={selectedCitation === part.id}
                  onSelect={() => {
                    onSelectCitation(part.id);
                  }}
                />
              ),
            )}
          </p>
        ) : (
          <Alert tone="warning" title="No validated answer" testId="abstention">
            <p data-testid="answer-text">{response.answer}</p>
            {reason ? <p className="mt-1">Why: {reasonText(reason)}</p> : null}
          </Alert>
        )}

        {response.citations.length > 0 ? (
          <div>
            <h3 className="mb-2 text-sm font-semibold">
              {validated
                ? 'Sources'
                : 'Closest sources (read them, but they did not validate an answer)'}
            </h3>
            <ol className="flex flex-col gap-1" data-testid="citation-list">
              {response.citations.map((c) => (
                <li key={c.id}>
                  <button
                    type="button"
                    className={cn(
                      'flex w-full flex-wrap items-center gap-2 rounded-md px-2 py-1 text-left text-sm hover:bg-muted',
                      selectedCitation === c.id && 'bg-muted',
                    )}
                    aria-pressed={selectedCitation === c.id}
                    onClick={() => {
                      onSelectCitation(c.id);
                    }}
                    data-testid={`citation-item-${c.id.toString()}`}
                  >
                    <Badge tone="info">[{c.id}]</Badge>
                    <span className="font-medium">{c.title}</span>
                    <span className="text-muted-foreground">
                      {c.source_org} · {c.section_path}
                    </span>
                    {c.superseded ? <Badge tone="warning">Superseded</Badge> : null}
                  </button>
                </li>
              ))}
            </ol>
          </div>
        ) : null}

        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              void copy();
            }}
            data-testid="copy-answer"
          >
            <Copy aria-hidden className="size-4" />
            Copy with sources
          </Button>
          {response.meta ? (
            <EscalateButton requestId={response.meta.request_id} abstained={!validated} />
          ) : null}
          <span aria-live="polite" className="text-sm text-muted-foreground">
            {copied === 'done'
              ? 'Copied.'
              : copied === 'failed'
                ? 'Copy failed: select the text instead.'
                : ''}
          </span>
          {response.meta ? (
            <span className="ml-auto text-xs text-muted-foreground">
              {formatMs(response.meta.latency_ms)} · index {response.meta.index_version} · ref{' '}
              {response.meta.request_id.slice(0, 12)}
            </span>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}
