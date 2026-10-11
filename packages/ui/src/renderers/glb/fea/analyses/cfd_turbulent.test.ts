import { BufferAttribute, BufferGeometry, Group, Mesh } from 'three';
import { describe, expect, it } from 'vitest';
import { feaControls, feaVerdict, readFeaResult, reynoldsWarning, studyRows } from '../../feaResult.js';
import { FLOW_SETUP } from './cfd.js';
import cfdTurbulent from './cfd_turbulent.js';
import { feaAnalysis } from './index.js';

const LIMIT = 'Steady RANS (k-omega SST), wall functions, incompressible';

// A turbulent flow result as cadgen writes one: wall pressure first, wall shear beside it, nothing deformed.
function turbulentResult(analysis: Record<string, unknown> = {}, extras: Record<string, unknown> = {}) {
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new BufferAttribute(new Float32Array([0, 0, 0, 0.015, 0, 0, 0, 0.005, 0]), 3));
  geometry.setIndex([0, 1, 2]);
  geometry.setAttribute('color', new BufferAttribute(new Uint8Array(12), 4, true));
  geometry.setAttribute('_displacement', new BufferAttribute(new Float32Array(9), 3));
  geometry.setAttribute('_pressure', new BufferAttribute(new Float32Array([23.6, 0, 11.8]), 1));
  geometry.setAttribute('_wall_shear', new BufferAttribute(new Float32Array([3.7, 3.7, 3.7]), 1));
  geometry.setAttribute('_face', new BufferAttribute(new Float32Array([0, 0, 0]), 1));
  const mesh = new Mesh(geometry);
  Object.assign(mesh.userData, {
    generator: 'cadgen fea', name: 'tube turbulent flow', deformation_scale: null, faces: ['#o1.f4'], occurrence: '#o1',
    analysis: { type: 'cfd_turbulent', tier: 3, word: 'Turbulent flow', estimate: false, limits: [LIMIT], noun: 'this flow',
      reference_C: null, warnings: [], turbulence: { model: 'k-omega SST', reynolds: 10000, kind: 'internal', viscosity_ratio_max: 89.6 },
      ...analysis },
    fields: [
      { attribute: '_PRESSURE', name: 'wall pressure', units: 'Pa', min: 0, max: 23.6, attribute_scale: 1, field: 'pressure', signed: true },
      { attribute: '_WALL_SHEAR', name: 'wall shear stress', units: 'Pa', min: 0, max: 3.7, attribute_scale: 1, field: 'wall_shear' },
    ],
    study: {
      flow: { kind: 'internal', fluid: { name: 'water', density_kg_m3: 998.2, viscosity_Pa_s: 0.001002 },
        inlets: [{ opening: 'x_min', velocity_m_s: 1.0, profile: 'developed', turbulence_intensity: 0.05 }],
        outlets: [{ opening: 'x_max', pressure_Pa: 0 }] },
      mesh: { size_mm: 1, order: 2, elements: 100, refined_from_mm: null },
    },
    checks: [{ kind: 'pressure_drop', label: 'Flow resistance', value: 23.6, limit: 50, unit: 'Pa', ratio: 0.47, close_at: 0.9,
      status: 'passes', where: { ref: null, at: [0, 0, 0] } }],
    findings: [],
    ...extras,
  });
  const root = new Group();
  root.add(mesh);
  return readFeaResult(root)!;
}

describe('cfd_turbulent', () => {
  it('is Turbulent flow, Tier 3 and RANS: judged by drop and speed, of no static family, with no routine', () => {
    expect(cfdTurbulent).toMatchObject({ name: 'cfd_turbulent', tier: 3, word: 'Turbulent flow', noun: 'this flow', limitWord: 'RANS',
      family: null, scalesWithLoad: false, checks: ['pressure_drop', 'velocity', 'stress', 'displacement'], displayTitle: 'Flow openings' });
    expect(cfdTurbulent.markers).toEqual(['inlet', 'outlet', 'fixture']);
    expect(cfdTurbulent.routine(turbulentResult())).toBeNull();
    expect(feaAnalysis(turbulentResult())).toBe(cfdTurbulent);
  });

  it('opens on the field alone, pressure first, and sets up as Flow does', () => {
    const controls = feaControls(turbulentResult());
    expect(controls.map((control: { drives: string }) => control.drives)).toEqual(['field']);
    expect(controls[0].options).toEqual([{ value: '_pressure', label: 'Pressure' }, { value: '_wall_shear', label: 'Wall shear' }]);
    expect(cfdTurbulent.setupGroups).toEqual(FLOW_SETUP);
    const rows = studyRows(turbulentResult());
    expect(rows[0].label).toBe('Flow in/out');
    expect(rows[0].children.map((row: { label: string }) => row.label)).toEqual(['In 1 m/s at the low X side', 'Out at 0 Pa, the high X side']);
  });

  it('leads its verdict with "RANS · ", says its limits in Details, and never warns as the laminar solver does', () => {
    const verdict = feaVerdict(turbulentResult());
    expect(verdict.title).toBe('Flows freely');
    expect(verdict.caption.startsWith('RANS · ')).toBe(true);
    expect(verdict.caption).not.toContain('unreliable');
    const details = studyRows(turbulentResult()).find((row: { id: string }) => row.id === 'details');
    expect(JSON.stringify(details)).toContain(LIMIT);
    expect(reynoldsWarning(turbulentResult({ reynolds: { value: 10000, limit: 2000, kind: 'internal' } }))).toBeNull();
  });
});
