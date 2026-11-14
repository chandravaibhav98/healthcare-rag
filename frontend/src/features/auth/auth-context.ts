import { createContext } from 'react';

import type { Role, User } from '@/api/types';

export interface AuthState {
  user: User | null;
  /** True until the start-up session restore (refresh cookie) has finished. */
  restoring: boolean;
  login: (email: string, password: string) => Promise<User>;
  logout: () => Promise<void>;
  hasRole: (role: Role) => boolean;
}

const RANK: Record<Role, number> = { user: 0, reviewer: 1, admin: 2 };

export function roleAllows(user: User | null, required: Role): boolean {
  return user !== null && RANK[user.role] >= RANK[required];
}

export const AuthContext = createContext<AuthState | null>(null);
