import { BufferAttribute, BufferGeometry, Group, Mesh } from 'three';
import { describe, expect, it } from 'vitest';
import { feaControls, feaVerdict, readFeaResult, studyRows } from '../../feaResult.js';
import { flowRows, heldRows, madeOfRows } from '../setup.js';
import fsi, { FSI_SETUP, bentRows, couplingOf } from './fsi.js';
import { feaAnalysis } from './index.js';

const LIMIT = 'Steady flow two-way coupled to a linear elastic part: no flutter, vortex shedding or other unsteady '
  + 'motion; small-to-moderate deflection, the flow mesh following the part (ALE mesh motion).';

// A flow-and-bending result as cadgen writes one: stress first, the wall pressure and shear beside it, deformed.
function fsiResult(coupling: Record<string, unknown> = {}, analysis: Record<string, unknown> = {}) {
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new BufferAttribute(new Float32Array([0, 0, 0, 0.012, 0, 0, 0, 0.003, 0]), 3));
  geometry.setIndex([0, 1, 2]);
  geometry.setAttribute('color', new BufferAttribute(new Uint8Array(12), 4, true));
  geometry.setAttribute('_von_mises', new BufferAttribute(new Float32Array([0.27, 0.01, 0.1]), 1));
  geometry.setAttribute('_displacement', new BufferAttribute(new Float32Array([0, 0, 0, 0, 0, 0, 0.0005, 0, 0]), 3));
  geometry.setAttribute('_pressure', new BufferAttribute(new Float32Array([1400, 0, 700]), 1));
  geometry.setAttribute('_wall_shear', new BufferAttribute(new Float32Array([20, 20, 20]), 1));
  geometry.setAttribute('_face', new BufferAttribute(new Float32Array([0, 0, 0]), 1));
  const mesh = new Mesh(geometry);
  Object.assign(mesh.userData, {
    generator: 'cadgen fea', name: 'flap flow and bending', deformation_scale: 5, safety_factor: 3.7, faces: ['#o1.f4', '#o1.f9'],
    occurrence: '#o1',
    analysis: { type: 'fsi', tier: 3, word: 'Flow and bending', estimate: false, limits: [LIMIT], noun: 'this flow', reference_C: null,
      warnings: [], regime: 'laminar', reynolds: { value: 0.25, limit: 2000, kind: 'internal', laminar: true },
      coupling: { iterations: 4, converged: true, residual: 2.2e-5, tolerance: 0.001, method: 'aitken', ...coupling }, ...analysis },
    fields: [
      { attribute: '_VON_MISES', name: 'von Mises stress', units: 'MPa', min: 0, max: 0.27, attribute_scale: 1, field: 'von_mises' },
      { attribute: '_PRESSURE', name: 'wall pressure', units: 'Pa', min: 0, max: 1400, attribute_scale: 1, field: 'pressure', signed: true },
      { attribute: '_WALL_SHEAR', name: 'wall shear stress', units: 'Pa', min: 0, max: 20, attribute_scale: 1, field: 'wall_shear' },
      { attribute: '_DISPLACEMENT', name: 'displacement', units: 'mm', min: 0, max: 0.5, attribute_scale: 1000, field: 'displacement' },
    ],
    study: {
      material: { name: 'soft', yield_MPa: 1 },
      fixtures: [{ type: 'fixed', faces: ['#o1.f9'] }], loads: [],
      flow: { kind: 'internal', regime: 'auto', fluid: { name: 'water', density_kg_m3: 998.2, viscosity_Pa_s: 0.001002 },
        inlets: [{ opening: 'x_min', velocity_m_s: 0.5, profile: 'developed' }], outlets: [{ opening: 'x_max', pressure_Pa: 0 }] },
      coupling: { method: 'aitken', relaxation: 1, tolerance: 0.001, max_iterations: 25 },
      mesh: { size_mm: 0.8, order: 2, elements: 4721, refined_from_mm: null },
    },
    checks: [
      { kind: 'stress', label: 'Strength', value: 0.27, limit: 1, unit: 'MPa', ratio: 0.27, close_at: 0.8, status: 'passes',
        where: { ref: '#o1.f4', at: [4, 0, 0.5] } },
      { kind: 'pressure_drop', label: 'Flow resistance', value: 1412, limit: 5000, unit: 'Pa', ratio: 0.28, close_at: 0.9,
        status: 'passes', where: { ref: null, at: [0, 0, 0] } },
    ],
    findings: [],
  });
  const root = new Group();
  root.add(mesh);
  return readFeaResult(root)!;
}

