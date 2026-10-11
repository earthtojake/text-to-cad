import { BufferAttribute, BufferGeometry, Group, Mesh } from 'three';
import { describe, expect, it } from 'vitest';
import { checkLine, checkTitle } from '../checkKinds.js';
import { feaControls, readFeaResult, studyRows } from '../../feaResult.js';
import { activeFrameIndex, deformationAt } from '../series.js';
import harmonic, { VIBRATE, frequencyAndDeformation, sweepWords, swingingRows } from './harmonic.js';
import { feaAnalysis } from './index.js';

// A shaken cantilever as cadgen writes one: frame 0 (the sweep's bottom) in the fields' own attributes, the
// resonance at 490 Hz the default, each frame's real and imaginary displacement and its peak stress.
const FRAMES = [10, 490, 600];
function shaken(study: Record<string, unknown> = {}) {
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new BufferAttribute(new Float32Array([0, 0, 0, 0.1, 0, 0, 0.1, 0, 0.006]), 3));
  geometry.setIndex([0, 1, 2]);
  geometry.setAttribute('color', new BufferAttribute(new Uint8Array(12), 4, true));
  geometry.setAttribute('_von_mises', new BufferAttribute(new Float32Array([0.3, 0.1, 0]), 1));
  geometry.setAttribute('_displacement', new BufferAttribute(new Float32Array(9), 3));
  geometry.setAttribute('_face', new BufferAttribute(new Float32Array([0, 1, 1]), 1));
  FRAMES.forEach((_, index) => {
    geometry.setAttribute(`_displacement_im_f${index}`, new BufferAttribute(new Float32Array(9), 3));
    if (index) {
      geometry.setAttribute(`_von_mises_f${index}`, new BufferAttribute(new Float32Array([8.7, 3, 0]), 1));
      geometry.setAttribute(`_displacement_f${index}`, new BufferAttribute(new Float32Array(9), 3));
    }
  });
  const mesh = new Mesh(geometry);
  Object.assign(mesh.userData, {
    generator: 'cadgen fea', name: 'beam shaking', deformation_scale: 120, faces: ['#o1.f1', '#o1.f2'],
    analysis: { type: 'harmonic', tier: 1, word: 'Shaking', estimate: false, limits: [], noun: 'this shake', reference_C: null, warnings: [] },
    fields: [
      { attribute: '_VON_MISES', name: 'von Mises stress (peak over the cycle)', units: 'MPa', min: 0, max: 8.7, attribute_scale: 1, field: 'von_mises', per_frame: true },
      { attribute: '_DISPLACEMENT', name: 'displacement (relative to the base)', units: 'mm', min: 0, max: 0.04, attribute_scale: 1000, field: 'displacement', per_frame: true },
    ],
    series: { kind: 'frequency', unit: 'Hz', default: 1, frames: FRAMES.map((value, index) => ({ value, label: `${value} Hz`, attributes: {
      von_mises: index ? `_VON_MISES_F${index}` : '_VON_MISES', displacement: index ? `_DISPLACEMENT_F${index}` : '_DISPLACEMENT',
      displacement_im: `_DISPLACEMENT_IM_F${index}` } })) },
    study: {
      material: { name: 'Steel', yield_MPa: 250 },
      fixtures: [{ type: 'fixed', faces: ['#o1.f1'] }], loads: [],
      excitation: { type: 'base', direction: [0, 0, 1], amplitude_g: 1 }, sweep_Hz: [10, 600], damping_ratio: 0.02,
      mesh: { size_mm: 2, order: 2, elements: 1708, refined_from_mm: null }, margin: 2,
      ...study,
    },
    checks: [{ kind: 'acceleration', label: 'Tip', value: 39.1, limit: 10, unit: 'g', ratio: 3.91, close_at: 0.9, status: 'fails',
      where: { ref: '#o1.f2', at: [100, -3, 3] }, faces: ['#o1.f2'], at: { frame: 1, value: 489.6, unit: 'Hz' } }],
    findings: [],
  });
  const root = new Group();
  root.add(mesh);
  return readFeaResult(root)!;
}

