import type { ReactNode } from 'react';

/**
 * A chart with a text alternative (WCAG 1.1.1): the SVG is hidden from assistive
 * technology and the same data is available as a visually hidden table.
 */
export function ChartFigure({
  title,
  description,
  columns,
  rows,
  children,
  testId,
}: {
  title: string;
  description?: string;
  columns: string[];
  rows: (string | number)[][];
  children: ReactNode;
  testId?: string;
}) {
  return (
    <figure className="flex flex-col gap-2" data-testid={testId}>
      <figcaption>
        <span className="text-sm font-semibold">{title}</span>
        {description ? (
          <span className="block text-xs text-muted-foreground">{description}</span>
        ) : null}
      </figcaption>
      <div aria-hidden className="h-56 w-full">
        {children}
      </div>
      {/* sr-only on a <table> itself does not clip (tables ignore width), so wrap it. */}
      <div className="sr-only">
        <table>
          <caption>{title}</caption>
          <thead>
            <tr>
              {columns.map((c) => (
                <th key={c} scope="col">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i}>
                {row.map((cell, j) => (
                  <td key={j}>{cell}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </figure>
  );
}
