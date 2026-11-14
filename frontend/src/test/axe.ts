import axe from 'axe-core';
import { expect } from 'vitest';

/**
 * Run axe-core on the rendered DOM and fail on serious or critical violations (the plan's
 * Phase 6 exit criterion). jsdom has no layout, so colour contrast is checked in the
 * browser audit (Lighthouse) instead.
 */
export async function expectNoSeriousA11yViolations(root: Element = document.body): Promise<void> {
  const results = await axe.run(root, {
    rules: { 'color-contrast': { enabled: false } },
    resultTypes: ['violations'],
  });
  const serious = results.violations.filter(
    (v) => v.impact === 'serious' || v.impact === 'critical',
  );
  expect(
    serious.map((v) => `${v.id}: ${v.help} (${v.nodes.map((n) => n.target.join(' ')).join(', ')})`),
  ).toEqual([]);
}
