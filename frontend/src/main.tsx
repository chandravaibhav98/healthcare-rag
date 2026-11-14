import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import { App } from './app/App.tsx';
import { applyTheme, initialTheme } from './hooks/useTheme.ts';
import './index.css';

// Apply the theme before the first paint (no light flash for dark-mode users).
applyTheme(initialTheme());

const container = document.getElementById('root');
if (!container) {
  throw new Error('Root element #root not found in index.html');
}

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
