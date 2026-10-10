import { BufferAttribute, BufferGeometry, Group, Mesh } from 'three';
import { describe, expect, it } from 'vitest';
import { feaControls, readFeaResult, studyRows } from '../../feaResult.js';
import { activeFrameIndex } from '../series.js';
import { feaAnalysis } from './index.js';
import { HEAT_MARKERS, HEAT_SETUP } from './thermal.js';
import thermalTransient, { PLAY, fieldAndTime } from './thermal_transient.js';

// A steady heat result as cadgen writes one: temperature first, heat flow beside it, nothing deformed.
function heatResult(extras: Record<string, unknown> = {}) {
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new BufferAttribute(new Float32Array([0, 0, 0, 0.01, 0, 0, 0, 0.01, 0]), 3));
  geometry.setIndex([0, 1, 2]);
  geometry.setAttribute('color', new BufferAttribute(new Uint8Array(12), 4, true));
  geometry.setAttribute('_von_mises', new BufferAttribute(new Float32Array([25, 60, 84]), 1));
  geometry.setAttribute('_displacement', new BufferAttribute(new Float32Array(9), 3));
  geometry.setAttribute('_temperature', new BufferAttribute(new Float32Array([25, 60, 84]), 1));
  geometry.setAttribute('_heat_flux', new BufferAttribute(new Float32Array([0, 900, 2000]), 1));
  geometry.setAttribute('_face', new BufferAttribute(new Float32Array([0, 0, 1]), 1));
  const mesh = new Mesh(geometry);
  Object.assign(mesh.userData, {
    generator: 'cadgen fea', name: 'plate temperature', deformation_scale: null, faces: ['#o1.f1', '#o1.f7'],
    analysis: { type: 'thermal', tier: 1, word: 'Heat', estimate: false, limits: [], noun: 'this heat', reference_C: 25, warnings: [] },
    fields: [
      { attribute: '_TEMPERATURE', name: 'temperature', units: '°C', min: 25, max: 84, attribute_scale: 1, field: 'temperature', signed: true },
      { attribute: '_HEAT_FLUX', name: 'heat flux', units: 'W/m²', min: 0, max: 2000, attribute_scale: 1, field: 'heat_flux' },
    ],
    study: {
      material: { name: 'Aluminum 6061-T6', yield_MPa: 276 },
      temperatures: [{ faces: ['#o1.f1'], C: 25 }],
      heat: [{ faces: ['#o1.f7'], W: 15 }],
      convection: [{ faces: ['#o1.f3', '#o1.f4'], h_W_m2K: 10, ambient_C: 25 }],
      mesh: { size_mm: 2, order: 2, elements: 100, refined_from_mm: null },
    },
    checks: [{ kind: 'temperature', label: 'Chip side', value: 84, limit: 100, unit: '°C', ratio: (84 - 25) / (100 - 25), close_at: 0.9,
      status: 'passes', where: { ref: '#o1.f7', at: [1, 2, 3] }, faces: ['#o1.f7'], reference: 25 }],
    findings: [],
    ...extras,
  });
  const root = new Group();
  root.add(mesh);
  return readFeaResult(root)!;
}

// Heat over time as cadgen writes it: frame 0 (t = 0) in the fields' own attributes, the hottest frame the default.
function overTime() {
  const result = heatResult({
    analysis: { type: 'thermal_transient', tier: 1, word: 'Heat over time', estimate: false, limits: [], noun: 'this heat', reference_C: 20, warnings: [] },
    fields: [
      { attribute: '_TEMPERATURE', name: 'temperature', units: '°C', min: 20, max: 84, attribute_scale: 1, field: 'temperature', signed: true, per_frame: true },
      { attribute: '_HEAT_FLUX', name: 'heat flux', units: 'W/m²', min: 0, max: 2000, attribute_scale: 1, field: 'heat_flux', per_frame: true },
    ],
    series: { kind: 'time', unit: 's', default: 2, frames: [
      { value: 0, label: '0 s', attributes: { temperature: '_TEMPERATURE', heat_flux: '_HEAT_FLUX' } },
      { value: 300, label: '5 min', attributes: { temperature: '_TEMPERATURE_F1', heat_flux: '_HEAT_FLUX_F1' } },
      { value: 301, label: '5.02 min', attributes: { temperature: '_TEMPERATURE_F2', heat_flux: '_HEAT_FLUX_F2' } },
      { value: 600, label: '10 min', attributes: { temperature: '_TEMPERATURE_F3', heat_flux: '_HEAT_FLUX_F3' } }] },
    checks: [{ kind: 'temperature', label: 'Heat', value: 84, limit: 85, unit: '°C', ratio: 64 / 65, close_at: 0.9, status: 'close',
      where: { ref: null, at: [1, 2, 3] }, reference: 20, at: { frame: 2, value: 301, unit: 's', time_s: 301 } }],
  });
  const geometry = result.mesh.geometry;
  for (const [index, top] of [[1, 70], [2, 84], [3, 40]]) {
    geometry.setAttribute(`_temperature_f${index}`, new BufferAttribute(new Float32Array([20, top - 10, top]), 1));
    geometry.setAttribute(`_heat_flux_f${index}`, new BufferAttribute(new Float32Array([0, 500, 1000]), 1));
  }
  return result;
}

describe('thermal_transient', () => {
  it('is Heat over time: judged by temperature, playing its frames, with the steady analysis\'s setup and markers', () => {
    expect(thermalTransient).toMatchObject({ name: 'thermal_transient', word: 'Heat over time', family: null, scalesWithLoad: false,
      checks: ['temperature'], displayTitle: 'Heat inputs and temperatures' });
    expect(thermalTransient.setupGroups).toBe(HEAT_SETUP);
    expect(thermalTransient.markers).toBe(HEAT_MARKERS);
    expect(feaAnalysis(overTime())).toBe(thermalTransient);
    expect(thermalTransient.routine(overTime())).toBe(PLAY);
    expect(PLAY).toEqual({ id: 'fea:play', label: 'Play', kind: 'play' });
    expect(thermalTransient.routine({ series: null })).toBeNull();
  });

  it('opens on the field and a time scrubber that snaps to the frames, on the hottest', () => {
    const result = overTime();
    const [field, time] = feaControls(result);
    expect(field).toMatchObject({ drives: 'field', defaultValue: '_temperature' });
    expect(time).toMatchObject({ drives: 'frame', type: 'number', label: 'Time', min: 0, max: 600, defaultValue: 301, unit: 's',
      snaps: [0, 300, 301, 600], frameLabels: ['0 s', '5 min', '5.02 min', '10 min'] });
    expect(activeFrameIndex(result)).toBe(2);
    expect(activeFrameIndex(result, { frame: 590 })).toBe(3);
  });

  it('shows the field alone for a result with no frames to scrub', () => {
    expect(fieldAndTime(heatResult()).map((control: { drives: string }) => control.drives)).toEqual(['field']);
  });

  it('keeps the check\'s moment, so choosing it can jump there, and its setup reads the heat', () => {
    const result = overTime();
    expect(result.checks[0].at).toMatchObject({ frame: 2, value: 301 });
    expect(studyRows(result).slice(0, 3).map((row: { label: string }) => row.label)).toEqual(['Kept at', 'Heated', 'Cooled by air']);
  });
});
