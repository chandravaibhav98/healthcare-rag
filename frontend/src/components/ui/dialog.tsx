import * as DialogPrimitive from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import type { ReactNode } from 'react';

import { cn } from '@/lib/cn';

export const Dialog = DialogPrimitive.Root;
export const DialogTrigger = DialogPrimitive.Trigger;
export const DialogClose = DialogPrimitive.Close;

interface ContentProps {
  title: string;
  description?: string;
  children: ReactNode;
  /** `sheet` slides in from the right (detail drawers); `center` is a modal dialog. */
  variant?: 'center' | 'sheet';
  className?: string;
  testId?: string;
}

/** Radix Dialog: focus trap, Escape to close, focus returns to the trigger, aria wiring. */
export function DialogContent({
  title,
  description,
  children,
  variant = 'center',
  className,
  testId,
}: ContentProps) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-black/50" />
      <DialogPrimitive.Content
        data-testid={testId}
        className={cn(
          'fixed z-50 flex flex-col gap-4 border border-border bg-card p-5 shadow-xl',
          variant === 'sheet'
            ? 'inset-y-0 right-0 w-full max-w-2xl overflow-y-auto'
            : 'left-1/2 top-1/2 w-[min(92vw,32rem)] -translate-x-1/2 -translate-y-1/2 rounded-lg',
          className,
        )}
      >
        <div className="flex items-start justify-between gap-4">
          <div className="flex flex-col gap-1">
            <DialogPrimitive.Title className="text-lg font-semibold">{title}</DialogPrimitive.Title>
            {description ? (
              <DialogPrimitive.Description className="text-sm text-muted-foreground">
                {description}
              </DialogPrimitive.Description>
            ) : (
              <DialogPrimitive.Description className="sr-only">{title}</DialogPrimitive.Description>
            )}
          </div>
          <DialogPrimitive.Close
            className="rounded-md p-1 hover:bg-muted"
            aria-label="Close"
            data-testid="dialog-close"
          >
            <X aria-hidden className="size-5" />
          </DialogPrimitive.Close>
        </div>
        {children}
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
}
