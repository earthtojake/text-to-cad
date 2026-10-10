import { BufferAttribute, BufferGeometry, Group, Mesh } from 'three';
import { describe, expect, it } from 'vitest';
import { feaControls, feaVerdict, readFeaResult, studyRows } from '../../feaResult.js';
import { checkLine, plyAngle } from '../checkKinds.js';
import { FIELD_WORDS } from '../fields.js';
import composite, { layupNotation, layupRows, layupWords, readLayup } from './composite.js';
import { ANALYSES } from './index.js';

const plain = (text: string) => text.replace(/[\u00a0\u202f]/g, ' ');
const ply = (angle: number, thickness = 0.5) => ({ material: 'cfrp', angle_deg: angle, thickness_mm: thickness });

/** A composite result as cadgen writes one (`analysis composite`): failure index, ply-envelope stress, displacement, its layup echoed. */
function compositeResult({ check = {}, layup = undefined as unknown } = {}) {
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new BufferAttribute(new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]), 3));
  geometry.setAttribute('_von_mises', new BufferAttribute(new Float32Array([0, 20, 40]), 1));
  geometry.setAttribute('_displacement', new BufferAttribute(new Float32Array(9), 3));
  geometry.setAttribute('_failure_index', new BufferAttribute(new Float32Array([0, 0.4, 0.82]), 1));
  geometry.setAttribute('_face', new BufferAttribute(new Float32Array([0, 0, 0]), 1));
  const mesh = new Mesh(geometry);
  Object.assign(mesh.userData, {
    generator: 'cadgen fea', name: 'panel composite', deformation_scale: 100,
    fields: [{ attribute: '_VON_MISES', name: 'von Mises stress (ply envelope)', units: 'MPa', min: 0, max: 40, attribute_scale: 1, field: 'von_mises' },
      { attribute: '_DISPLACEMENT', name: 'displacement', units: 'mm', min: 0, max: 0.02, attribute_scale: 1000, field: 'displacement' },
      { attribute: '_FAILURE_INDEX', name: 'failure index', units: '', min: 0, max: 0.82, attribute_scale: 1, field: 'failure_index' }],
    analysis: { type: 'composite', tier: 3, word: 'Composite', estimate: false, limits: ['Linear: ... no delamination ...'], noun: 'this load', reference_C: null, warnings: [] },
    checks: [{ kind: 'ply_failure', label: 'Ply failure', value: 0.82, limit: 1, unit: '', ratio: 0.82, close_at: 0.9, status: 'passes',
      where: { ref: '#o1.f5', at: [0, 0, 0] }, ply: 3, angle_deg: 45, criterion: 'tsai_wu', ...check }],
    faces: ['#o1.f5', '#o1.f6'], occurrence: '#o1',
    study: { fixtures: [{ type: 'fixed', faces: ['#o1.f6'] }], loads: [{ type: 'pressure', faces: ['#o1.f5'], pressure_MPa: 0.01 }],
      mesh: { size_mm: 8, refined_from_mm: null },
      layup: layup === undefined ? { plies: [ply(0), ply(90), ply(90), ply(0)], notation: '[0/90]s', thickness_mm: 2 } : layup },
  });
  const root = new Group();
  root.add(mesh);
  return readFeaResult(root)!;
}

describe('composite', () => {
  it('is registered: Tier 3, its own ply failure check and displacement, no load control', () => {
    expect(ANALYSES.composite).toBe(composite);
    expect(composite).toMatchObject({ name: 'composite', tier: 3, word: 'Composite', family: null, scalesWithLoad: false, limitWord: 'Lite',
      checks: ['ply_failure', 'displacement'] });
    expect(composite.routine(compositeResult())).toBeNull();
    expect(FIELD_WORDS._failure_index).toBe('Failure index');
  });

  it('writes its check as the worst ply, its angle and its index, and titles it by status', () => {
    const result = compositeResult();
    const verdict = feaVerdict(result)!;
    expect(verdict.title).toBe('Every ply holds');
    expect(verdict.rows.map((row: any) => row.label)).toEqual(['Ply failure']);
    expect(plain(checkLine({ ...result.checks![0], shown: 0.82 }))).toBe('Worst ply 3 (+45°), failure index 0.82');
    expect(plain(checkLine({ kind: 'ply_failure', shown: 1.3, limit: 1 }))).toBe('Failure index 1.30, limit 1');
    expect(plyAngle(-45)).toBe('−45°');
    expect(plyAngle(0)).toBe('0°');
    expect(feaVerdict(compositeResult({ check: { value: 1.3, ratio: 1.3, status: 'fails' } }))!.title).toBe('A ply fails');
    expect(feaVerdict(compositeResult({ check: { value: 0.95, ratio: 0.95, status: 'close' } }))!.title).toBe('Close to failing');
  });

  it('sets up as Held at, Pushed and its Layup: "4 plies, [0/90]s, 2 mm"', () => {
    const result = compositeResult();
    const rows = studyRows(result);
    expect(rows.map((row: any) => row.id)).toEqual(['fixed', 'loads', 'layup', 'details']);
    expect(rows[2]).toMatchObject({ id: 'layup', label: 'Layup', glyph: 'material',
      children: [{ id: 'layup:0', label: '4 plies, [0/90]s, 2 mm', hint: 'cfrp', refs: ['#o1'], summary: 'Layup 4 plies, [0/90]s, 2 mm of cfrp' }] });
    expect(layupRows(compositeResult({ layup: null }))).toEqual([]);
    // An echo with no notation is written from its plies.
    const own = readLayup(compositeResult({ layup: { plies: [ply(0, 0.25), ply(45, 0.25), ply(-45, 0.25), ply(90, 0.25)] } }))!;
    expect(layupWords(own)).toBe('4 plies, [0/45/-45/90], 1 mm');
    expect(layupNotation([ply(45), ply(-45), ply(-45), ply(45)])).toBe('[45/-45]s');
  });

  it('offers the field and the deformation', () => {
    expect(feaControls(compositeResult()).map((control: any) => control.drives)).toEqual(['field', 'deformation']);
  });
});
