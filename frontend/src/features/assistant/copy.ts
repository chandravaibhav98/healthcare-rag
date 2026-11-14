import type { QAResponse } from '@/api/types';

/** Plain-text answer with numbered sources, for pasting into notes or tickets. */
export function formatAnswerForCopy(question: string, response: QAResponse): string {
  const lines = [`Q: ${question}`, '', response.answer, ''];
  lines.push(response.status === 'validated' ? 'Sources:' : 'Candidate sources (not validated):');
  for (const c of response.citations) {
    lines.push(
      `[${c.id.toString()}] ${c.title} (${c.source_org}), ${c.section_path}${c.superseded ? ' [superseded]' : ''} · ${c.chunk_id}`,
    );
  }
  lines.push(
    '',
    `Status: ${response.status} · confidence ${response.confidence.toFixed(2)}${response.meta ? ` · ref ${response.meta.request_id}` : ''}`,
    'Synthetic guidelines. Not for clinical use.',
  );
  return lines.join('\n');
}
