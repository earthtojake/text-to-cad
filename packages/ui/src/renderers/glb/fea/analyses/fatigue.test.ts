import { BufferAttribute, BufferGeometry, Group, Mesh } from 'three';
import { describe, expect, it } from 'vitest';
import { feaControls, feaVerdict, readFeaResult, studyRows } from '../../feaResult.js';
import { heldRows, madeOfRows, pushedRows } from '../setup.js';
import fatigue from './fatigue.js';
import { ANALYSES } from './index.js';

// The check as cadgen writes it: the Goodman factor as the value, held to its margin, its ratio one over
// the factor and its close_at one over the margin; the cycles needed (`need`) and, within the data, the life.
const CLOSE = { kind: 'fatigue', label: 'Fatigue life', value: 1.317, limit: 1.5, unit: '', ratio: 0.759301, close_at: 0.666667,
  margin: 1.5, status: 'close', where: { ref: '#o1.f1', at: [0, 0, 3] }, need: 1e6, life: 3.903e7 };
const FAILS = { ...CLOSE, label: 'Service life', value: 0.812, ratio: 1.231527, status: 'fails', need: 1e9 };
const RUNOUT = { kind: 'fatigue', label: '', value: 2.4, limit: 1.5, unit: '', ratio: 0.416667, close_at: 0.666667, margin: 1.5,
  status: 'passes', where: { ref: null, at: [0, 0, 0] }, need: 1e6 };

/** A fatigue result as cadgen writes one: life (log10 cycles) first, the fatigue factor, the displacement. */
function fatigueResult(checks: unknown[]) {
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new BufferAttribute(new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]), 3));
  geometry.setAttribute('_von_mises', new BufferAttribute(new Float32Array([7.6, 8, 8.7]), 1));
  geometry.setAttribute('_life', new BufferAttribute(new Float32Array([7.6, 8, 8.7]), 1));
  geometry.setAttribute('_fatigue_factor', new BufferAttribute(new Float32Array([1.3, 5, 100]), 1));
  geometry.setAttribute('_displacement', new BufferAttribute(new Float32Array(9), 3));
  const mesh = new Mesh(geometry);
  Object.assign(mesh.userData, {
    generator: 'cadgen fea', name: 'beam fatigue life', deformation_scale: 2,
    fields: [
      { attribute: '_LIFE', name: 'fatigue life', units: 'log10 cycles', min: 7.59, max: 8.699, attribute_scale: 1, field: 'life' },
      { attribute: '_FATIGUE_FACTOR', name: 'fatigue safety factor', units: '', min: 1.317, max: 100, attribute_scale: 1, field: 'fatigue_factor' },
      { attribute: '_DISPLACEMENT', name: 'displacement', units: 'mm', min: 0, max: 1.4, attribute_scale: 1000, field: 'displacement' }],
    analysis: { type: 'fatigue', tier: 1, word: 'Fatigue life', estimate: false, limits: [], noun: 'this load', reference_C: null, warnings: [] },
    checks, faces: ['#o1.f1', '#o1.f2'], occurrence: '#o1',
    study: { material: { name: 'Aluminum 7075-T6', yield_MPa: 503 }, fixtures: [{ type: 'fixed', faces: ['#o1.f1'] }],
      loads: [{ type: 'force', faces: ['#o1.f2'], vector_N: [0, 0, -150] }], mesh: { size_mm: 1.5, refined_from_mm: 3 },
      fatigue: { from: 'static', loading: 'zero_based', stress_ratio: 0, cycles: 1e6, surface: 'machined', factor: 1 } },
  });
  const root = new Group();
  root.add(mesh);
  return readFeaResult(root)!;
}

describe('fatigue', () => {
  it('judges the fatigue kind, does not follow the load control and plays no routine', () => {
    expect(ANALYSES.fatigue).toBe(fatigue);
    expect(fatigue).toMatchObject({ name: 'fatigue', tier: 1, word: 'Fatigue life', family: null, scalesWithLoad: false, checks: ['fatigue'] });
    expect(fatigue.routine(fatigueResult([CLOSE]))).toBeNull();
    expect(fatigue.setupGroups).toEqual([heldRows, pushedRows, madeOfRows]);
  });

  it('reads the check cadgen writes: the life against the life needed, close under its margin', () => {
    const result = fatigueResult([CLOSE]);
    expect(result.checks).toEqual([expect.objectContaining({ kind: 'fatigue', value: 1.317, need: 1e6, life: 3.903e7, margin: 1.5, closeAt: 0.666667 })]);
    const verdict = feaVerdict(result)!;
    expect(verdict.title).toBe('Close to the limit');
    expect(verdict.caption).toBe('Lasts 39 million cycles, needs 1 million');
    expect(verdict.rows[0]).toMatchObject({ label: 'Fatigue life', margin: 1.5 });
  });

  it('says the factor at the cycles needed where the life is past the material\'s data, and fails a check short of its cycles', () => {
    expect(feaVerdict(fatigueResult([RUNOUT]))!).toMatchObject({ title: 'Lasts long enough', caption: 'Factor 2.4 at 1 million cycles, needs 1.5' });
    const both = feaVerdict(fatigueResult([CLOSE, FAILS]))!;
    expect(both.title).toBe('Fails 1 of 2 checks');
    expect(both.rows.map((row: any) => [row.label, row.line.replace(/ /g, ' ')])).toEqual([
      ['Service life', 'Lasts 39 million cycles, needs 1 billion'], ['Fatigue life', 'Lasts 39 million cycles, needs 1 million']]);
  });

  it('opens on the life, offers the fatigue factor and the displacement, and the deformation; its setup is static\'s', () => {
    const result = fatigueResult([CLOSE]);
    const [field, deformation] = feaControls(result);
    expect(field).toMatchObject({ drives: 'field', defaultValue: '_life',
      options: [{ value: '_life', label: 'Life' }, { value: '_fatigue_factor', label: 'Fatigue margin' }, { value: '_displacement', label: 'Displacement' }] });
    expect(deformation).toMatchObject({ drives: 'deformation' });
    expect(studyRows(result).map((row: any) => row.id)).toEqual(['fixed', 'loads', 'material', 'details']);
  });
});
