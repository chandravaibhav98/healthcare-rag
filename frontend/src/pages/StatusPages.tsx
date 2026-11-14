import { Link } from 'react-router';

import { buttonVariants } from '@/components/ui/button-variants';
import { usePageTitle } from '@/hooks/usePageTitle';

function StatusPage({
  code,
  title,
  children,
}: {
  code: string;
  title: string;
  children: React.ReactNode;
}) {
  usePageTitle(title);
  return (
    <div
      className="mx-auto flex max-w-xl flex-col items-start gap-4 p-8"
      data-testid={`page-${code}`}
    >
      <p className="text-sm font-semibold text-muted-foreground">Error {code}</p>
      <h1 className="text-2xl font-bold">{title}</h1>
      <div className="text-muted-foreground">{children}</div>
      <Link to="/" className={buttonVariants({ variant: 'outline' })}>
        Back to the assistant
      </Link>
    </div>
  );
}

export function ForbiddenPage() {
  return (
    <StatusPage code="403" title="You don’t have access to this page">
      The dashboard is for reviewers and administrators. Ask an administrator for the reviewer role
      if you need it.
    </StatusPage>
  );
}

export function NotFoundPage() {
  return (
    <StatusPage code="404" title="Page not found">
      The page you asked for doesn’t exist.
    </StatusPage>
  );
}
