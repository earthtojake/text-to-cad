import { BufferAttribute, BufferGeometry, Group, Mesh } from 'three';
import { describe, expect, it } from 'vitest';
import { feaControls, feaVerdict, readFeaResult, reynoldsWarning, studyRows } from '../../feaResult.js';
import { flowRows, heldRows, madeOfRows } from '../setup.js';
import cfd, { FLOW_SETUP } from './cfd.js';
import { feaAnalysis } from './index.js';

const LIMIT = 'Laminar, steady, incompressible; no turbulence model.';
const PAST = 'Re 2391 is past the laminar range (laminar above Re 2000 is unreliable): real flow is likely turbulent, '
  + 'so this pressure drop is a lower bound and the flow pattern may be wrong';

// A flow result as cadgen writes one: wall pressure first, wall shear beside it, nothing deformed.
function flowResult(analysis: Record<string, unknown> = {}, extras: Record<string, unknown> = {}) {
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new BufferAttribute(new Float32Array([0, 0, 0, 0.016, 0, 0, 0, 0.002, 0]), 3));
  geometry.setIndex([0, 1, 2]);
  geometry.setAttribute('color', new BufferAttribute(new Uint8Array(12), 4, true));
  geometry.setAttribute('_displacement', new BufferAttribute(new Float32Array(9), 3));
  geometry.setAttribute('_pressure', new BufferAttribute(new Float32Array([0.32, 0, 0.16]), 1));
  geometry.setAttribute('_wall_shear', new BufferAttribute(new Float32Array([0.02, 0.02, 0.02]), 1));
  geometry.setAttribute('_face', new BufferAttribute(new Float32Array([0, 0, 0]), 1));
  const mesh = new Mesh(geometry);
  Object.assign(mesh.userData, {
    generator: 'cadgen fea', name: 'tube flow', deformation_scale: null, faces: ['#o1.f4'], occurrence: '#o1',
    analysis: { type: 'cfd', tier: 3, word: 'Flow', estimate: false, limits: [LIMIT], noun: 'this flow', reference_C: null, warnings: [],
      ...analysis },
    fields: [
      { attribute: '_PRESSURE', name: 'wall pressure', units: 'Pa', min: 0, max: 0.32, attribute_scale: 1, field: 'pressure', signed: true },
      { attribute: '_WALL_SHEAR', name: 'wall shear stress', units: 'Pa', min: 0, max: 0.02, attribute_scale: 1, field: 'wall_shear' },
    ],
    study: {
      flow: { kind: 'internal', fluid: { name: 'water', density_kg_m3: 998.2, viscosity_Pa_s: 0.001002 },
        inlets: [{ opening: 'x_min', velocity_m_s: 0.5, profile: 'developed' }], outlets: [{ opening: 'x_max', pressure_Pa: 0 }] },
      mesh: { size_mm: 1, order: 2, elements: 100, refined_from_mm: null },
    },
    checks: [{ kind: 'pressure_drop', label: 'Flow resistance', value: 820, limit: 1000, unit: 'Pa', ratio: 0.82, close_at: 0.9,
      status: 'passes', where: { ref: null, at: [0, 0, 0] } }],
    findings: [],
    ...extras,
  });
  const root = new Group();
  root.add(mesh);
  return readFeaResult(root)!;
}

describe('cfd', () => {
  it('is Flow, Tier 3 and Laminar: judged by drop and speed, of no static family, with no routine', () => {
    expect(cfd).toMatchObject({ name: 'cfd', tier: 3, word: 'Flow', noun: 'this flow', limitWord: 'Laminar', family: null,
      scalesWithLoad: false, checks: ['pressure_drop', 'velocity', 'stress', 'displacement'], displayTitle: 'Flow openings' });
    expect(cfd.markers).toEqual(['inlet', 'outlet', 'fixture']);
    expect(cfd.routine(flowResult())).toBeNull();
    expect(feaAnalysis(flowResult())).toBe(cfd);
  });

  it('opens on the field alone, pressure first, when nothing deforms', () => {
    const controls = feaControls(flowResult());
    expect(controls.map((control: { drives: string }) => control.drives)).toEqual(['field']);
    expect(controls[0].options).toEqual([{ value: '_pressure', label: 'Pressure' }, { value: '_wall_shear', label: 'Wall shear' }]);
    const mapped = flowResult({}, { fields: [
      { attribute: '_PRESSURE', name: 'wall pressure', units: 'Pa', min: 0, max: 0.32, attribute_scale: 1, field: 'pressure', signed: true },
      { attribute: '_DISPLACEMENT', name: 'displacement', units: 'mm', min: 0, max: 0.001, attribute_scale: 1000, field: 'displacement' },
    ], deformation_scale: 1000 });
    expect(feaControls(mapped).map((control: { drives: string }) => control.drives)).toEqual(['field', 'deformation']);
  });

  it('sets up as flow in/out, then held and made of when mapped onto the structure', () => {
    expect(cfd.setupGroups).toEqual(FLOW_SETUP);
    expect(FLOW_SETUP).toEqual([flowRows, heldRows, madeOfRows]);
    const rows = studyRows(flowResult());
    expect(rows[0].label).toBe('Flow in/out');
    expect(rows[0].children.map((row: { label: string }) => row.label)).toEqual(['In 0.5 m/s at the low X side', 'Out at 0 Pa, the high X side']);
  });

  it('leads its verdict with "Laminar · " and says its limits in Details', () => {
    const verdict = feaVerdict(flowResult());
    expect(verdict.title).toBe('Flows freely');
    expect(verdict.caption.startsWith('Laminar · ')).toBe(true);
    expect(verdict.caption).not.toContain('unreliable');
    const details = studyRows(flowResult()).find((row: { id: string }) => row.id === 'details');
    expect(JSON.stringify(details)).toContain(LIMIT);
  });

  it('reads the Reynolds number as data first: past its limit, the caption and a Details row say so', () => {
    const past = flowResult({ reynolds: { value: 2391, limit: 2000, kind: 'internal', laminar: false }, warnings: [PAST] });
    expect(past.analysis.reynolds).toEqual({ value: 2391, limit: 2000, kind: 'internal' });
    expect(reynoldsWarning(past)).toEqual({ sentence: PAST, limit: 2000 });
    expect(feaVerdict(past).caption.startsWith('Laminar · unreliable above Re 2000 · ')).toBe(true);
    const details = studyRows(past).find((row: { id: string }) => row.id === 'details');
    expect(details.children[0]).toMatchObject({ id: 'reynolds', label: PAST });
    // The data rules: a laminar number with a stray sentence is no warning; a number past its limit with no sentence still is.
    expect(reynoldsWarning(flowResult({ reynolds: { value: 900, limit: 1000, kind: 'external' }, warnings: [PAST] }))).toBeNull();
    const bare = reynoldsWarning(flowResult({ reynolds: { value: 1500, limit: 1000, kind: 'external' } }));
    expect(bare).toMatchObject({ limit: 1000 });
    expect(bare!.sentence).toContain('Re 1500 is past the laminar range');
  });

  it('falls back to the sentence when the file carries no structured number', () => {
    expect(reynoldsWarning(flowResult({ warnings: [PAST] }))).toEqual({ sentence: PAST, limit: 2000 });
    expect(reynoldsWarning(flowResult())).toBeNull();
  });
});
