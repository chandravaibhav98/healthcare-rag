import { useMutation } from '@tanstack/react-query';
import { Flag } from 'lucide-react';
import { useState } from 'react';

import { api, ApiError, unwrap } from '@/api/client';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogTrigger } from '@/components/ui/dialog';
import { ErrorAlert } from '@/components/ui/feedback';
import { Label, Textarea } from '@/components/ui/input';

/** "Escalate for review": puts this answer in the reviewers' queue (POST /escalations). */
export function EscalateButton({
  requestId,
  abstained,
}: {
  requestId: string;
  abstained: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState('');
  const mutation = useMutation({
    mutationFn: () =>
      unwrap(api.POST('/api/v1/escalations', { body: { request_id: requestId, note } })),
  });

  if (mutation.isSuccess) {
    return (
      <p role="status" className="text-sm text-success" data-testid="escalation-done">
        Sent to the reviewers. Reference {requestId.slice(0, 12)}.
      </p>
    );
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) mutation.reset();
      }}
    >
      <DialogTrigger asChild>
        <Button variant={abstained ? 'default' : 'outline'} size="sm" data-testid="escalate-button">
          <Flag aria-hidden className="size-4" />
          {abstained ? 'Escalate for review' : 'Report a problem'}
        </Button>
      </DialogTrigger>
      <DialogContent
        title="Escalate for human review"
        description="A reviewer will check this answer against the guidelines. Do not include patient details; identifiers are removed automatically."
        testId="escalate-dialog"
      >
        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            mutation.mutate();
          }}
        >
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="escalation-note">What should the reviewer look at? (optional)</Label>
            <Textarea
              id="escalation-note"
              data-testid="escalation-note"
              maxLength={1000}
              value={note}
              onChange={(e) => {
                setNote(e.target.value);
              }}
            />
          </div>
          {mutation.isError ? (
            <ErrorAlert
              title={
                mutation.error instanceof ApiError && mutation.error.status === 503
                  ? 'Escalation is not available on this deployment'
                  : 'Could not escalate'
              }
              error={mutation.error}
            />
          ) : null}
          <div className="flex justify-end gap-2">
            <Button
              variant="outline"
              onClick={() => {
                setOpen(false);
              }}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={mutation.isPending} data-testid="escalation-submit">
              {mutation.isPending ? 'Sending…' : 'Send to reviewers'}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
