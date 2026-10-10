import { describe, expect, it } from 'vitest';
import { CHECK_KINDS, FEA_CHECK_KINDS, checkCaption, checkLabel, checkLine, checkTitle, cyclesWords, loadCaption } from './checkKinds.js';

const plain = (text: string) => text.replace(/ /g, ' ');
// A check as the verdict judges it: the file's, with `shown` its value at the load shown.
const at = (kind: string, shown: number, limit: number, extra: Record<string, unknown> = {}) => ({ kind, label: '', value: shown, shown, limit, unit: '', times: null, ...extra });

describe('the check kinds', () => {
  it('are every kind the engine judges, each with its own words for each status and its default label', () => {
    expect(FEA_CHECK_KINDS).toEqual(['stress', 'displacement', 'frequency', 'buckling', 'temperature', 'acceleration', 'fatigue', 'pressure_drop',
      'velocity', 'plastic_strain', 'contact_pressure']);
    const words = Object.fromEntries(FEA_CHECK_KINDS.map((kind) => [kind, [CHECK_KINDS[kind].defaultLabel, ...['fails', 'close', 'passes'].map((status) => checkTitle({ kind }, status))]]));
    expect(words).toEqual({
      stress: ['Strength', 'Too weak', 'Close to the limit', 'Strong enough'],
      displacement: ['Displacement', 'Moves too much', 'Close to the limit', 'Stiff enough'],
      frequency: ['Vibration', 'Vibrates too low', 'Close to the limit', 'Clear of vibration'],
      buckling: ['Buckling', 'Buckles', 'Close to buckling', "Won't buckle"],
      temperature: ['Heat', 'Runs too hot', 'Close to the limit', 'Cool enough'],
      acceleration: ['Shaking', 'Shakes too hard', 'Close to the limit', 'Within the g limit'],
      fatigue: ['Fatigue life', 'Wears out too soon', 'Close to the limit', 'Lasts long enough'],
      pressure_drop: ['Flow resistance', 'Too much resistance', 'Close to the limit', 'Flows freely'],
      velocity: ['Flow speed', 'Flows too fast', 'Close to the limit', 'Slow enough'],
      plastic_strain: ['Permanent bend', 'Bends for good', 'Close to the limit', 'Springs back'],
      contact_pressure: ['Contact', 'Presses too hard', 'Close to the limit', 'Within the limit'],
    });
    // A band to stay out of has its own words.
    expect(['fails', 'close', 'passes'].map((status) => checkTitle({ kind: 'frequency', band: [110, 130] }, status)))
      .toEqual(['Resonates in the band', 'Close to the band', 'Clear of the band']);
  });

  it('say how each moves with the load: stress, displacement and acceleration with it, buckling against it, the rest not at all', () => {
    expect(FEA_CHECK_KINDS.filter((kind) => CHECK_KINDS[kind].scaling === 'linear')).toEqual(['stress', 'displacement', 'acceleration']);
    expect(FEA_CHECK_KINDS.filter((kind) => CHECK_KINDS[kind].scaling === 'inverse')).toEqual(['buckling']);
  });

  it('name a check by its own label, else the analysis\'s word for its kind, else the kind\'s', () => {
    expect(checkLabel({ kind: 'stress', label: 'Bracket' })).toBe('Bracket');
    expect(checkLabel({ kind: 'stress', label: '' }, { stress: 'Shock' })).toBe('Shock');
    expect(checkLabel({ kind: 'stress', label: '' })).toBe('Strength');
  });

  it('write stress and displacement as today: bare in the verdict\'s row, led by a word in a sentence, each half kept whole', () => {
    expect(checkLine(at('stress', 405.2, 276, { unit: 'MPa' }), { bare: true })).toBe('405 MPa, limit 276 MPa');
    expect(plain(checkLine(at('stress', 405.2, 276)))).toBe('Peak 405 MPa, limit 276 MPa');
    expect(plain(checkLine(at('displacement', 1.0412, 0.5), { bare: true }))).toBe('1.04 mm, limit 0.5 mm');
    expect(plain(checkLine(at('displacement', 0.62, 0.5)))).toBe('Moves 0.62 mm, limit 0.5 mm');
  });

  it('write every other kind as its own sentence, bare or not', () => {
    const lines = [
      at('frequency', 85.2, 60),
      at('frequency', 118.4, 110, { mode: 2, band: [110, 130] }),
      at('frequency', 135, 130, { mode: 2, band: [110, 130] }),
      at('frequency', 140, 100, { mode: 7 }),
      at('buckling', 13.3, 3, { margin: 3 }),
      at('temperature', 84.2, 100),
      at('acceleration', 12.3, 10),
      at('fatigue', 1.4, 1.5, { margin: 1.5, need: 1e6, life: 2.1e6 }),
      at('fatigue', 1.42, 1.5, { margin: 1.5, need: 1e6 }),
      at('pressure_drop', 820, 1000),
      at('velocity', 3.1, 4),
      at('plastic_strain', 0.4, 0.2),
      at('contact_pressure', 380, 400),
    ].map((check) => [plain(checkLine(check, { bare: true })), plain(checkLine(check))]);
    for (const [bare, full] of lines) expect(bare).toBe(full);
    expect(lines.map(([line]) => line)).toEqual([
      'First mode 85 Hz, must stay above 60 Hz',
      'Mode 2 at 118 Hz, inside 110–130 Hz',
      'Mode 2 at 135 Hz, clear of 110–130 Hz',
      'Mode 7 140 Hz, must stay above 100 Hz',
      'Buckles at 13× this load, needs 3×',
      'Hottest 84 °C, limit 100 °C',
      'Peak 12 g, limit 10 g',
      'Lasts 2.1 million cycles, needs 1 million',
      'Factor 1.4 at 1 million cycles, needs 1.5',
      'Drop 820 Pa, limit 1000 Pa',
      'Peak 3.1 m/s, limit 4 m/s',
      '0.4 % permanent, limit 0.2 %',
      'Peak 380 MPa, limit 400 MPa',
    ]);
    // Buckling says the analysis's noun.
    expect(plain(checkLine(at('buckling', 2.47, 3, { margin: 3 }), { noun: 'this push' }))).toBe('Buckles at 2.4× this push, needs 3×');
  });

  it('caption the verdict with the load the weakest takes for a kind that scales, else the check\'s own sentence', () => {
    expect(checkCaption(at('stress', 47, 276), { times: 1.68 })).toBe('OK up to 1.6× this load');
    expect(checkCaption(at('acceleration', 12, 10), { times: 0.83, noun: 'this shake' })).toBe('OK only to 0.8× this shake');
    expect(checkCaption(at('buckling', 13.3, 3, { margin: 3 }), { times: 13.3 })).toBe('OK up to 13× this load');
    expect(checkCaption(at('temperature', 84.2, 100))).toBe('Hottest 84 °C, 16 °C under its limit');
    expect(checkCaption(at('temperature', 103, 100))).toBe('Hottest 103 °C, 3 °C over its limit');
    expect(checkCaption(at('frequency', 85, 60))).toBe('First mode 85 Hz, must stay above 60 Hz');
    expect(loadCaption(0.4)).toBe('OK only to 0.4× this load');
  });

  it('say cycles in words', () => {
    expect([800, 5e5, 1e6, 2.1e6, 3e9].map(cyclesWords)).toEqual(['800', '500 thousand', '1 million', '2.1 million', '3 billion']);
  });
});
