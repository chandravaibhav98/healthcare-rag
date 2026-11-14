import { History, Trash2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/cn';
import { formatDateTime } from '@/lib/format';

import type { HistoryEntry } from './history';

interface Props {
  entries: HistoryEntry[];
  activeId: string | null;
  onSelect: (entry: HistoryEntry) => void;
  onClear: () => void;
}

export function HistorySidebar({ entries, activeId, onSelect, onClear }: Props) {
  return (
    <aside aria-labelledby="history-heading" className="flex flex-col gap-2" data-testid="history">
      <div className="flex items-center justify-between">
        <h2 id="history-heading" className="flex items-center gap-2 text-sm font-semibold">
          <History aria-hidden className="size-4" />
          This session
        </h2>
        {entries.length > 0 ? (
          <Button variant="ghost" size="sm" onClick={onClear} data-testid="history-clear">
            <Trash2 aria-hidden className="size-3.5" />
            Clear
          </Button>
        ) : null}
      </div>
      {entries.length === 0 ? (
        <p className="text-sm text-muted-foreground">Questions you ask appear here.</p>
      ) : (
        <ul className="flex flex-col gap-1">
          {entries.map((entry) => (
            <li key={entry.id}>
              <button
                type="button"
                onClick={() => {
                  onSelect(entry);
                }}
                aria-current={entry.id === activeId ? 'true' : undefined}
                data-testid="history-item"
                className={cn(
                  'flex w-full flex-col items-start gap-0.5 rounded-md px-2 py-1.5 text-left text-sm hover:bg-muted',
                  entry.id === activeId && 'bg-muted',
                )}
              >
                <span className="line-clamp-2">{entry.question}</span>
                <span className="text-xs text-muted-foreground">
                  {entry.response.status === 'validated' ? 'Validated' : 'Needs review'} ·{' '}
                  {formatDateTime(entry.askedAt)}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
      <p className="text-xs text-muted-foreground">Kept only in this browser tab.</p>
    </aside>
  );
}
