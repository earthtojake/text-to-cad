import { BufferAttribute, BufferGeometry, Group, Mesh } from 'three';
import { describe, expect, it } from 'vitest';
import { feaControls, feaVerdict, readFeaResult, reynoldsWarning, studyRows } from '../../feaResult.js';
import { colourBarText } from '../../FeaColourBar.jsx';
import { coolantRows, cooledRows, flowRows, heatedRows, keptAtRows, madeOfRows } from '../setup.js';
import conjugateHeat, { COOLED_SETUP, cooledLimitWord } from './conjugate_heat.js';
import { feaAnalysis } from './index.js';

const LIMIT = 'Steady; the flow carries the heat but is not changed by it (no buoyancy, constant properties).';

// A cooled-by-flow result as cadgen writes one: the part's temperature first, the fluid's beside it, nothing deformed.
function cooledResult(analysis: Record<string, unknown> = {}, extras: Record<string, unknown> = {}) {
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new BufferAttribute(new Float32Array([0, 0, 0, 0.024, 0, 0, 0, 0.004, 0]), 3));
  geometry.setIndex([0, 1, 2]);
  geometry.setAttribute('color', new BufferAttribute(new Uint8Array(12), 4, true));
  geometry.setAttribute('_displacement', new BufferAttribute(new Float32Array(9), 3));
  geometry.setAttribute('_temperature', new BufferAttribute(new Float32Array([23.5, 24.1, 23.8]), 1));
  geometry.setAttribute('_fluid_temperature', new BufferAttribute(new Float32Array([20, 21.9, 21]), 1));
  geometry.setAttribute('_wall_heat_flux', new BufferAttribute(new Float32Array([4000, 2500, 3000]), 1));
  geometry.setAttribute('_heat_transfer_coefficient', new BufferAttribute(new Float32Array([1100, 1300, 1200]), 1));
  geometry.setAttribute('_pressure', new BufferAttribute(new Float32Array([0.48, 0, 0.24]), 1));
  geometry.setAttribute('_face', new BufferAttribute(new Float32Array([0, 0, 1]), 1));
  const mesh = new Mesh(geometry);
  Object.assign(mesh.userData, {
    generator: 'cadgen fea', name: 'cold plate cooled by flow', deformation_scale: null, faces: ['#o1.f3', '#o1.f7'], occurrence: '#o1',
    analysis: { type: 'conjugate_heat', tier: 3, word: 'Cooled by flow', estimate: false, limits: [LIMIT], noun: 'this heat',
      reference_C: 20, warnings: [], reynolds: { value: 39.85, limit: 2000, kind: 'internal', length_mm: 4 }, regime: 'laminar', ...analysis },
    fields: [
      { attribute: '_TEMPERATURE', name: 'temperature', units: '°C', min: 23.48, max: 24.15, attribute_scale: 1, field: 'temperature', signed: true },
      { attribute: '_FLUID_TEMPERATURE', name: 'fluid temperature', units: '°C', min: 20, max: 21.9, attribute_scale: 1, field: 'fluid_temperature', signed: true },
      { attribute: '_WALL_HEAT_FLUX', name: 'heat into the flow', units: 'W/m²', min: 0, max: 4000, attribute_scale: 1, field: 'wall_heat_flux', signed: true },
      { attribute: '_HEAT_TRANSFER_COEFFICIENT', name: 'heat transfer coefficient', units: 'W/m²K', min: 0, max: 1300, attribute_scale: 1, field: 'heat_transfer_coefficient' },
      { attribute: '_PRESSURE', name: 'wall pressure', units: 'Pa', min: 0, max: 0.48, attribute_scale: 1, field: 'pressure', signed: true },
    ],
    study: {
      material: { name: 'Aluminum 6061-T6', yield_MPa: 276 },
      flow: { kind: 'internal', regime: 'auto', fluid: { name: 'water', density_kg_m3: 998.2, viscosity_Pa_s: 0.001002, conductivity_W_mK: 0.606, specific_heat_J_kgK: 4181 },
        inlets: [{ opening: 'x_min', velocity_m_s: 0.01, profile: 'developed', temperature_C: 20 }], outlets: [{ opening: 'x_max', pressure_Pa: 0 }] },
      temperatures: [], heat: [{ faces: ['#o1.f3'], W: 1 }], convection: [],
      mesh: { size_mm: 0.75, order: 2, elements: 100, refined_from_mm: null },
    },
    checks: [{ kind: 'temperature', label: 'Heat', value: 24.15, limit: 60, unit: '°C', ratio: (24.15 - 20) / 40, close_at: 0.9,
      status: 'passes', where: { ref: '#o1.f3', at: [24, 0, 4] }, reference: 20 }],
    findings: [],
    ...extras,
  });
  const root = new Group();
  root.add(mesh);
  return readFeaResult(root)!;
}

