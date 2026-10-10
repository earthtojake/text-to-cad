import { describe, expect, it } from 'vitest';
import { checkLine, checkTitle } from '../checkKinds.js';
import { heldRows, madeOfRows, pushedRows } from '../setup.js';
import buckling, { BUCKLE } from './buckling.js';

const geometry = { getAttribute: (name: string) => (['_displacement', '_mode_shape_f1'].includes(name) ? { itemSize: 3 } : null) };
const result = {
  fields: [{ attribute: '_displacement', name: 'mode shape', view: 'mode_shape' }, { attribute: '_von_mises', name: 'von Mises stress' }],
  deformationScale: 20, mesh: { geometry }, occurrence: '#o1', parts: [],
  series: { kind: 'mode', unit: '×', default: 0, frames: [
    { value: 1, label: 'Mode 1 · 13.3×', attributes: { mode_shape: '_displacement' } },
    { value: 2, label: 'Mode 2 · 119×', attributes: { mode_shape: '_mode_shape_f1' } }] },
  study: { fixtures: [{ type: 'fixed', faces: ['#o1.f1'] }], loads: [{ type: 'force', faces: ['#o1.f2'], vector: [-100, 0, 0], pressure: null }],
    material: { name: 'Steel', yieldMPa: 250 } },
};

describe('buckling', () => {
  it('judges the load factor, which the load control moves, and plays Buckle', () => {
    expect(buckling).toMatchObject({ name: 'buckling', tier: 1, word: 'Buckling', noun: 'this load', family: null, scalesWithLoad: true,
      checks: ['buckling'], markers: ['load', 'fixture', 'body_load'], displayTitle: 'Loads and fixtures' });
    expect(buckling.routine(result)).toBe(BUCKLE);
    expect(BUCKLE).toEqual({ id: 'fea:buckle', label: 'Buckle', kind: 'load_ramp' });
  });

  it('opens on the mode picker over its shapes and the deformation', () => {
    const [mode, deformation] = buckling.defaultControls(result);
    expect(mode.options.map((option: { label: string }) => option.label)).toEqual(['Mode 1 · 13.3×', 'Mode 2 · 119×']);
    expect(deformation).toMatchObject({ drives: 'deformation', defaultValue: 20 });
  });

  it('sets up as static: held at, pushed, made of', () => {
    expect(buckling.setupGroups).toEqual([heldRows, pushedRows, madeOfRows]);
    const rows = buckling.setupGroups.flatMap((group: (r: unknown) => unknown[]) => group(result));
    expect(rows.map((row: { label: string }) => row.label)).toEqual(['Held at', 'Pushed', 'Made of']);
    expect(rows[1].children[0].label).toBe('100 N along −X');
  });

  it('words its check as cadgen writes it', () => {
    const check = { kind: 'buckling', value: 13.3, shown: 13.3, limit: 3, margin: 3 };
    expect(checkTitle(check, 'passes')).toBe("Won't buckle");
    expect(checkLine(check).replace(/ /g, ' ')).toBe('Buckles at 13× this load, needs 3×');
  });
});
