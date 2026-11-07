import { describe, expect, it } from 'vitest';
import { FIELD_WORDS, fieldWord } from './fields.js';

describe('the fields', () => {
  it('name the two a static result carries in plain words, and fall back to the file\'s name for any other', () => {
    expect(FIELD_WORDS).toEqual({ _von_mises: 'Stress', _displacement: 'Displacement' });
    expect(fieldWord({ attribute: '_VON_MISES', name: 'von Mises stress' })).toBe('Stress');
    expect(fieldWord({ attribute: '_displacement', name: 'displacement' })).toBe('Displacement');
    expect(fieldWord({ attribute: '_vorticity', name: 'vorticity' })).toBe('vorticity');
  });
});
