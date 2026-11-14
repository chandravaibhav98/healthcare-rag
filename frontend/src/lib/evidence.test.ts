import { describe, expect, it } from 'vitest';

import {
  checkEvidence,
  contentTerms,
  highlight,
  numbersIn,
  parseAnswer,
  stripMarkers,
  textCiting,
} from './evidence';

describe('evidence helpers', () => {
  it('extracts content words without stop-words or numbers', () => {
    expect([...contentTerms('The handrub should take 20 seconds [1].')]).toEqual([
      'handrub',
      'take',
      'seconds',
    ]);
  });

  it('normalises numbers', () => {
    expect(numbersIn('Store at 2–8 °C, 70 % alcohol, 1,000 ppm')).toEqual([
      '2',
      '8',
      '70%',
      '1000',
    ]);
  });

  it('highlights shared words and keeps the rest of the text intact', () => {
    const segments = highlight('Use handrub now.', new Set(['handrub']));
    expect(segments).toEqual([
      { text: 'Use ', match: false },
      { text: 'handrub', match: true },
      { text: ' now.', match: false },
    ]);
    expect(segments.map((s) => s.text).join('')).toBe('Use handrub now.');
  });

  it('checks overlap and numbers against the source', () => {
    const check = checkEvidence(
      'Handrub takes 20–30 seconds [1]; gloves for 45 minutes [2].',
      'Rub hands with handrub for 20–30 seconds.',
    );
    expect(check.numbers).toEqual([
      { value: '20', found: true },
      { value: '30', found: true },
      { value: '45', found: false },
    ]);
    expect(check.matchedTerms).toBe(2); // handrub, seconds
    expect(check.overlap).toBeGreaterThan(0);
  });

  it('parses citation markers', () => {
    expect(parseAnswer('A [1] and B [2].')).toEqual([
      { kind: 'text', text: 'A ' },
      { kind: 'cite', id: 1 },
      { kind: 'text', text: ' and B ' },
      { kind: 'cite', id: 2 },
      { kind: 'text', text: '.' },
    ]);
    expect(stripMarkers('A [1] and B [2].')).toBe('A and B.');
  });

  it('attributes each sentence to the source it cites', () => {
    const answer = 'Rub for 20 seconds [1]. Wear gloves [2]. Both apply [1][2].';
    expect(textCiting(answer, 1)).toBe('Rub for 20 seconds. Both apply');
    expect(textCiting(answer, 2)).toBe('Wear gloves. Both apply');
    expect(textCiting(answer, 9)).toBe(answer);
  });
});
