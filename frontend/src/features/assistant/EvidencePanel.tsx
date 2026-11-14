import { Check, X } from 'lucide-react';
import { useMemo } from 'react';

import type { Citation } from '@/api/types';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { checkEvidence } from '@/lib/evidence';
import { formatPercent, formatScore } from '@/lib/format';

interface Props {
  citation: Citation;
  /** Text compared with the source: the answer, or the question when abstaining. */
  compareWith: string;
  compareLabel: 'answer' | 'question';
  /** Shown in the sentence: e.g. 'answer sentences citing this source'. */
  compareDescription?: string;
}

export function EvidencePanel({ citation, compareWith, compareLabel, compareDescription }: Props) {
  const description = compareDescription ?? compareLabel;
  const check = useMemo(
    () => checkEvidence(compareWith, citation.snippet),
    [compareWith, citation.snippet],
  );
  return (
    <Card data-testid="evidence-panel" aria-labelledby="evidence-title">
      <CardHeader>
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone="info">[{citation.id}]</Badge>
          <CardTitle id="evidence-title">{citation.title}</CardTitle>
          {citation.superseded ? (
            <Badge tone="warning" data-testid="superseded-badge">
              Superseded version
            </Badge>
          ) : null}
        </div>
        <CardDescription>
          {citation.source_org} · {citation.section_path} · match score{' '}
          {formatScore(citation.score)}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <p className="text-sm" data-testid="evidence-overlap">
          <strong>{check.matchedTerms}</strong> of {check.answerTerms} key words in the{' '}
          {description} appear in this source ({formatPercent(check.overlap)}). They are{' '}
          <mark className="rounded bg-highlight px-0.5 text-foreground">highlighted</mark>.
        </p>
        <blockquote
          className="max-h-80 overflow-y-auto whitespace-pre-wrap rounded-md border-l-4 border-primary bg-muted p-3 text-sm leading-relaxed"
          data-testid="evidence-text"
          tabIndex={0}
          aria-label="Source text"
        >
          {check.segments.map((segment, i) =>
            segment.match ? (
              <mark key={i} className="rounded bg-highlight px-0.5 text-foreground">
                {segment.text}
              </mark>
            ) : (
              <span key={i}>{segment.text}</span>
            ),
          )}
        </blockquote>
        {check.numbers.length > 0 ? (
          <div>
            <h3 className="text-sm font-semibold">Numbers in the {description}</h3>
            <ul className="mt-1 flex flex-wrap gap-2" data-testid="number-checks">
              {check.numbers.map(({ value, found }) => (
                <li key={value}>
                  <Badge tone={found ? 'success' : 'danger'}>
                    {found ? (
                      <Check aria-hidden className="size-3" />
                    ) : (
                      <X aria-hidden className="size-3" />
                    )}
                    {value}
                    <span className="sr-only">
                      {found ? 'found in this source' : 'not in this source'}
                    </span>
                  </Badge>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        <p className="text-xs text-muted-foreground">
          Chunk {citation.chunk_id}. This view explains the evidence; the validation decision itself
          is made by the server’s checks.
        </p>
      </CardContent>
    </Card>
  );
}
