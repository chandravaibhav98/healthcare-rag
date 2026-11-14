/**
 * Client-side evidence view (plan Phase 6, "Evidence panel").
 *
 * Shows WHY an answer counts as supported: the words of the answer that also occur in
 * the cited chunk, and whether every number in the answer appears in that chunk. This
 * mirrors the server's coverage and numeric checks (ADR-0002) closely enough to explain
 * them, but the server's `meta.signals` remain the source of truth for the decision.
 */

const STOPWORDS = new Set(
  (
    'a an and are as at be been being but by can could did do does for from had has have ' +
    'how i if in into is it its may might must no not of on or our should so such than ' +
    'that the their them then there these they this those to was we were what when where ' +
    'which while who why will with would you your after before during per also any all ' +
    'each both more most other same some only own very'
  ).split(' '),
);

const WORD_RE = /[\p{L}\p{N}]+(?:[-'][\p{L}\p{N}]+)*/gu;
const NUMBER_RE = /\d+(?:[.,]\d+)*(?:\s?%)?/g;

/** Lower-cased content words (no stop-words, no single letters). */
export function contentTerms(text: string): Set<string> {
  const terms = new Set<string>();
  for (const match of text.toLowerCase().matchAll(WORD_RE)) {
    const word = match[0];
    if (word.length > 1 && !STOPWORDS.has(word) && !/^\d/.test(word)) terms.add(word);
  }
  return terms;
}

/** Numbers as written, normalised ("70 %" → "70%", "1,000" → "1000"). */
export function numbersIn(text: string): string[] {
  const seen = new Set<string>();
  for (const match of text.matchAll(NUMBER_RE)) {
    seen.add(match[0].replace(/\s/g, '').replace(/,(?=\d{3}\b)/g, ''));
  }
  return [...seen];
}

export interface Segment {
  text: string;
  match: boolean;
}

/** Split `source` into segments, marking words that also occur in `terms`. */
export function highlight(source: string, terms: Set<string>): Segment[] {
  const segments: Segment[] = [];
  let last = 0;
  for (const match of source.matchAll(WORD_RE)) {
    const start = match.index;
    const word = match[0];
    if (!terms.has(word.toLowerCase())) continue;
    if (start > last) segments.push({ text: source.slice(last, start), match: false });
    segments.push({ text: word, match: true });
    last = start + word.length;
  }
  if (last < source.length) segments.push({ text: source.slice(last), match: false });
  return segments;
}

export interface EvidenceCheck {
  segments: Segment[];
  /** Share of the answer's content words found in this source. */
  overlap: number;
  matchedTerms: number;
  answerTerms: number;
  numbers: { value: string; found: boolean }[];
}

export function checkEvidence(answer: string, source: string): EvidenceCheck {
  const cleanAnswer = stripMarkers(answer);
  const answerTerms = contentTerms(cleanAnswer);
  const sourceTerms = contentTerms(source);
  const shared = new Set([...answerTerms].filter((t) => sourceTerms.has(t)));
  const sourceNumbers = new Set(numbersIn(source));
  return {
    segments: highlight(source, shared),
    overlap: answerTerms.size ? shared.size / answerTerms.size : 0,
    matchedTerms: shared.size,
    answerTerms: answerTerms.size,
    numbers: numbersIn(cleanAnswer).map((value) => ({ value, found: sourceNumbers.has(value) })),
  };
}

/** Remove `[n]` citation markers. */
export function stripMarkers(text: string): string {
  return text.replace(/\s?\[\d+\]/g, '');
}

export type AnswerPart = { kind: 'text'; text: string } | { kind: 'cite'; id: number };

/** Split an answer into text and `[n]` citation markers. */
export function parseAnswer(answer: string): AnswerPart[] {
  const parts: AnswerPart[] = [];
  let last = 0;
  for (const match of answer.matchAll(/\[(\d+)\]/g)) {
    if (match.index > last) parts.push({ kind: 'text', text: answer.slice(last, match.index) });
    parts.push({ kind: 'cite', id: Number(match[1]) });
    last = match.index + match[0].length;
  }
  if (last < answer.length) parts.push({ kind: 'text', text: answer.slice(last) });
  return parts;
}

/**
 * The part of an answer that cites source `id`: each sentence is attributed to the
 * marker(s) that follow it. Falls back to the whole answer when nothing cites `id`, so
 * a multi-source answer is checked against each source only for the claims it supports.
 */
export function textCiting(answer: string, id: number): string {
  const parts = parseAnswer(answer);
  const cited: string[] = [];
  let pending = '';
  let previousWasCite = false;
  let lastText = '';
  for (const part of parts) {
    if (part.kind === 'text') {
      pending += part.text;
      previousWasCite = false;
    } else {
      const sentence = previousWasCite ? lastText : pending;
      const clean = sentence.replace(/^[\s.;,:]+/, '').trim();
      if (part.id === id && clean) cited.push(clean);
      if (!previousWasCite) {
        lastText = pending;
        pending = '';
      }
      previousWasCite = true;
    }
  }
  return cited.length > 0 ? cited.join('. ') : answer;
}
