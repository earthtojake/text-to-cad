import { describe, expect, it } from 'vitest';
import { colourBarText } from './FeaColourBar.jsx';

describe('the colour bar\'s words', () => {
  it('are a field\'s word and its range, a signed field from its own minimum, at the scale shown', () => {
    expect(colourBarText({ attribute: '_von_mises', name: 'von Mises stress', units: 'MPa', min: 0, max: 47.3 })).toEqual({ word: 'Stress', min: '0', max: '47.3 MPa' });
    expect(colourBarText({ attribute: '_von_mises', name: 'von Mises stress', units: 'MPa', min: 0, max: 47.3 }, 2)).toEqual({ word: 'Stress', min: '0', max: '94.6 MPa' });
    expect(colourBarText({ attribute: '_temperature', name: 'temperature', units: '°C', min: -12, max: 84 })).toEqual({ word: 'Temperature', min: '-12.0', max: '84.0 °C' });
  });

  it('write a life in cycles as powers of ten', () => {
    expect(colourBarText({ attribute: '_life', name: 'life', units: 'log10 cycles', min: 3, max: 9 })).toEqual({ word: 'Life', min: '10³', max: '10⁹ cycles' });
    expect(colourBarText({ attribute: '_life', name: 'life', units: 'log10 cycles', min: -2.2, max: 12 }).min).toBe('10⁻²');
  });

  it('say the sigma level an RMS field is shown at', () => {
    expect(colourBarText({ attribute: '_von_mises_rms', name: 'von Mises RMS', units: 'MPa', min: 0, max: 30 }, 3, 3))
      .toEqual({ word: 'Stress (3σ)', min: '0', max: '90.0 MPa' });
    expect(colourBarText({ attribute: '_von_mises', name: 'von Mises stress', units: 'MPa', min: 0, max: 30 }, 1, 3).word).toBe('Stress');
  });
});
