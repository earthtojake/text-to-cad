import { BufferAttribute, BufferGeometry, Group, Mesh } from 'three';
import { describe, expect, it } from 'vitest';
import { readFeaResult } from '../feaResult.js';
import { seriesControls } from './controls.js';
import {
  activeFrame, activeFrameIndex, deformationAt, fieldAtFrame, frameAttribute, frameControl, framesBetween, frameText, isRms, sigmaControl, sigmaScale, snapFrame
} from './series.js';

// A result with a series, the way GLTFLoader hands one over: each frame's fields in attributes of their own.
function seriesResult(extras: Record<string, unknown>, vectors: Record<string, number[]>, scalars: Record<string, number[]> = {}) {
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new BufferAttribute(new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0, 1, 1, 0]), 3));
  geometry.setIndex([0, 1, 2, 1, 3, 2]);
  geometry.setAttribute('color', new BufferAttribute(new Uint8Array(16), 4, true));
  for (const [name, values] of Object.entries(vectors)) geometry.setAttribute(name, new BufferAttribute(new Float32Array(values), 3));
  for (const [name, values] of Object.entries(scalars)) geometry.setAttribute(name, new BufferAttribute(new Float32Array(values), 1));
  const mesh = new Mesh(geometry);
  Object.assign(mesh.userData, { generator: 'cadgen fea', deformation_scale: 10, ...extras });
  const root = new Group();
  root.add(mesh);
  return readFeaResult(root)!;
}
const up = (z: number) => [0, 0, 0, 0, 0, z, 0, 0, z, 0, 0, z];
const MODES = {
  analysis: { type: 'modal' },
  fields: [{ attribute: '_DISPLACEMENT', name: 'mode shape', units: 'mm', min: 0, max: 1, attribute_scale: 1000, field: 'mode_shape', per_frame: true }],
  series: { kind: 'mode', unit: 'Hz', default: 0, frames: [
    { value: 85.2, label: 'Mode 1 · 85 Hz', attributes: { mode_shape: '_DISPLACEMENT' } },
    { value: 118.4, label: 'Mode 2 · 118 Hz', attributes: { mode_shape: '_MODE_SHAPE_F1' } },
    { value: 240, label: 'Mode 3 · 240 Hz', attributes: { mode_shape: '_MODE_SHAPE_F2' } }] },
};
const modal = () => seriesResult(MODES, { _displacement: up(0.001), _mode_shape_f1: up(-0.001), _mode_shape_f2: up(0.0005) });
const TIMES = {
  analysis: { type: 'transient' },
  fields: [{ attribute: '_VON_MISES', name: 'von Mises stress', units: 'MPa', min: 0, max: 90, per_frame: true },
    { attribute: '_DISPLACEMENT', name: 'displacement', units: 'mm', min: 0, max: 2, attribute_scale: 1000, per_frame: true }],
  series: { kind: 'time', unit: 's', default: 2, frames: [
    { value: 0, label: '0 ms', attributes: { von_mises: '_VON_MISES', displacement: '_DISPLACEMENT' } },
    { value: 0.01, label: '10 ms', attributes: { von_mises: '_VON_MISES_F1', displacement: '_DISPLACEMENT_F1' } },
    { value: 0.02, label: '20 ms', attributes: { von_mises: '_VON_MISES_F2', displacement: '_DISPLACEMENT_F2' } }] },
};
const transient = () => seriesResult(TIMES, { _displacement: up(0), _displacement_f1: up(0.001), _displacement_f2: up(0.002) },
  { _von_mises: [0, 0, 0, 0], _von_mises_f1: [10, 20, 30, 40], _von_mises_f2: [20, 40, 60, 90] });

