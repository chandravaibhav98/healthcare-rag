import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';

import { api, refreshSession, unwrap } from '@/api/client';
import { clearSession, getUser, hasSessionHint, setSession, subscribe } from '@/api/session';
import type { User } from '@/api/types';

import { AuthContext, roleAllows, type AuthState } from './auth-context';

export function AuthProvider({
  children,
  restore = true,
}: {
  children: ReactNode;
  restore?: boolean;
}) {
  const queryClient = useQueryClient();
  const [user, setUser] = useState<User | null>(getUser);
  const [restoring, setRestoring] = useState(() => restore && hasSessionHint());

  useEffect(() => subscribe(setUser), []);

  useEffect(() => {
    if (!restore || !hasSessionHint()) return;
    let cancelled = false;
    // A page reload loses the in-memory access token; the httpOnly refresh cookie (if
    // any) brings the session back without the user typing a password again.
    void refreshSession().finally(() => {
      if (!cancelled) setRestoring(false);
    });
    return () => {
      cancelled = true;
    };
  }, [restore]);

  const login = useCallback(async (email: string, password: string) => {
    const tokens = await unwrap(api.POST('/api/v1/auth/login', { body: { email, password } }));
    setSession(tokens);
    return tokens.user;
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.POST('/api/v1/auth/logout', { body: {} });
    } finally {
      clearSession();
      queryClient.clear(); // never show the previous user's cached admin data
    }
  }, [queryClient]);

  const value = useMemo<AuthState>(
    () => ({ user, restoring, login, logout, hasRole: (role) => roleAllows(user, role) }),
    [user, restoring, login, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
