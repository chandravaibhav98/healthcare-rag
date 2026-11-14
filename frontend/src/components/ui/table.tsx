import type { HTMLAttributes, TdHTMLAttributes, ThHTMLAttributes } from 'react';

import { cn } from '@/lib/cn';

/** Scrollable on small screens; the region is focusable so keyboard users can scroll it. */
export function Table({
  className,
  label,
  ...props
}: HTMLAttributes<HTMLTableElement> & { label: string }) {
  return (
    <div
      className="w-full overflow-x-auto rounded-md border border-border"
      role="region"
      aria-label={label}
      tabIndex={0}
    >
      <table className={cn('w-full text-left text-sm', className)} {...props} />
    </div>
  );
}

export function THead(props: HTMLAttributes<HTMLTableSectionElement>) {
  return <thead className="bg-muted" {...props} />;
}

export function TBody(props: HTMLAttributes<HTMLTableSectionElement>) {
  return <tbody className="divide-y divide-border" {...props} />;
}

export function Th({ className, ...props }: ThHTMLAttributes<HTMLTableCellElement>) {
  return <th scope="col" className={cn('px-3 py-2 font-semibold', className)} {...props} />;
}

export function Td({ className, ...props }: TdHTMLAttributes<HTMLTableCellElement>) {
  return <td className={cn('px-3 py-2 align-top', className)} {...props} />;
}
