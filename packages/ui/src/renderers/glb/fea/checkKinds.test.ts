import { describe, expect, it } from 'vitest';
import { CHECK_KINDS, FEA_CHECK_KINDS, checkLabel, checkLine, checkTitle, loadCaption } from './checkKinds.js';

const plain = (text: string) => text.replace(/ /g, ' ');
// A check as the verdict judges it: the file's, with `shown` its value at the load shown.
const at = (kind: string, shown: number, limit: number, extra: Record<string, unknown> = {}) => ({ kind, label: '', value: shown, shown, limit, unit: '', times: null, ...extra });

describe('the check kinds', () => {
  it('are the two a static study judges, each with its own words for each status and its default label', () => {
    expect(FEA_CHECK_KINDS).toEqual(['stress', 'displacement']);
    const words = Object.fromEntries(FEA_CHECK_KINDS.map((kind) => [kind, [CHECK_KINDS[kind].defaultLabel, ...['fails', 'close', 'passes'].map((status) => checkTitle({ kind }, status))]]));
    expect(words).toEqual({
      stress: ['Strength', 'Too weak', 'Close to the limit', 'Strong enough'],
      displacement: ['Displacement', 'Moves too much', 'Close to the limit', 'Stiff enough'],
    });
  });

  it('name a check by its own label, else the kind\'s', () => {
    expect(checkLabel({ kind: 'stress', label: 'Bracket' })).toBe('Bracket');
    expect(checkLabel({ kind: 'stress', label: '' })).toBe('Strength');
  });

  it('write stress and displacement bare in the verdict\'s row, led by a word in a sentence, each half kept whole', () => {
    expect(plain(checkLine(at('stress', 405.2, 276, { unit: 'MPa' }), { bare: true }))).toBe('405 MPa, limit 276 MPa');
    expect(plain(checkLine(at('stress', 405.2, 276)))).toBe('Peak 405 MPa, limit 276 MPa');
    expect(plain(checkLine(at('displacement', 1.0412, 0.5), { bare: true }))).toBe('1.04 mm, limit 0.5 mm');
    expect(plain(checkLine(at('displacement', 0.62, 0.5)))).toBe('Moves 0.62 mm, limit 0.5 mm');
  });

  it('caption the verdict with the load the weakest takes, floored', () => {
    expect(loadCaption(1.68)).toBe('OK up to 1.6× this load');
    expect(loadCaption(0.4)).toBe('OK only to 0.4× this load');
    expect(loadCaption(13.3)).toBe('OK up to 13× this load');
  });
});
