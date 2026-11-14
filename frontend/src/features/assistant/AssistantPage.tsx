import { useEffect, useRef, useState } from 'react';

import { ApiError } from '@/api/client';
import { Card, CardContent } from '@/components/ui/card';
import { EmptyState, ErrorAlert, Skeleton } from '@/components/ui/feedback';
import { usePageTitle } from '@/hooks/usePageTitle';
import { textCiting } from '@/lib/evidence';

import { AnswerCard } from './AnswerCard';
import { EvidencePanel } from './EvidencePanel';
import {
  clearHistory,
  HISTORY_LIMIT,
  loadHistory,
  saveHistory,
  type HistoryEntry,
} from './history';
import { HistorySidebar } from './HistorySidebar';
import { QuestionForm } from './QuestionForm';
import { useAsk } from './useAsk';

function errorTitle(error: Error): string {
  if (error instanceof ApiError) {
    if (error.status === 429) return 'Too many questions in a short time. Wait a moment.';
    if (error.status === 401) return 'Sign in to ask questions on this deployment.';
    if (error.status === 503) return 'The guideline index is loading. Try again shortly.';
    if (error.status === 422) return 'The question could not be accepted.';
  }
  return 'The question could not be answered';
}

export function AssistantPage() {
  usePageTitle('Ask the guidelines');
  const ask = useAsk();
  const [history, setHistory] = useState<HistoryEntry[]>(loadHistory);
  const [active, setActive] = useState<HistoryEntry | null>(() => history[0] ?? null);
  const [selectedCitation, setSelectedCitation] = useState<number | null>(null);
  const resultRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    saveHistory(history);
  }, [history]);

  const onAsk = (question: string, topK: number) => {
    ask.mutate(
      { question, topK },
      {
        onSuccess: (response) => {
          const entry: HistoryEntry = {
            id: response.meta?.request_id ?? crypto.randomUUID(),
            question,
            topK,
            askedAt: new Date().toISOString(),
            response,
          };
          setHistory((prev) => [entry, ...prev].slice(0, HISTORY_LIMIT));
          setActive(entry);
          setSelectedCitation(
            response.status === 'validated' ? (response.citations[0]?.id ?? null) : null,
          );
          // Move focus to the result so screen-reader users hear it (and keyboard users land there).
          requestAnimationFrame(() => resultRef.current?.focus());
        },
      },
    );
  };

  const citation = active?.response.citations.find((c) => c.id === selectedCitation) ?? null;

  return (
    <div className="mx-auto grid grid-cols-1 max-w-7xl gap-6 p-4 lg:grid-cols-[16rem_1fr]">
      <div className="order-2 lg:order-1">
        <HistorySidebar
          entries={history}
          activeId={active?.id ?? null}
          onSelect={(entry) => {
            setActive(entry);
            setSelectedCitation(null);
          }}
          onClear={() => {
            clearHistory();
            setHistory([]);
            setActive(null);
          }}
        />
      </div>
      <div className="order-1 flex min-w-0 flex-col gap-4 lg:order-2">
        <div>
          <h1 className="text-2xl font-bold">Ask the guidelines</h1>
          <p className="text-sm text-muted-foreground">
            Answers come only from the indexed guideline documents, with citations. When the
            evidence is weak the assistant says so instead of guessing.
          </p>
        </div>
        <Card>
          <CardContent className="pt-4">
            <QuestionForm onAsk={onAsk} pending={ask.isPending} />
          </CardContent>
        </Card>

        <div
          ref={resultRef}
          tabIndex={-1}
          aria-live="polite"
          className="flex flex-col gap-4 outline-none"
        >
          {ask.isPending ? (
            <div className="flex flex-col gap-2" data-testid="answer-loading">
              <span className="sr-only">Checking the guidelines…</span>
              <Skeleton className="h-6 w-40" />
              <Skeleton className="h-24 w-full" />
            </div>
          ) : ask.isError ? (
            <ErrorAlert title={errorTitle(ask.error)} error={ask.error} />
          ) : active ? (
            <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
              <AnswerCard
                question={active.question}
                response={active.response}
                selectedCitation={selectedCitation}
                onSelectCitation={setSelectedCitation}
              />
              {citation ? (
                <EvidencePanel
                  citation={citation}
                  compareWith={
                    active.response.status === 'validated'
                      ? textCiting(active.response.answer, citation.id)
                      : active.question
                  }
                  compareLabel={active.response.status === 'validated' ? 'answer' : 'question'}
                  compareDescription={
                    active.response.status === 'validated'
                      ? 'answer sentences citing this source'
                      : 'question'
                  }
                />
              ) : active.response.citations.length === 0 ? (
                <EmptyState title="No matching sources">
                  None of the indexed guidelines matched this question.
                </EmptyState>
              ) : (
                <EmptyState title="Select a source">
                  Choose a citation to see its text, with the words it shares with the{' '}
                  {active.response.status === 'validated' ? 'answer' : 'question'} highlighted.
                </EmptyState>
              )}
            </div>
          ) : (
            <EmptyState title="No question yet">
              Ask about infection prevention, PPE, hand hygiene, vaccination and more.
            </EmptyState>
          )}
        </div>
      </div>
    </div>
  );
}
