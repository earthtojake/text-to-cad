import { BufferAttribute, BufferGeometry, Group, Mesh } from 'three';
import { describe, expect, it } from 'vitest';
import { feaControls, feaVerdict, readFeaResult, studyRows } from '../../feaResult.js';
import drop, { dropG, droppedEstimateRows } from './drop.js';
import { ANALYSES } from './index.js';
import { LOAD_RAMP } from './static.js';

/** A drop result as cadgen writes one (`analysis drop`): a static result's fields, the drop echoed, its stress check "Drop". */
function dropResult(study: Record<string, unknown> = {}) {
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new BufferAttribute(new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]), 3));
  geometry.setAttribute('_von_mises', new BufferAttribute(new Float32Array([0, 2, 4]), 1));
  geometry.setAttribute('_displacement', new BufferAttribute(new Float32Array(9), 3));
  geometry.setAttribute('_face', new BufferAttribute(new Float32Array([0, 0, 0]), 1));
  const mesh = new Mesh(geometry);
  Object.assign(mesh.userData, {
    generator: 'cadgen fea', name: 'block drop (estimate)', deformation_scale: 1000, safety_factor: 10,
    fields: [{ attribute: '_VON_MISES', name: 'von Mises stress', units: 'MPa', min: 0, max: 4, attribute_scale: 1, field: 'von_mises' },
      { attribute: '_DISPLACEMENT', name: 'displacement', units: 'mm', min: 0, max: 0.001, attribute_scale: 1000, field: 'displacement' }],
    analysis: { type: 'drop', tier: 2, word: 'Drop (estimate)', estimate: true, limits: ['An estimate: ...'], noun: 'this drop', reference_C: null, warnings: [] },
    checks: [{ kind: 'stress', label: 'Drop', value: 4, limit: 40, unit: 'MPa', ratio: 0.1, close_at: 0.5, margin: 2, status: 'passes', where: { ref: '#o1.f5', at: [0, 0, 0] } }],
    faces: ['#o1.f5'], occurrence: '#o1',
    study: { material: { name: 'ABS', yield_MPa: 40 }, fixtures: [{ type: 'fixed', faces: ['#o1.f5'] }],
      loads: [{ type: 'acceleration', vector_g: [0, 0, 500] }], mesh: { size_mm: 5, refined_from_mm: null },
      drop: { height_mm: 1000, onto: ['#o1.f5'], stop_mm: 2, direction: [0, 0, -1], G: 500 }, ...study },
  });
  const root = new Group();
  root.add(mesh);
  return readFeaResult(root)!;
}

describe('drop', () => {
  it('is the registry\'s estimate of the static family, under the Load ramp, its stress check "Drop"', () => {
    expect(ANALYSES.drop).toBe(drop);
    expect(drop).toMatchObject({ name: 'drop', tier: 2, estimate: true, family: 'static', scalesWithLoad: true, noun: 'this drop',
      checks: ['stress', 'displacement'], checkLabels: { stress: 'Drop' }, markers: ['drop', 'fixture'] });
    expect(drop.routine(dropResult())).toBe(LOAD_RAMP);
  });

  it('works out the g a drop became: height over stop, or a half-sine\'s peak', () => {
    expect(dropG({ heightMm: 1000, stopMm: 2, impactMs: null })).toBe(500);
    expect(dropG({ heightMm: 1000, stopMm: null, impactMs: 1.5 })).toBeCloseTo(472.9, 1);
    expect(dropG({ heightMm: null, stopMm: 2, impactMs: null })).toBeNull();
    expect(dropG(null)).toBeNull();
  });

  it('sets up as Dropped, the landing faces under it and the steady load it became its hint, then Made of', () => {
    const result = dropResult();
    const [dropped, material] = studyRows(result);
    expect(dropped).toMatchObject({ id: 'drop', label: 'Dropped', glyph: 'drop', children: [
      { id: 'drop:0', label: '1 m drop', hint: 'stopping in 2 mm, about 500 g steady', faces: ['#o1.f5'],
        summary: '1 m drop, stopping in 2 mm, landing on face 5' }] });
    expect(material).toMatchObject({ id: 'material', label: 'Made of' });
    // No "Held at" or "Pushed": the landing faces and the equivalent load are the drop's own row.
    expect(studyRows(result).map((row: any) => row.id)).toEqual(['drop', 'material', 'details']);
    expect(droppedEstimateRows(dropResult({ drop: undefined }))).toEqual([]);
  });

  it('says it is an estimate in its takeaway, and offers the field and the deformation', () => {
    const result = dropResult();
    const verdict = feaVerdict(result)!;
    expect(verdict.caption).toBe('Estimate · OK up to 10× this drop');
    expect(verdict.rows.map((row: any) => row.label)).toEqual(['Drop']);
    expect(feaControls(result).map((control: any) => control.drives)).toEqual(['field', 'deformation']);
  });
});
