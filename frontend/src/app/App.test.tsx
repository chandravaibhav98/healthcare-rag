import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoSeriousA11yViolations } from '@/test/axe';
import { renderApp } from '@/test/render';

describe('App shell', () => {
  it('always shows the clinical-use disclaimer', async () => {
    renderApp();
    expect(await screen.findByTestId('clinical-disclaimer')).toHaveTextContent(
      /not for clinical use/i,
    );
  });

  it('renders the assistant heading and a skip link', async () => {
    renderApp();
    expect(
      await screen.findByRole('heading', { level: 1, name: /ask the guidelines/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /skip to main content/i })).toHaveAttribute(
      'href',
      '#main',
    );
  });

  it('shows API and index versions in the footer', async () => {
    renderApp();
    expect(await screen.findByTestId('version-info')).toHaveTextContent('index 6ce73ffaf982'); // pragma: allowlist secret (fake hash)
  });

  it('toggles dark mode and remembers it', async () => {
    const { user } = renderApp();
    await user.click(await screen.findByTestId('theme-toggle'));
    expect(document.documentElement).toHaveClass('dark');
    expect(localStorage.getItem('hcrag.theme')).toBe('"dark"');
    await user.click(screen.getByTestId('theme-toggle'));
    expect(document.documentElement).not.toHaveClass('dark');
  });

  it('has a 404 page', async () => {
    renderApp({ route: '/nope' });
    expect(await screen.findByTestId('page-404')).toBeInTheDocument();
    await expectNoSeriousA11yViolations();
  });
});
