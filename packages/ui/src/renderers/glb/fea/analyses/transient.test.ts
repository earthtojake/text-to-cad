import { BufferAttribute, BufferGeometry, Group, Mesh } from 'three';
import { describe, expect, it } from 'vitest';
import { feaControls, readFeaResult, studyRows } from '../../feaResult.js';
import { activeFrameIndex } from '../series.js';
import { feaAnalysis } from './index.js';
import transient, { PLAY, historyWords, timeFieldAndDeformation, timeWords } from './transient.js';

// A cantilever with a tip force stepped on, as cadgen writes one: frame 0 (t = 0) in the fields' own
// attributes, the peak at 1.02 ms the default, each frame's stress and displacement, the envelopes beside them.
const FRAMES = [0, 0.00102, 0.003, 0.006];
const LABELS = ['0 s', '1.02 ms', '3 ms', '6 ms'];
function overTime(study: Record<string, unknown> = {}, series = true) {
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new BufferAttribute(new Float32Array([0, 0, 0, 0.1, 0, 0, 0.1, 0, 0.006]), 3));
  geometry.setIndex([0, 1, 2]);
  geometry.setAttribute('color', new BufferAttribute(new Uint8Array(12), 4, true));
  geometry.setAttribute('_von_mises', new BufferAttribute(new Float32Array(3), 1));
  geometry.setAttribute('_displacement', new BufferAttribute(new Float32Array(9), 3));
  geometry.setAttribute('_von_mises_peak', new BufferAttribute(new Float32Array([63.6, 20, 0]), 1));
  geometry.setAttribute('_displacement_peak', new BufferAttribute(new Float32Array([0, 0.1, 0.31]), 1));
  geometry.setAttribute('_face', new BufferAttribute(new Float32Array([0, 1, 1]), 1));
  FRAMES.forEach((_, index) => {
    if (!index) return;
    geometry.setAttribute(`_von_mises_f${index}`, new BufferAttribute(new Float32Array([60, 20, 0]), 1));
    geometry.setAttribute(`_displacement_f${index}`, new BufferAttribute(new Float32Array(9), 3));
  });
  const mesh = new Mesh(geometry);
  Object.assign(mesh.userData, {
    generator: 'cadgen fea', name: 'beam over time', deformation_scale: 80, faces: ['#o1.f1', '#o1.f2'],
    analysis: { type: 'transient', tier: 1, word: 'Over time', estimate: false, limits: [], noun: 'this load', reference_C: null, warnings: [] },
    fields: [
      { attribute: '_VON_MISES', name: 'von Mises stress', units: 'MPa', min: 0, max: 63.6, attribute_scale: 1, field: 'von_mises', per_frame: true },
      { attribute: '_DISPLACEMENT', name: 'displacement', units: 'mm', min: 0, max: 0.31, attribute_scale: 1000, field: 'displacement', per_frame: true },
      { attribute: '_VON_MISES_PEAK', name: 'von Mises stress (peak over time)', units: 'MPa', min: 0, max: 63.6, attribute_scale: 1, field: 'von_mises_peak' },
      { attribute: '_DISPLACEMENT_PEAK', name: 'displacement (largest over time)', units: 'mm', min: 0, max: 0.31, attribute_scale: 1, field: 'displacement_peak' },
    ],
    ...(series ? { series: { kind: 'time', unit: 's', default: 1, frames: FRAMES.map((value, index) => ({ value, label: LABELS[index], attributes: {
      von_mises: index ? `_VON_MISES_F${index}` : '_VON_MISES', displacement: index ? `_DISPLACEMENT_F${index}` : '_DISPLACEMENT' } })) } } : {}),
    study: {
      material: { name: 'Steel', yield_MPa: 250 },
      fixtures: [{ type: 'fixed', faces: ['#o1.f1'] }],
      loads: [{ type: 'force', faces: ['#o1.f2'], vector_N: [0, 0, -50], history: { shape: 'half_sine', duration_s: 0.002 } }],
      end_s: 0.006, step_s: 'auto', damping_ratio: 0.02, method: 'modal',
      mesh: { size_mm: 3, order: 2, elements: 699, refined_from_mm: null }, margin: 2,
      ...study,
    },
    checks: [{ kind: 'stress', label: 'Strength', value: 63.6, limit: 250, unit: 'MPa', ratio: 0.2544, close_at: 0.5, status: 'passes',
      where: { ref: '#o1.f1', at: [0, -3, 3] }, at: { frame: 1, value: 0.00102, unit: 's', time_s: 0.00102 } }],
    findings: [],
  });
  const root = new Group();
  root.add(mesh);
  return readFeaResult(root)!;
}

