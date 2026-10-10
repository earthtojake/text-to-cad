import { BufferAttribute, BufferGeometry, Group, Mesh } from 'three';
import { describe, expect, it } from 'vitest';
import { feaControls, feaVerdict, readFeaResult, studyRows } from '../../feaResult.js';
import { checkLine, checkTitle } from '../checkKinds.js';
import { heldRows, madeOfRows } from '../setup.js';
import { feaAnalysis } from './index.js';
import { VIBRATE } from './modal.js';
import piezo, { PIEZO_SETUP, electrodeLabel, piezoElectrodeRows, poledRows, polingWords } from './piezo.js';

const LIMITS = ['Linear, small signal: room-temperature constants at low field; no depolarisation, hysteresis, ageing or self-heating.'];
const STUDY = {
  material: { name: 'PZT-5A', yield_MPa: null },
  solve: 'static',
  electrodes: [{ faces: ['#o1.f6'], name: 'top', V: 1 }, { faces: ['#o1.f5'], name: 'bottom', V: 0 }, { faces: ['#o1.f2'], name: 'out', open: true }],
  fixtures: [{ type: 'roller', faces: ['#o1.f5'] }], loads: [],
  poling: [{ part: 'disc', material: 'PZT-5A', direction: [0, 0, 1] }],
  mesh: { size_mm: 0.5, order: 2, elements: 100, refined_from_mm: null },
};

// A piezo result as cadgen writes one: the stress first, the voltage (signed), the field and the displacement.
function piezoResult(extras: Record<string, unknown> = {}, attributes: Record<string, [number[], number]> = {}) {
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new BufferAttribute(new Float32Array([0, 0, 0, 0.01, 0, 0, 0, 0.01, 0]), 3));
  geometry.setIndex([0, 1, 2]);
  geometry.setAttribute('color', new BufferAttribute(new Uint8Array(12), 4, true));
  geometry.setAttribute('_displacement', new BufferAttribute(new Float32Array(9), 3));
  geometry.setAttribute('_von_mises', new BufferAttribute(new Float32Array([0, 2, 4]), 1));
  geometry.setAttribute('_potential', new BufferAttribute(new Float32Array([0, 0.5, 1]), 1));
  geometry.setAttribute('_electric_field', new BufferAttribute(new Float32Array([0.001, 0.001, 0.001]), 1));
  geometry.setAttribute('_face', new BufferAttribute(new Float32Array([0, 0, 1]), 1));
  for (const [name, [values, size]] of Object.entries(attributes)) geometry.setAttribute(name, new BufferAttribute(new Float32Array(values), size));
  const mesh = new Mesh(geometry);
  Object.assign(mesh.userData, {
    generator: 'cadgen fea', name: 'disc piezo', deformation_scale: 50, faces: ['#o1.f2', '#o1.f5', '#o1.f6'],
    analysis: { type: 'piezo', tier: 3, word: 'Piezo', estimate: false, limits: LIMITS, noun: 'this voltage', reference_C: null,
      warnings: [], solve: 'static' },
    fields: [
      { attribute: '_VON_MISES', name: 'von Mises stress', units: 'MPa', min: 0, max: 4, attribute_scale: 1, field: 'von_mises' },
      { attribute: '_POTENTIAL', name: 'voltage', units: 'V', min: 0, max: 1, attribute_scale: 1, field: 'potential', signed: true },
      { attribute: '_ELECTRIC_FIELD', name: 'electric field', units: 'kV/mm', min: 0, max: 0.001, attribute_scale: 1, field: 'electric_field' },
      { attribute: '_DISPLACEMENT', name: 'displacement', units: 'mm', min: 0, max: 1e-4, attribute_scale: 1000, field: 'displacement' },
    ],
    study: STUDY,
    checks: [{ kind: 'voltage', label: 'Signal', value: 0.82, limit: 0.5, unit: 'V', ratio: 0.5 / 0.82, close_at: 0.9, status: 'passes',
      where: { ref: '#o1.f2', at: [0, 0, 0] }, electrode: 'out' }],
    findings: [],
    ...extras,
  });
  const root = new Group();
  root.add(mesh);
  return readFeaResult(root)!;
}

const RESONANCE = {
  analysis: { type: 'piezo', tier: 3, word: 'Piezo', estimate: false, limits: LIMITS, noun: 'this voltage', reference_C: null, warnings: [],
    solve: 'resonance' },
  fields: [
    { attribute: '_DISPLACEMENT', name: 'mode shape', units: 'mm', min: 0, max: 1, attribute_scale: 1000, field: 'mode_shape', per_frame: true },
    { attribute: '_VON_MISES', name: 'von Mises stress (mode shape scaled to 1 mm)', units: 'MPa', min: 0, max: 40, attribute_scale: 1,
      field: 'von_mises', per_frame: true },
    { attribute: '_POTENTIAL', name: 'voltage (mode shape scaled to 1 mm)', units: 'V', min: -900, max: 900, attribute_scale: 1,
      field: 'potential', signed: true, per_frame: true },
  ],
  series: { kind: 'mode', unit: 'Hz', default: 0, frames: [
    { value: 1, label: 'Mode 1 · 1.94 MHz', attributes: { mode_shape: '_DISPLACEMENT', von_mises: '_VON_MISES', potential: '_POTENTIAL' } },
    { value: 2, label: 'Mode 2 · 2.42 MHz', attributes: { mode_shape: '_MODE_SHAPE_F1', von_mises: '_VON_MISES_F1', potential: '_POTENTIAL_F1' } },
  ] },
  study: { ...STUDY, solve: 'resonance', fixtures: [], modes_requested: 2 },
  checks: [{ kind: 'frequency', label: 'Vibration', value: 1935000, limit: 1000000, unit: 'Hz', ratio: 0.52, close_at: 0.9, status: 'passes',
    mode: 1, where: { ref: null, at: [0, 0, 0] } }],
};
const FRAME_ONE = { _mode_shape_f1: [[0, 0, 0, 0, 0, 0, 0, 0, 0], 3] as [number[], number], _von_mises_f1: [[1, 2, 3], 1] as [number[], number],
  _potential_f1: [[-1, 0, 1], 1] as [number[], number] };

