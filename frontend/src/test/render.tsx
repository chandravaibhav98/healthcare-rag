import { render, type RenderResult } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactElement } from 'react';
import { MemoryRouter } from 'react-router';

import { setSession } from '@/api/session';
import type { Role } from '@/api/types';
import { AppRoutes, Providers } from '@/app/App';
import { createQueryClient } from '@/app/queryClient';

import { tokens } from './fixtures';

interface Options {
  route?: string;
  role?: Role | null;
}

/** Render the real route tree at `route`, optionally signed in as `role`. */
export function renderApp({ route = '/', role = null }: Options = {}): RenderResult & {
  user: ReturnType<typeof userEvent.setup>;
} {
  if (role) setSession(tokens(role));
  const client = createQueryClient();
  client.setDefaultOptions({
    queries: { retry: false, staleTime: Infinity },
    mutations: { retry: false },
  });
  const user = userEvent.setup();
  const result = render(
    <Providers client={client} restoreSession={false}>
      <MemoryRouter initialEntries={[route]}>
        <AppRoutes />
      </MemoryRouter>
    </Providers>,
  );
  return { ...result, user };
}

export function renderWithProviders(ui: ReactElement): RenderResult {
  const client = createQueryClient();
  client.setDefaultOptions({ queries: { retry: false } });
  return render(
    <Providers client={client} restoreSession={false}>
      <MemoryRouter>{ui}</MemoryRouter>
    </Providers>,
  );
}
