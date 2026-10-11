import { describe, expect, it } from 'vitest';
import { checkCaption, checkLine, checkTitle } from '../checkKinds.js';
import { heldRows, madeOfRows } from '../setup.js';
import modal, { freeRows, VIBRATE } from './modal.js';

// A modal result as readFeaResult hands one over, with only what these read: two modes, mode 1 baked in.
const geometry = { getAttribute: (name: string) => (['_displacement', '_mode_shape_f1'].includes(name) ? { itemSize: 3 } : null) };
const series = { kind: 'mode', unit: 'Hz', default: 0, frames: [
  { value: 1, label: 'Mode 1 · 490 Hz', attributes: { mode_shape: '_displacement' } },
  { value: 2, label: 'Mode 2 · 3018 Hz', attributes: { mode_shape: '_mode_shape_f1' } }] };
const result = (fixtures: unknown[]) => ({
  fields: [{ attribute: '_displacement', name: 'mode shape', view: 'mode_shape' }], deformationScale: 12, series, mesh: { geometry },
  occurrence: '#o1', parts: [], study: { fixtures, loads: [], material: { name: 'Steel', yieldMPa: 250 } },
});

describe('modal', () => {
  it('judges frequencies, which no load moves, and vibrates in preview', () => {
    expect(modal).toMatchObject({ name: 'modal', tier: 1, word: 'Vibration', family: null, scalesWithLoad: false, checks: ['frequency'],
      markers: ['fixture'], displayTitle: 'Fixtures' });
    expect(modal.routine(result([]))).toBe(VIBRATE);
    expect(VIBRATE).toEqual({ id: 'fea:vibrate', label: 'Vibrate', kind: 'vibrate' });
  });

  it('opens on the mode picker over its modes and the deformation', () => {
    const [mode, deformation] = modal.defaultControls(result([]));
    expect(mode).toMatchObject({ id: 'mode', drives: 'mode', type: 'enum', defaultValue: '0',
      options: [{ value: '0', label: 'Mode 1 · 490 Hz' }, { value: '1', label: 'Mode 2 · 3018 Hz' }] });
    expect(deformation).toMatchObject({ id: 'deformation', drives: 'deformation', defaultValue: 12 });
  });

  it('says where it is held, or that nothing holds it, and what it is made of', () => {
    expect(modal.setupGroups).toEqual([heldRows, freeRows, madeOfRows]);
    const free = modal.setupGroups.flatMap((group: (r: unknown) => unknown[]) => group(result([])));
    expect(free.map((row: { label: string }) => row.label)).toEqual(['Held at', 'Made of']);
    expect(free[0].children[0]).toMatchObject({ label: 'Nothing: free in space', refs: ['#o1'], summary: 'Free in space, held by nothing' });
    const held = modal.setupGroups.flatMap((group: (r: unknown) => unknown[]) => group(result([{ type: 'fixed', faces: ['#o1.f1'] }])));
    expect(held.map((row: { label: string }) => row.label)).toEqual(['Held at', 'Made of']);
    expect(held[0].children[0].label).toBe('Face 1');
  });

  it('words its checks as cadgen writes them', () => {
    const low = { kind: 'frequency', value: 52, shown: 52, limit: 60, mode: 1 };
    expect(checkTitle(low, 'fails')).toBe('Vibrates too low');
    expect(checkLine(low).replace(/ /g, ' ')).toBe('First mode 52 Hz, must stay above 60 Hz');
    const band = { kind: 'frequency', value: 3018, shown: 3018, limit: 2900, mode: 3, band: [2900, 3100] };
    expect(checkTitle(band, 'fails')).toBe('Resonates in the band');
    expect(checkCaption(band).replace(/ /g, ' ')).toBe('Mode 3 at 3018 Hz, inside 2900–3100 Hz');
  });
});