describe('a series', () => {
  it('shows the frame the mode picker or the scrubber chose, else its own default', () => {
    expect(activeFrameIndex(modal())).toBe(0);
    expect(activeFrameIndex(modal(), { mode: '2' })).toBe(2);
    expect(activeFrameIndex(modal(), { mode: '7' })).toBe(0);
    expect(activeFrameIndex(transient())).toBe(2);
    // The scrubber snaps to the frame nearest it.
    expect(activeFrameIndex(transient(), { frame: 0.012 })).toBe(1);
    expect(activeFrameIndex(transient(), { frame: -1 })).toBe(0);
    // A result with no series is its one frame.
    expect(activeFrameIndex(seriesResult({ fields: TIMES.fields }, { _displacement: up(0) }, { _von_mises: [0, 1, 2, 3] }), { mode: '2' })).toBe(0);
  });

  it('reads each field and the deformation from the frame\'s own attributes, frame 0 from the field\'s', () => {
    const result = transient();
    const [stress] = result.fields;
    expect(frameAttribute(result, stress, 0)).toBe('_von_mises');
    expect(frameAttribute(result, stress, 2)).toBe('_von_mises_f2');
    // The same words and range: a per-frame field's range spans every frame.
    expect(fieldAtFrame(result, stress, 1)).toMatchObject({ attribute: '_von_mises_f1', name: 'von Mises stress', min: 0, max: 90 });
    expect(fieldAtFrame(result, stress, 0)).toBe(stress);
    expect(deformationAt(result, 2)).toEqual({ attribute: '_displacement_f2', imaginary: null });
    expect(deformationAt(result, 0)).toEqual({ attribute: '_displacement', imaginary: null });
    // A mode shape deforms its mode; mode 1's is the displacement the file baked in.
    expect(deformationAt(modal(), 1).attribute).toBe('_mode_shape_f1');
    expect(deformationAt(modal(), 0).attribute).toBe('_displacement');
    expect(activeFrame(modal(), { mode: '1' }, modal().fields[0])).toMatchObject({ index: 1, frame: { label: 'Mode 2 · 118 Hz' } });
    // A frame naming an attribute the file lacks reads the field's own; a temperature has nothing to deform by.
    const missing = seriesResult({ ...TIMES, series: { ...TIMES.series, frames: [TIMES.series.frames[0], { value: 1, attributes: { von_mises: '_NOPE' } }] } },
      {}, { _von_mises: [0, 1, 2, 3] });
    expect(frameAttribute(missing, missing.fields[0], 1)).toBe('_von_mises');
    expect(deformationAt(missing, 1).attribute).toBeNull();
  });

  it('turns a harmonic frame through its phase with its imaginary part', () => {
    const harmonic = seriesResult({ analysis: { type: 'harmonic' }, fields: [{ attribute: '_DISPLACEMENT', name: 'displacement', units: 'mm', min: 0, max: 1 }],
      series: { kind: 'frequency', unit: 'Hz', frames: [{ value: 50, label: '50 Hz', attributes: { displacement: '_DISPLACEMENT', displacement_im: '_DISPLACEMENT_IM_F0' } }] } },
    { _displacement: up(0.001), _displacement_im_f0: up(0.0005) });
    expect(deformationAt(harmonic, 0)).toEqual({ attribute: '_displacement', imaginary: '_displacement_im_f0' });
  });

  it('plays its frames in turn, each blended into the next', () => {
    expect(framesBetween(transient(), 0)).toEqual({ from: 0, to: 1, weight: 0 });
    expect(framesBetween(transient(), 0.25)).toEqual({ from: 0, to: 1, weight: 0.5 });
    expect(framesBetween(transient(), 1)).toEqual({ from: 1, to: 2, weight: 1 });
    expect(framesBetween(modal(), 0.5)).toEqual({ from: 1, to: 2, weight: 0 });
  });

  it('builds a mode picker over a series of modes and a scrubber over times, which snaps and says its frame', () => {
    expect(frameControl(modal())).toEqual({ id: 'mode', drives: 'mode', type: 'enum', label: 'Mode', defaultValue: '0',
      options: [{ value: '0', label: 'Mode 1 · 85 Hz' }, { value: '1', label: 'Mode 2 · 118 Hz' }, { value: '2', label: 'Mode 3 · 240 Hz' }] });
    // A view's default names a mode by its value.
    expect(frameControl(modal(), 'mode', { label: 'Which mode', default: 118.4 })).toMatchObject({ label: 'Which mode', defaultValue: '1' });
    const scrubber = frameControl(transient())!;
    expect(scrubber).toMatchObject({ id: 'frame', drives: 'frame', type: 'number', label: 'Time', min: 0, max: 0.02, defaultValue: 0.02, unit: 's' });
    expect(snapFrame(scrubber, 0.012)).toBe(0.01);
    expect(frameText(scrubber, 0.012)).toBe('10 ms');
    expect(frameText({ unit: 'MPa' }, 3)).toBeNull();
    expect(frameControl({ ...transient(), series: { ...transient().series!, kind: 'frequency' } })!.label).toBe('Frequency');
    expect(frameControl({ ...transient(), series: { ...transient().series!, unit: '%' } })!.label).toBe('Load step');
    expect(frameControl(seriesResult({ fields: TIMES.fields }, {}, { _von_mises: [0, 1, 2, 3] }))).toBeNull();
  });

  it('opens What you see as the analysis asks with no view: Mode and Deformation, Time, Field and Deformation, Field alone for a temperature', () => {
    expect(seriesControls(modal()).map((control: any) => control.id)).toEqual(['mode', 'deformation']);
    expect(seriesControls(transient()).map((control: any) => control.id)).toEqual(['frame', 'field', 'deformation']);
    const heat = seriesResult({ analysis: { type: 'thermal' }, fields: [{ attribute: '_TEMPERATURE', name: 'temperature', units: '°C', min: 20, max: 84, signed: true }] },
      {}, { _temperature: [20, 40, 60, 84] });
    expect(seriesControls(heat).map((control: any) => control.id)).toEqual(['field']);
  });

  it('shows a random vibration\'s RMS fields at 1σ or 3σ, opening on the level the study judges at', () => {
    const random = seriesResult({ analysis: { type: 'random_vibration' }, study: { sigma: 1 },
      fields: [{ attribute: '_VON_MISES_RMS', name: 'von Mises RMS', units: 'MPa', min: 0, max: 30 }] }, {}, { _von_mises_rms: [0, 10, 20, 30] });
    expect(sigmaControl(random)).toEqual({ id: 'sigma', drives: 'sigma', type: 'enum', label: 'Sigma', defaultValue: '1',
      options: [{ value: '1', label: '1σ' }, { value: '3', label: '3σ' }] });
    expect(seriesControls(random).map((control: any) => control.id)).toEqual(['field', 'sigma']);
    expect(sigmaControl({ ...random, study: null })!.defaultValue).toBe('3');
    expect(sigmaControl(transient())).toBeNull();
    expect([isRms(random.fields[0]), isRms({ attribute: '_von_mises_rms_f2' }), isRms(transient().fields[0])]).toEqual([true, true, false]);
    expect([sigmaScale(random.fields[0], '3'), sigmaScale(random.fields[0], 2), sigmaScale(transient().fields[0], 3)]).toEqual([3, 1, 1]);
  });
});
