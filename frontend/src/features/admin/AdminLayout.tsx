import {
  BarChart3,
  ClipboardCheck,
  Database,
  FlaskConical,
  ScrollText,
  Search,
  SlidersHorizontal,
} from 'lucide-react';
import { NavLink, Outlet } from 'react-router';

import { useAuth } from '@/features/auth/useAuth';
import { cn } from '@/lib/cn';

const LINKS = [
  { to: '/admin', label: 'Overview', icon: BarChart3, end: true, admin: false },
  { to: '/admin/review', label: 'Review queue', icon: ClipboardCheck, end: false, admin: false },
  { to: '/admin/queries', label: 'Query explorer', icon: Search, end: false, admin: false },
  { to: '/admin/evaluation', label: 'Evaluation', icon: FlaskConical, end: false, admin: false },
  { to: '/admin/index', label: 'Index & corpus', icon: Database, end: false, admin: false },
  { to: '/admin/settings', label: 'Settings', icon: SlidersHorizontal, end: false, admin: false },
  { to: '/admin/audit', label: 'Audit log', icon: ScrollText, end: false, admin: true },
] as const;

export function AdminLayout() {
  const { hasRole } = useAuth();
  return (
    <div className="mx-auto grid grid-cols-1 max-w-7xl gap-6 p-4 md:grid-cols-[13rem_1fr]">
      <nav aria-label="Dashboard" data-testid="admin-nav" className="min-w-0">
        <ul className="flex gap-1 overflow-x-auto md:flex-col">
          {LINKS.filter((link) => !link.admin || hasRole('admin')).map(
            ({ to, label, icon: Icon, end }) => (
              <li key={to}>
                <NavLink
                  to={to}
                  end={end}
                  className={({ isActive }) =>
                    cn(
                      'flex items-center gap-2 whitespace-nowrap rounded-md px-3 py-2 text-sm font-medium hover:bg-muted',
                      isActive && 'bg-muted',
                    )
                  }
                >
                  <Icon aria-hidden className="size-4" />
                  {label}
                </NavLink>
              </li>
            ),
          )}
        </ul>
      </nav>
      <div className="min-w-0">
        <Outlet />
      </div>
    </div>
  );
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: React.ReactNode;
}) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-bold">{title}</h1>
        {description ? <p className="text-sm text-muted-foreground">{description}</p> : null}
      </div>
      {actions}
    </div>
  );
}
