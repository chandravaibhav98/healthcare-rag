import { describe, expect, it } from 'vitest';

import { qaAbstained, qaValidated } from '@/test/fixtures';

import { ContractError, parseQAResponse } from './validation';

describe('parseQAResponse', () => {
  it('accepts contract-shaped answers', () => {
    expect(parseQAResponse(qaValidated)).toEqual(qaValidated);
    expect(parseQAResponse(qaAbstained).status).toBe('needs_review');
  });

  it('rejects a validated answer without evidence', () => {
    expect(() => parseQAResponse({ ...qaValidated, citations: [] })).toThrow(ContractError);
  });

  it('rejects unknown statuses and out-of-range confidence', () => {
    expect(() => parseQAResponse({ ...qaValidated, status: 'approved' })).toThrow(ContractError);
    expect(() => parseQAResponse({ ...qaValidated, confidence: 1.4 })).toThrow(ContractError);
  });
});
