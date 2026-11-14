import { Send } from 'lucide-react';
import { useId, useState, type SyntheticEvent, type KeyboardEvent } from 'react';

import { Button } from '@/components/ui/button';
import { Input, Label, Textarea } from '@/components/ui/input';

export const QUESTION_MIN = 3;
export const QUESTION_MAX = 1000;
export const TOP_K_DEFAULT = 5;

interface Props {
  onAsk: (question: string, topK: number) => void;
  pending: boolean;
  initialQuestion?: string;
}

/** Enter submits; Shift+Enter adds a line. Limits mirror the API contract (ADR-0006). */
export function QuestionForm({ onAsk, pending, initialQuestion = '' }: Props) {
  const [question, setQuestion] = useState(initialQuestion);
  const [topK, setTopK] = useState(TOP_K_DEFAULT);
  const [error, setError] = useState<string | null>(null);
  const hintId = useId();
  const errorId = useId();

  const submit = (event?: SyntheticEvent) => {
    event?.preventDefault();
    const trimmed = question.trim();
    if (trimmed.length < QUESTION_MIN) {
      setError(`Type a question of at least ${QUESTION_MIN.toString()} characters.`);
      return;
    }
    setError(null);
    onAsk(trimmed, topK);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      if (!pending) submit();
    }
  };

  return (
    <form onSubmit={submit} className="flex flex-col gap-3" data-testid="question-form" noValidate>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="question">Your question</Label>
        <Textarea
          id="question"
          data-testid="question-input"
          value={question}
          maxLength={QUESTION_MAX}
          placeholder="e.g. How long should hand hygiene with alcohol-based handrub take?"
          aria-describedby={error ? `${hintId} ${errorId}` : hintId}
          aria-invalid={error ? true : undefined}
          onChange={(e) => {
            setQuestion(e.target.value);
          }}
          onKeyDown={onKeyDown}
        />
        <p id={hintId} className="text-xs text-muted-foreground">
          Press Enter to ask, Shift+Enter for a new line. {question.length}/{QUESTION_MAX}
        </p>
        {error ? (
          <p id={errorId} role="alert" className="text-sm text-danger">
            {error}
          </p>
        ) : null}
      </div>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="top-k">Sources to search (top_k)</Label>
          <Input
            id="top-k"
            data-testid="top-k-input"
            type="number"
            min={1}
            max={20}
            value={topK}
            className="w-24"
            onChange={(e) => {
              const value = Number(e.target.value);
              setTopK(
                Number.isFinite(value)
                  ? Math.min(20, Math.max(1, Math.round(value)))
                  : TOP_K_DEFAULT,
              );
            }}
          />
        </div>
        <Button type="submit" disabled={pending} data-testid="ask-button">
          <Send aria-hidden className="size-4" />
          {pending ? 'Checking the guidelines…' : 'Ask'}
        </Button>
      </div>
    </form>
  );
}