describe('conjugate_heat', () => {
  it('is Cooled by flow, Tier 3: judged by the hottest point, the drop and the speed, with no routine', () => {
    expect(conjugateHeat).toMatchObject({ name: 'conjugate_heat', tier: 3, word: 'Cooled by flow', noun: 'this heat', family: null,
      scalesWithLoad: false, checks: ['temperature', 'pressure_drop', 'velocity'], displayTitle: 'Flow openings and heat' });
    expect(conjugateHeat.markers).toEqual(['inlet', 'outlet', 'heat', 'temperature', 'convection']);
    expect(conjugateHeat.routine(cooledResult())).toBeNull();
    expect(feaAnalysis(cooledResult())).toBe(conjugateHeat);
  });

  it('opens on the field alone, temperature first, the fluid temperature among the options', () => {
    const controls = feaControls(cooledResult());
    expect(controls.map((control: { drives: string }) => control.drives)).toEqual(['field']);
    expect(controls[0].options).toEqual([
      { value: '_temperature', label: 'Temperature' }, { value: '_fluid_temperature', label: 'Fluid temperature' },
      { value: '_wall_heat_flux', label: 'Heat into the flow' }, { value: '_heat_transfer_coefficient', label: 'Heat transfer coefficient' },
      { value: '_pressure', label: 'Pressure' }]);
    expect(controls[0].defaultValue).toBe('_temperature');
    // Its colour bar says the field's word and its scale.
    expect(colourBarText({ attribute: '_fluid_temperature', name: 'fluid temperature', units: '°C', min: 20, max: 21.9 }))
      .toEqual({ word: 'Fluid temperature', min: '20.0', max: '21.9 °C' });
  });

  it('sets up as flow in/out, the coolant at its temperature, heated, kept at, cooled by air, made of', () => {
    expect(conjugateHeat.setupGroups).toBe(COOLED_SETUP);
    expect(COOLED_SETUP).toEqual([flowRows, coolantRows, heatedRows, keptAtRows, cooledRows, madeOfRows]);
    const result = cooledResult();
    expect(result.study.flow).toMatchObject({ fluid: 'water', regime: 'auto' });
    expect(result.study.flow.inlets[0]).toMatchObject({ opening: 'x_min', speed: 0.01, temperatureC: 20 });
    const rows = studyRows(result);
    expect(rows.slice(0, 4).map((row: { label: string }) => row.label)).toEqual(['Flow in/out', 'Coolant', 'Heated', 'Made of']);
    expect(rows[1].children[0]).toMatchObject({ label: 'Water in at 20 °C', hint: 'At the low X side', summary: 'Water in at 20 °C at the low X side' });
    expect(rows[2].children[0]).toMatchObject({ label: '1 W', summary: '1 W of heat into face 3' });
    // A plain flow (no inlet temperature) has no Coolant row.
    expect(coolantRows({ ...result, study: { ...result.study, flow: { ...result.study.flow, inlets: [{ opening: 'x_min', speed: 1, velocity: null, temperatureC: null }] } } })).toEqual([]);
  });

  it('leads its takeaway with the flow model it solved, and says the hottest point against its limit', () => {
    expect(cooledLimitWord(cooledResult())).toBe('Laminar');
    expect(cooledLimitWord(cooledResult({ regime: 'turbulent' }))).toBe('Turbulent');
    expect(cooledLimitWord(cooledResult({ regime: undefined }))).toBe('Flow');
    const verdict = feaVerdict(cooledResult());
    expect(verdict.title).toBe('Cool enough');
    expect(verdict.caption).toContain('Laminar · ');
    expect(verdict.caption).toContain('Hottest 24 °C, 36 °C under its limit');
    // The laminar flow solver's Reynolds warning is cfd's alone.
    expect(reynoldsWarning(cooledResult({ reynolds: { value: 4000, limit: 2000, kind: 'internal' } }))).toBeNull();
    expect(feaVerdict(cooledResult({ regime: 'turbulent' })).caption).toContain('Turbulent · ');
  });
});