describe('transient', () => {
  it('is Over time: stress and displacement, both by this load, playing its frames', () => {
    expect(transient).toMatchObject({ name: 'transient', tier: 1, word: 'Over time', noun: 'this load', family: null,
      scalesWithLoad: true, checks: ['stress', 'displacement'], markers: ['load', 'fixture', 'base_excitation'] });
    const result = overTime();
    expect(feaAnalysis(result)).toBe(transient);
    expect(transient.routine(result)).toBe(PLAY);
    expect(PLAY).toEqual({ id: 'fea:play', label: 'Play', kind: 'play' });
    expect(transient.routine({ series: null })).toBeNull();
  });

  it('opens on a Time scrubber over its frames, on the peak, then the field and the deformation', () => {
    const result = overTime();
    const [time, field, deformation] = feaControls(result);
    expect(time).toMatchObject({ drives: 'frame', type: 'number', label: 'Time', min: 0, max: 0.006, defaultValue: 0.00102, unit: 's',
      snaps: FRAMES, frameLabels: LABELS });
    expect(field).toMatchObject({ drives: 'field', defaultValue: '_von_mises' });
    expect(field.options.map((option: { value: string }) => option.value))
      .toEqual(['_von_mises', '_displacement', '_von_mises_peak', '_displacement_peak']);
    expect(deformation).toMatchObject({ drives: 'deformation', defaultValue: 80 });
    expect(activeFrameIndex(result)).toBe(1);
    expect(activeFrameIndex(result, { frame: 0.0029 })).toBe(2);
    expect(timeFieldAndDeformation(overTime({}, false)).map((control: { drives: string }) => control.drives)).toEqual(['field', 'deformation']);
  });

  it('says the load with its history: how much, how it changes over time, which way it points', () => {
    const rows = studyRows(overTime());
    expect(rows.slice(0, 3).map((row: { label: string }) => row.label)).toEqual(['Held at', 'Pushed', 'Made of']);
    expect(rows[1].children[0]).toMatchObject({ label: '50 N half-sine, 2 ms', hint: 'Pointing down', faces: ['#o1.f2'] });
    expect(rows[1].children[0].summary).toMatch(/half-sine, 2 ms$/);
  });

  it('says a shake at the fixtures with its history', () => {
    const rows = studyRows(overTime({ loads: [], excitation: { type: 'base', direction: [0, 0, 1], amplitude_g: 10,
      history: { shape: 'ramp', duration_s: 0.001 } } }));
    expect(rows.slice(0, 3).map((row: { label: string }) => row.label)).toEqual(['Held at', 'Shaken', 'Made of']);
    expect(rows[1].children[0]).toMatchObject({ label: '10 g along Z', hint: 'Over time: ramp over 1 ms' });
  });

  it('reads each history from the study it keeps, not the raw echo', () => {
    const result = overTime({ excitation: { type: 'base', direction: [0, 0, 1], amplitude_g: 10, history: [[0, 0], [0.001, 1]] } });
    expect(result.study.loads[0].history).toEqual({ shape: 'half_sine', duration_s: 0.002 });
    expect(result.study.excitation.history).toEqual([[0, 0], [0.001, 1]]);
    result.mesh.userData.study = {};
    const rows = studyRows(result);
    expect(rows[1].children[0]).toMatchObject({ label: '50 N half-sine, 2 ms' });
    expect(rows.find((row: { id: string }) => row.id === 'shaken').children[0].hint).toBe('Over time: table of 2 points to 1 ms');
  });

  it('keeps the check\'s moment, so choosing it can jump there', () => {
    expect(overTime().checks[0].at).toMatchObject({ frame: 1, value: 0.00102 });
  });

  it('words every history and time', () => {
    expect([{ shape: 'step' }, { shape: 'ramp', duration_s: 0.002 }, { shape: 'half_sine', duration_s: 0.0015 },
      [[0, 0], [0.001, 1], [0.01, 0]], null, { shape: 'ramp' }].map(historyWords))
      .toEqual(['step', 'ramp over 2 ms', 'half-sine, 1.5 ms', 'table of 3 points to 10 ms', '', '']);
    expect([0, 0.00102, 2.5, 300].map(timeWords)).toEqual(['0 s', '1.02 ms', '2.5 s', '5 min']);
  });
});
