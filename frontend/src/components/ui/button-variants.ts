import { cva } from 'class-variance-authority';

export const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 rounded-md text-sm font-medium transition-colors ' +
    'disabled:pointer-events-none disabled:opacity-60 cursor-pointer min-h-9',
  {
    variants: {
      variant: {
        default: 'bg-primary text-primary-foreground hover:opacity-90',
        outline: 'border border-border bg-background hover:bg-muted',
        ghost: 'hover:bg-muted',
        danger: 'bg-danger text-white hover:opacity-90 dark:text-background',
        link: 'text-primary underline underline-offset-4 hover:opacity-80',
      },
      size: {
        default: 'px-4 py-2',
        sm: 'px-3 py-1.5 text-xs min-h-8',
        icon: 'size-9',
      },
    },
    defaultVariants: { variant: 'default', size: 'default' },
  },
);
