import type { AbstentionReason } from '@/api/types';

/** Plain-language explanation of each abstention reason (ADR-0007). */
export const REASON_TEXT: Record<AbstentionReason, string> = {
  no_evidence: 'No guideline text matched the question.',
  below_retrieval_floor: 'The closest guideline text is only weakly related to the question.',
  numeric_mismatch:
    'A number in the draft answer (a dose, time or temperature) is not in the cited text.',
  low_confidence: 'The cited text does not cover the question’s key terms well enough.',
};

export function reasonText(reason: string): string {
  return (REASON_TEXT as Record<string, string | undefined>)[reason] ?? reason;
}
