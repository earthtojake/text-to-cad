import { describe, expect, it } from 'vitest';
import { colourBarText } from './FeaColourBar.jsx';

describe('the colour bar\'s words', () => {
  it('are a field\'s word and its range, a signed field from its own minimum, at the scale shown', () => {
    expect(colourBarText({ attribute: '_von_mises', name: 'von Mises stress', units: 'MPa', min: 0, max: 47.3 })).toEqual({ word: 'Stress', min: '0', max: '47.3 MPa' });
    expect(colourBarText({ attribute: '_von_mises', name: 'von Mises stress', units: 'MPa', min: 0, max: 47.3 }, 2)).toEqual({ word: 'Stress', min: '0', max: '94.6 MPa' });
    expect(colourBarText({ attribute: '_temperature', name: 'temperature', units: '°C', min: -12, max: 84 })).toEqual({ word: 'Temperature', min: '-12.0', max: '84.0 °C' });
  });

  it('write a life in cycles as powers of ten, the shortest life at the red end', () => {
    expect(colourBarText({ attribute: '_life', name: 'life', units: 'log10 cycles', min: 3, max: 9 })).toEqual({ word: 'Life', min: '10⁹', max: '10³ cycles' });
    expect(colourBarText({ attribute: '_life', name: 'life', units: 'log10 cycles', min: -2.2, max: 12 }).max).toBe('10⁻² cycles');
  });

  it('put the lowest fatigue margin, the worst, at the red end as a stress puts its peak', () => {
    expect(colourBarText({ attribute: '_fatigue_factor', name: 'fatigue safety factor', units: '', min: 4.09, max: 100 }))
      .toEqual({ word: 'Fatigue margin', min: '100', max: '4.09' });
  });

  it('say a top stopped below a singular peak as "≥", with the percentile and the peak', () => {
    const capped = { attribute: '_von_mises', name: 'von Mises stress', units: 'MPa', min: 0, max: 360.6, capped: { quantile: 0.99, peak: 948.2 } };
    expect(colourBarText(capped)).toEqual({ word: 'Stress', min: '0', max: '≥361 MPa',
      note: 'Colours stop at the 99th percentile; the peak is 948 MPa' });
    expect(colourBarText(capped, 2).note).toBe('Colours stop at the 99th percentile; the peak is 1896 MPa');
  });

  it('say the sigma level an RMS field is shown at', () => {
    expect(colourBarText({ attribute: '_von_mises_rms', name: 'von Mises RMS', units: 'MPa', min: 0, max: 30 }, 3, 3))
      .toEqual({ word: 'Stress (3σ)', min: '0', max: '90.0 MPa' });
    expect(colourBarText({ attribute: '_von_mises', name: 'von Mises stress', units: 'MPa', min: 0, max: 30 }, 1, 3).word).toBe('Stress');
  });
});
