import { describe, expect, it } from 'vitest';
import { matchPaletteText } from './fuzzy-match';

describe('matchPaletteText', () => {
  const fields = {
    primary: ['Toggle Theme', 'appearance'],
    secondary: ['Switch between light and dark themes'],
  };

  it('classifies primary, alias, fuzzy, and secondary matches into ordered bands', () => {
    expect(matchPaletteText('toggle theme', fields)?.band).toBe('exact');
    expect(matchPaletteText('appearance', fields)?.band).toBe('exact');
    expect(matchPaletteText('toggle', fields)?.band).toBe('prefix');
    expect(matchPaletteText('theme', fields)?.band).toBe('substring');
    expect(matchPaletteText('tth', fields)?.band).toBe('fuzzy');
    expect(matchPaletteText('switch', fields)?.band).toBe('secondary');
    expect(matchPaletteText('unrelated', fields)).toBeUndefined();
  });

  it('rewards consecutive and word-boundary fuzzy matches over wide gaps', () => {
    const boundary = matchPaletteText('tt', { primary: ['Toggle Theme'] });
    const gaps = matchPaletteText('tt', { primary: ['Totally tangled'] });

    expect(boundary?.band).toBe('fuzzy');
    expect(gaps?.band).toBe('fuzzy');
    expect(boundary!.score).toBeGreaterThan(gaps!.score);
  });
});