describe('piezo', () => {
  it('is Piezo, Tier 3: judged by stress, displacement, its signal or a frequency, which no load control moves', () => {
    expect(piezo).toMatchObject({ name: 'piezo', tier: 3, word: 'Piezo', noun: 'this voltage', family: null, scalesWithLoad: false,
      limitWord: 'Linear', checks: ['stress', 'displacement', 'voltage', 'frequency'] });
    expect(feaAnalysis(piezoResult())).toBe(piezo);
    expect(piezo.routine(piezoResult())).toBeNull();
  });

  it('opens on the Field select, stress, voltage, field and displacement, and the deformation', () => {
    const controls = feaControls(piezoResult());
    expect(controls.map((control: { drives: string }) => control.drives)).toEqual(['field', 'deformation']);
    expect(controls[0].options.map((option: { label: string }) => option.label)).toEqual(['Stress', 'Voltage', 'Electric field', 'Displacement']);
  });

  it('sets up as its electrodes ("1 V on the top electrode"), how it is poled ("Along Z"), where it is held and what it is made of', () => {
    expect(piezo.setupGroups).toEqual(PIEZO_SETUP);
    expect(PIEZO_SETUP).toContain(heldRows);
    expect(PIEZO_SETUP).toContain(madeOfRows);
    const result = piezoResult();
    const rows = studyRows(result);
    expect(rows.slice(0, 3).map((row: { label: string }) => row.label)).toEqual(['Electrodes', 'Poled', 'Slides on']);
    expect(rows[0].children.map((row: { label: string }) => row.label))
      .toEqual(['1 V on the top electrode', '0 V on the bottom electrode', 'The out electrode, open']);
    expect(rows[0].children[0]).toMatchObject({ faces: ['#o1.f6'], summary: '1 V on the top electrode (face 6), poled along Z' });
    expect(rows[0].children[2].hint).toContain('Floats');
    expect(poledRows(result)[0].children[0]).toMatchObject({ label: 'Along Z', hint: 'disc, PZT-5A', summary: 'Disc poled along Z' });
    expect([polingWords([0, 0, -1]), polingWords([1, 0, 0]), polingWords([0.6, 0, 0.8])]).toEqual(['along −Z', 'along X', 'along (0.6, 0, 0.8)']);
    expect(electrodeLabel({ name: 'sense_out', open: true, volts: null })).toBe('The sense out electrode, open');
    const none = piezoResult({ study: { ...STUDY, electrodes: undefined } });
    expect(piezoElectrodeRows(none)).toEqual([]);
  });

  it('says its signal against the least it must make, in plain words, and leads its takeaway with "Linear · "', () => {
    const verdict = feaVerdict(piezoResult());
    expect(verdict.title).toBe('Strong enough signal');
    expect(verdict.caption.startsWith('Linear · ')).toBe(true);
    const plain = (text: string) => text.replace(/\u00a0/g, ' ');
    expect(plain(checkLine({ kind: 'voltage', shown: 0.82, limit: 0.5, unit: 'V' }))).toBe('0.82 V, needs at least 0.5 V');
    expect(['fails', 'close', 'passes'].map((status) => checkTitle({ kind: 'voltage' }, status)))
      .toEqual(['Signal too weak', 'Close to the limit', 'Strong enough signal']);
    const weak = feaVerdict(piezoResult({ checks: [{ kind: 'voltage', label: 'Signal', value: 0.3, limit: 0.5, unit: 'V', ratio: 0.5 / 0.3,
      close_at: 0.9, status: 'fails', where: { ref: '#o1.f2', at: [0, 0, 0] }, electrode: 'out' }] }));
    expect(weak.title).toBe('Signal too weak');
  });

  it('opens a resonance on the mode picker, the field (per mode) and the deformation, and vibrates', () => {
    const result = piezoResult(RESONANCE, FRAME_ONE);
    const controls = feaControls(result);
    expect(controls.map((control: { drives: string }) => control.drives)).toEqual(['mode', 'field', 'deformation']);
    expect(controls[0].options.map((option: { label: string }) => option.label)).toEqual(['Mode 1 · 1.94 MHz', 'Mode 2 · 2.42 MHz']);
    expect(controls[1].options.map((option: { label: string }) => option.label)).toEqual(['Mode shape', 'Stress', 'Voltage']);
    expect(piezo.routine(result)).toBe(VIBRATE);
    expect(feaVerdict(result).title).toBe('Clear of vibration');
  });
});