describe('fsi', () => {
  it('is Flow and bending, Tier 3: judged by stress, displacement and drop, of no static family, with no routine', () => {
    expect(fsi).toMatchObject({ name: 'fsi', tier: 3, word: 'Flow and bending', noun: 'this flow', family: null, scalesWithLoad: false,
      checks: ['stress', 'displacement', 'pressure_drop'], displayTitle: 'Flow openings and fixtures' });
    expect(fsi.markers).toEqual(['inlet', 'outlet', 'fixture']);
    expect(fsi.routine(fsiResult())).toBeNull();
    expect(feaAnalysis(fsiResult())).toBe(fsi);
  });

  it('opens on the field, stress and pressure among its options, and the deformation', () => {
    const controls = feaControls(fsiResult());
    expect(controls.map((control: { drives: string }) => control.drives)).toEqual(['field', 'deformation']);
    expect(controls[0].options.map((option: { value: string }) => option.value))
      .toEqual(['_von_mises', '_pressure', '_wall_shear', '_displacement']);
    expect(controls[0].options.slice(0, 2).map((option: { label: string }) => option.label)).toEqual(['Stress', 'Pressure']);
  });

  it('sets up as what bends it, flow in/out, held at and made of', () => {
    expect(fsi.setupGroups).toEqual(FSI_SETUP);
    expect(FSI_SETUP).toEqual([bentRows, flowRows, heldRows, madeOfRows]);
    const rows = studyRows(fsiResult());
    expect(rows[0]).toMatchObject({ id: 'bent', label: 'Bent by the flow' });
    expect(rows[0].children[0]).toMatchObject({ label: 'Water at 0.5 m/s bends the flap', refs: ['#o1'] });
    expect(rows[0].children[0].summary).toContain('two-way');
    expect(rows.map((row: { label: string }) => row.label).slice(0, 4)).toEqual(['Bent by the flow', 'Flow in/out', 'Held at', 'Made of']);
  });

  it('says the coupling iterations in Details, and its limits', () => {
    expect(couplingOf(fsiResult())).toEqual({ iterations: 4, converged: true, residual: 2.2e-5, tolerance: 0.001, method: 'aitken' });
    const details = studyRows(fsiResult()).find((row: { id: string }) => row.id === 'details');
    const coupling = details.children.find((row: { id: string }) => row.id === 'coupling');
    expect(coupling).toMatchObject({ label: 'Coupling: settled in 4 iterations', hint: 'Last change 2.2e-5 of itself' });
    expect(JSON.stringify(details)).toContain(LIMIT);
  });

  it('leads its verdict with the regime, and says plainly when the coupling did not settle', () => {
    const settled = feaVerdict(fsiResult());
    expect(settled.caption.startsWith('Laminar · ')).toBe(true);
    expect(settled.caption).not.toContain('not converged');
    const loose = fsiResult({ iterations: 25, converged: false, residual: 0.018 });
    expect(feaVerdict(loose).caption.startsWith('Laminar · not converged · ')).toBe(true);
    const details = studyRows(loose).find((row: { id: string }) => row.id === 'details');
    const coupling = details.children.find((row: { id: string }) => row.id === 'coupling');
    expect(coupling.label).toBe('Coupling: did not settle in 25 iterations');
    expect(coupling.hint).toBe('Still changing by 1.8e-2, short of 1e-3: the last state, not an answer');
    expect(feaVerdict(fsiResult({}, { regime: 'turbulent' })).caption.startsWith('Turbulent · ')).toBe(true);
  });
});
