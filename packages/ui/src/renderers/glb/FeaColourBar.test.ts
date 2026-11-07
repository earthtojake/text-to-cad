import { describe, expect, it } from 'vitest';
import { colourBarText } from './FeaColourBar.jsx';

describe('the colour bar\'s words', () => {
  it('are a field\'s word and its range, at the load shown', () => {
    expect(colourBarText({ attribute: '_von_mises', name: 'von Mises stress', units: 'MPa', min: 0, max: 47.3 })).toEqual({ word: 'Stress', min: '0', max: '47.3 MPa' });
    expect(colourBarText({ attribute: '_von_mises', name: 'von Mises stress', units: 'MPa', min: 0, max: 47.3 }, 2)).toEqual({ word: 'Stress', min: '0', max: '94.6 MPa' });
    expect(colourBarText({ attribute: '_displacement', name: 'displacement', units: 'mm', min: 0, max: 0.214 })).toEqual({ word: 'Displacement', min: '0', max: '0.214 mm' });
  });
});
