import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { App } from './App.tsx';

describe('App', () => {
  it('always shows the clinical-use disclaimer', () => {
    render(<App />);
    expect(screen.getByRole('alert')).toHaveTextContent(/not for clinical use/i);
  });

  it('renders the product heading', () => {
    render(<App />);
    expect(
      screen.getByRole('heading', { level: 1, name: /healthcare guidelines rag assistant/i }),
    ).toBeInTheDocument();
  });
});
