/**
 * Runtime validation of the one response a clinician acts on (`/qa`). TypeScript types
 * vanish at runtime; if a proxy, cache or version skew ever delivered a malformed body,
 * the UI must refuse to render it as a validated answer rather than guess.
 */
import { z } from 'zod';

import type { QAResponse } from './types';

const citation = z.object({
  id: z.number().int().positive(),
  doc_id: z.string(),
  title: z.string(),
  source_org: z.string(),
  section_path: z.string(),
  chunk_id: z.string(),
  snippet: z.string(),
  score: z.number(),
  superseded: z.boolean().optional(),
});

const signals = z.object({
  coverage: z.number().min(0).max(1),
  query_support: z.number().min(0).max(1),
  retrieval_score: z.number().min(0).max(1),
  numeric_ok: z.boolean(),
});

export const qaResponseSchema = z
  .object({
    answer: z.string(),
    citations: z.array(citation),
    confidence: z.number().min(0).max(1),
    status: z.enum(['validated', 'needs_review']),
    meta: z
      .object({
        request_id: z.string(),
        index_version: z.string(),
        latency_ms: z.number(),
        abstained: z.boolean(),
        reason: z
          .enum(['no_evidence', 'below_retrieval_floor', 'numeric_mismatch', 'low_confidence'])
          .nullable()
          .optional(),
        signals,
      })
      .nullable()
      .optional(),
  })
  .refine((r) => r.status !== 'validated' || r.citations.length > 0, {
    message: 'a validated answer must cite evidence',
  });

export class ContractError extends Error {
  constructor(detail: string) {
    super(`The server sent an answer this app cannot verify (${detail}).`);
    this.name = 'ContractError';
  }
}

export function parseQAResponse(body: unknown): QAResponse {
  const result = qaResponseSchema.safeParse(body);
  if (!result.success) {
    throw new ContractError(result.error.issues[0]?.message ?? 'invalid response');
  }
  return result.data as QAResponse;
}
