import { BufferAttribute, BufferGeometry, Group, Mesh } from 'three';
import { describe, expect, it } from 'vitest';
import { feaControls, feaVerdict, readFeaResult, recolorByField, studyRows } from '../../feaResult.js';
import { cooledRows, heatedRows, keptAtRows, madeOfRows, radiatesRows } from '../setup.js';
import { feaAnalysis } from './index.js';
import thermal, { HEAT_MARKERS, HEAT_SETUP } from './thermal.js';

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

describe('thermal', () => {
  it('is Heat: judged by temperature, not by the load, of no static family, with no routine', () => {
    expect(thermal).toMatchObject({ name: 'thermal', tier: 1, word: 'Heat', noun: 'this heat', family: null, scalesWithLoad: false,
      checks: ['temperature'], displayTitle: 'Heat inputs and temperatures' });
    expect(thermal.markers).toEqual(HEAT_MARKERS);
    expect(HEAT_MARKERS).toEqual(['temperature', 'heat', 'convection']);
    expect(thermal.routine(heatResult())).toBeNull();
    expect(feaAnalysis(heatResult())).toBe(thermal);
  });

  it('opens on the field alone, temperature first, with no deformation to draw', () => {
    const controls = feaControls(heatResult());
    expect(controls.map((control: { drives: string }) => control.drives)).toEqual(['field']);
    expect(controls[0].options).toEqual([{ value: '_temperature', label: 'Temperature' }, { value: '_heat_flux', label: 'Heat flow' }]);
    expect(controls[0].defaultValue).toBe('_temperature');
  });

  it('sets up as kept at, heated, cooled by air, made of', () => {
    expect(thermal.setupGroups).toEqual(HEAT_SETUP);
    expect(HEAT_SETUP).toEqual([keptAtRows, heatedRows, cooledRows, radiatesRows, madeOfRows]);
    const rows = studyRows(heatResult());
    expect(rows.slice(0, 4).map((row: { label: string }) => row.label)).toEqual(['Kept at', 'Heated', 'Cooled by air', 'Made of']);
    expect(rows[0].children[0]).toMatchObject({ label: '25 °C', summary: 'Kept at 25 °C on face 1' });
    expect(rows[1].children[0]).toMatchObject({ label: '15 W', summary: '15 W of heat into face 7' });
    expect(rows[2].children[0]).toMatchObject({ label: 'Air at 25 °C', hint: 'Heat transfer coefficient 10 W/m²K' });
  });

  it('says where it radiates: to the surroundings at a temperature, with its emissivity, and to other faces', () => {
    const study = {
      material: { name: 'Aluminum 6061-T6', yield_MPa: 276 },
      temperatures: [{ faces: ['#o1.f1'], C: 25 }], heat: [], convection: [],
      radiation: [{ faces: ['#o1.f7'], emissivity: 0.9, ambient_C: 25 }, { faces: ['#o1.f1', '#o1.f7'], emissivity: 0.8, ambient_C: 40, surface_to_surface: true }],
      mesh: { size_mm: 2, order: 2, elements: 100, refined_from_mm: null },
    };
    const result = heatResult({ study });
    expect(result.study.radiation).toEqual([
      { faces: ['#o1.f7'], emissivity: 0.9, ambientC: 25, surfaceToSurface: false },
      { faces: ['#o1.f1', '#o1.f7'], emissivity: 0.8, ambientC: 40, surfaceToSurface: true },
    ]);
    const rows = studyRows(result);
    expect(rows.slice(0, 3).map((row: { label: string }) => row.label)).toEqual(['Kept at', 'Radiation', 'Made of']);
    expect(rows[1].children[0]).toMatchObject({ label: 'Radiates to 25 °C, emissivity 0.9', summary: 'Radiates to 25 °C (emissivity 0.9) from face 7' });
    expect(rows[1].children[0].hint).toBeUndefined();
    expect(rows[1].children[1]).toMatchObject({ label: 'Radiates to 40 °C, emissivity 0.8', hint: 'And to the other faces that radiate to each other' });
    // A study with none has no Radiation row.
    expect(studyRows(heatResult()).some((row: { label: string }) => row.label === 'Radiation')).toBe(false);
  });

  it('says the hottest point against its limit, with no "No stress" and no load multiple', () => {
    const verdict = feaVerdict(heatResult());
    expect(verdict.title).toBe('Cool enough');
    expect(verdict.caption).toContain('Hottest 84 °C, 16 °C under its limit');
    expect(JSON.stringify(verdict)).not.toContain('No stress');
    const hot = feaVerdict(heatResult({ checks: [{ kind: 'temperature', label: 'Chip side', value: 112, limit: 100, unit: '°C',
      ratio: (112 - 25) / 75, close_at: 0.9, status: 'fails', where: { ref: '#o1.f7', at: [1, 2, 3] }, reference: 25 }] }));
    expect(hot.title).toBe('Runs too hot');
    expect(hot.caption).toContain('12 °C over its limit');
  });

  it('reads and colours by its own listed fields, with no _von_mises in the file', () => {
    // cadgen writes a thermal GLB with no stress copy: only the attributes extras.fields lists.
    const { mesh } = heatResult();
    mesh.geometry.deleteAttribute('_von_mises');
    const root = new Group();
    root.add(mesh);
    const result = readFeaResult(root)!;
    expect(result.fields.map((field: { attribute: string }) => field.attribute)).toEqual(['_temperature', '_heat_flux']);
    expect(feaControls(result)[0].defaultValue).toBe('_temperature');
    expect(recolorByField(mesh, result.fields[0])).toBe(true);
    const colours = Array.from(mesh.geometry.getAttribute('color').array as Uint8Array);
    // 25 °C is the ramp's blue end, 84 °C its red end.
    expect(colours.slice(0, 3)).toEqual([13, 26, 230]);
    expect(colours.slice(8, 11)).toEqual([230, 20, 13]);
  });
});