describe('harmonic', () => {
  it('is Shaking: stress, displacement and acceleration, all by this shake, vibrating in preview', () => {
    expect(harmonic).toMatchObject({ name: 'harmonic', tier: 1, word: 'Shaking', noun: 'this shake', family: null, scalesWithLoad: true,
      checks: ['stress', 'displacement', 'acceleration'], markers: ['fixture', 'base_excitation', 'load'], displayTitle: 'Shaker and fixtures' });
    const result = shaken();
    expect(feaAnalysis(result)).toBe(harmonic);
    expect(harmonic.routine(result)).toBe(VIBRATE);
    expect(VIBRATE).toEqual({ id: 'fea:vibrate', label: 'Vibrate', kind: 'vibrate' });
  });

  it('opens on a Frequency scrubber over its frames, on the resonance, and the deformation', () => {
    const result = shaken();
    const [frequency, deformation] = feaControls(result);
    expect(frequency).toMatchObject({ drives: 'frame', type: 'number', label: 'Frequency', min: 10, max: 600, defaultValue: 490, unit: 'Hz',
      snaps: FRAMES, frameLabels: ['10 Hz', '490 Hz', '600 Hz'] });
    expect(deformation).toMatchObject({ drives: 'deformation', defaultValue: 120 });
    expect(activeFrameIndex(result)).toBe(1);
    expect(activeFrameIndex(result, { frame: 580 })).toBe(2);
  });

  it('turns each frame through its cycle by its own imaginary part, frame 0 included', () => {
    const result = shaken();
    expect(deformationAt(result, 1)).toEqual({ attribute: '_displacement_f1', imaginary: '_displacement_im_f1' });
    expect(deformationAt(result, 0)).toEqual({ attribute: '_displacement', imaginary: '_displacement_im_f0' });
  });

  it('falls back to the field and the deformation where there is no sweep to scrub', () => {
    const result = { ...shaken(), series: null };
    expect(frequencyAndDeformation(result).map((control: { drives: string }) => control.drives)).toEqual(['field', 'deformation']);
  });

  it('says it is held, shaken 1 g along Z where it is held, and what it is made of', () => {
    const rows = studyRows(shaken());
    expect(rows.slice(0, 3).map((row: { label: string }) => row.label)).toEqual(['Held at', 'Shaken', 'Made of']);
    expect(rows[1].children[0]).toMatchObject({ label: '1 g along Z', faces: ['#o1.f1'], summary: 'Shaken where it is held: 1 g along Z' });
  });

  it('hints the sweep and its damping on the Shaken row, read from the study it keeps', () => {
    const result = shaken();
    expect(result.study).toMatchObject({ sweepHz: [10, 600], dampingRatio: 0.02 });
    expect(studyRows(result)[1].children[0].hint).toBe('10 to 600 Hz sweep, 2% damping');
    expect(sweepWords({ sweepHz: [5, 2000], dampingRatio: null })).toBe('5 to 2000 Hz sweep');
    expect(sweepWords({ sweepHz: null, dampingRatio: 0.05 })).toBe('5% damping');
    expect(sweepWords(null)).toBe('');
  });

  it('says which loads swing in a force shake, and shows no shaker', () => {
    const result = shaken({ excitation: { type: 'force' }, loads: [{ type: 'force', faces: ['#o1.f2'], vector_N: [0, 0, 1] }] });
    const rows = studyRows(result);
    expect(rows.slice(0, 3).map((row: { label: string }) => row.label)).toEqual(['Held at', 'Pushed', 'Made of']);
    expect(rows[1].children[0]).toMatchObject({ label: '1 N up', hint: 'Swinging back and forth across the sweep' });
    expect(swingingRows(shaken())).toEqual([]);
  });

  it('words its acceleration check and keeps its frequency, so choosing it can jump there', () => {
    const result = shaken();
    const check = result.checks[0];
    expect(check.at).toMatchObject({ frame: 1, value: 489.6 });
    expect(checkTitle(check, 'fails')).toBe('Shakes too hard');
    expect(checkLine({ ...check, shown: check.value }).replace(/[\u00a0\u202f]/g, ' ')).toBe('Peak 39 g, limit 10 g');
  });
});
