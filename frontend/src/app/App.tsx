/**
 * Application root: providers and routes (plan Phase 6).
 *
 *   /                 Query Assistant (anonymous unless ALLOW_ANONYMOUS_QA=false)
 *   /login            Sign in
 *   /admin/*          Dashboard: reviewer or admin (audit log: admin only)
 *   /403, *           Status pages
 *
 * The clinical disclaimer is part of the shell, so every route shows it (risk R8).
 * Admin pages are lazy-loaded: the assistant never downloads chart code.
 */
import { QueryClientProvider, type QueryClient } from '@tanstack/react-query';
import { lazy, Suspense, useState, type ReactNode } from 'react';
import { BrowserRouter, Route, Routes } from 'react-router';

import { AppShell } from '@/components/layout/AppShell';
import { Spinner } from '@/components/ui/feedback';
import { TooltipProvider } from '@/components/ui/tooltip';
import { AssistantPage } from '@/features/assistant/AssistantPage';
import { AuthProvider } from '@/features/auth/AuthProvider';
import { LoginPage } from '@/features/auth/LoginPage';
import { RequireRole } from '@/features/auth/RequireRole';
import { ForbiddenPage, NotFoundPage } from '@/pages/StatusPages';

import { createQueryClient } from './queryClient';

const admin = () => import('@/features/admin/pages');
const AdminLayout = lazy(() => admin().then((m) => ({ default: m.AdminLayout })));
const OverviewPage = lazy(() => admin().then((m) => ({ default: m.OverviewPage })));
const ReviewQueuePage = lazy(() => admin().then((m) => ({ default: m.ReviewQueuePage })));
const QueryExplorerPage = lazy(() => admin().then((m) => ({ default: m.QueryExplorerPage })));
const EvaluationPage = lazy(() => admin().then((m) => ({ default: m.EvaluationPage })));
const IndexPage = lazy(() => admin().then((m) => ({ default: m.IndexPage })));
const SettingsPage = lazy(() => admin().then((m) => ({ default: m.SettingsPage })));
const AuditLogPage = lazy(() => admin().then((m) => ({ default: m.AuditLogPage })));

function Loading() {
  return (
    <div className="p-8">
      <Spinner />
    </div>
  );
}

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<AssistantPage />} />
        <Route path="login" element={<LoginPage />} />
        <Route
          path="admin"
          element={
            <RequireRole role="reviewer">
              <Suspense fallback={<Loading />}>
                <AdminLayout />
              </Suspense>
            </RequireRole>
          }
        >
          <Route
            index
            element={
              <Suspense fallback={<Loading />}>
                <OverviewPage />
              </Suspense>
            }
          />
          <Route
            path="review"
            element={
              <Suspense fallback={<Loading />}>
                <ReviewQueuePage />
              </Suspense>
            }
          />
          <Route
            path="queries"
            element={
              <Suspense fallback={<Loading />}>
                <QueryExplorerPage />
              </Suspense>
            }
          />
          <Route
            path="evaluation"
            element={
              <Suspense fallback={<Loading />}>
                <EvaluationPage />
              </Suspense>
            }
          />
          <Route
            path="index"
            element={
              <Suspense fallback={<Loading />}>
                <IndexPage />
              </Suspense>
            }
          />
          <Route
            path="settings"
            element={
              <Suspense fallback={<Loading />}>
                <SettingsPage />
              </Suspense>
            }
          />
          <Route
            path="audit"
            element={
              <RequireRole role="admin">
                <Suspense fallback={<Loading />}>
                  <AuditLogPage />
                </Suspense>
              </RequireRole>
            }
          />
        </Route>
        <Route path="403" element={<ForbiddenPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}

/** Providers shared by the app and the tests (tests pass a MemoryRouter instead). */
export function Providers({
  children,
  client,
  restoreSession = true,
}: {
  children: ReactNode;
  client?: QueryClient;
  restoreSession?: boolean;
}) {
  const [queryClient] = useState(() => client ?? createQueryClient());
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider delayDuration={200}>
        <AuthProvider restore={restoreSession}>{children}</AuthProvider>
      </TooltipProvider>
    </QueryClientProvider>
  );
}

export function App() {
  return (
    <Providers>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </Providers>
  );
}
