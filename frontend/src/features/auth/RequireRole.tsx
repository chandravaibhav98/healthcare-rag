import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router';

import type { Role } from '@/api/types';
import { Spinner } from '@/components/ui/feedback';

import { useAuth } from './useAuth';

/**
 * Route guard. Not signed in → login (and back afterwards); signed in without the role →
 * 403 page. This is UX only: the API enforces the same RBAC matrix on every call.
 */
export function RequireRole({ role, children }: { role: Role; children: ReactNode }) {
  const { user, restoring, hasRole } = useAuth();
  const location = useLocation();
  if (restoring) {
    return (
      <div className="p-8">
        <Spinner label="Restoring your session" />
      </div>
    );
  }
  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  }
  if (!hasRole(role)) return <Navigate to="/403" replace />;
  return children;
}
