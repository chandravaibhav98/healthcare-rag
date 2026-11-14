import { useQuery } from '@tanstack/react-query';
import { LayoutDashboard, LogIn, LogOut, MessageSquareText, Moon, Sun } from 'lucide-react';
import { NavLink, Outlet, useNavigate } from 'react-router';

import { api, unwrap } from '@/api/client';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/features/auth/useAuth';
import { useTheme } from '@/hooks/useTheme';
import { cn } from '@/lib/cn';

export function DisclaimerBanner() {
  return (
    <div
      role="note"
      aria-label="Clinical disclaimer"
      data-testid="clinical-disclaimer"
      className="bg-warning-bg px-4 py-2 text-center text-sm text-warning"
    >
      <strong>Not for clinical use.</strong> All guideline content is synthetic. Answers are for
      demonstration and must never guide patient care.
    </div>
  );
}

const navClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    'inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium hover:bg-muted',
    isActive && 'bg-muted',
  );

function VersionFooter() {
  const { data } = useQuery({
    queryKey: ['version'],
    queryFn: () => unwrap(api.GET('/version')),
    staleTime: 5 * 60_000,
    retry: false,
  });
  return (
    <footer className="border-t border-border py-3 text-xs text-muted-foreground">
      <div className="mx-auto max-w-7xl px-4">
        <span>Synthetic WHO/NIH/CDC-style corpus · prototype</span>
        {data ? (
          <span data-testid="version-info">
            {' '}
            · API {data.build_version} · contract {data.contract_version} · index{' '}
            {data.index_version ?? 'not loaded'}
          </span>
        ) : null}
      </div>
    </footer>
  );
}

export function AppShell() {
  const { user, hasRole, logout } = useAuth();
  const [theme, toggleTheme] = useTheme();
  const navigate = useNavigate();

  return (
    <div className="flex min-h-dvh flex-col">
      <a
        href="#main"
        className="sr-only z-50 rounded-md bg-primary px-3 py-2 text-primary-foreground focus:not-sr-only focus:fixed focus:left-2 focus:top-2"
      >
        Skip to main content
      </a>
      <header className="border-b border-border bg-card">
        <DisclaimerBanner />
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-2 px-4 py-2">
          <NavLink to="/" className="font-semibold">
            Guidelines Assistant
          </NavLink>
          <nav aria-label="Main" className="flex flex-wrap items-center gap-1">
            <NavLink to="/" end className={navClass} data-testid="nav-assistant">
              <MessageSquareText aria-hidden className="size-4" />
              Assistant
            </NavLink>
            {hasRole('reviewer') ? (
              <NavLink to="/admin" className={navClass} data-testid="nav-admin">
                <LayoutDashboard aria-hidden className="size-4" />
                Dashboard
              </NavLink>
            ) : null}
            <Button
              variant="ghost"
              size="icon"
              onClick={toggleTheme}
              aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
              data-testid="theme-toggle"
            >
              {theme === 'dark' ? (
                <Sun aria-hidden className="size-4" />
              ) : (
                <Moon aria-hidden className="size-4" />
              )}
            </Button>
            {user ? (
              <>
                <span className="px-2 text-sm text-muted-foreground" data-testid="current-user">
                  {user.display_name} ({user.role})
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  data-testid="logout"
                  onClick={() => {
                    void logout().then(() => navigate('/'));
                  }}
                >
                  <LogOut aria-hidden className="size-4" />
                  Sign out
                </Button>
              </>
            ) : (
              <NavLink to="/login" className={navClass} data-testid="nav-login">
                <LogIn aria-hidden className="size-4" />
                Sign in
              </NavLink>
            )}
          </nav>
        </div>
      </header>
      <main id="main" tabIndex={-1} className="flex-1 outline-none">
        <Outlet />
      </main>
      <VersionFooter />
    </div>
  );
}
