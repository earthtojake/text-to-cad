import { BufferAttribute, BufferGeometry, Group, Mesh } from 'three';
import { describe, expect, it } from 'vitest';
import { checkTitle } from '../checkKinds.js';
import { feaControls, feaVerdict, readFeaResult, studyRows } from '../../feaResult.js';
import { feaAnalysis } from './index.js';
import shock, { shockedRows, spectrumLevel, spectrumWords } from './shock.js';

// A shocked cantilever as cadgen writes one: two envelopes (peak stress, peak displacement), no series.
function shocked(study: Record<string, unknown> = {}, checks: unknown[] = []) {
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new BufferAttribute(new Float32Array([0, 0, 0, 0.1, 0, 0, 0.1, 0, 0.006]), 3));
  geometry.setIndex([0, 1, 2]);
  geometry.setAttribute('color', new BufferAttribute(new Uint8Array(12), 4, true));
  geometry.setAttribute('_von_mises', new BufferAttribute(new Float32Array([16.7, 2, 0]), 1));
  geometry.setAttribute('_displacement', new BufferAttribute(new Float32Array(9), 3));
  geometry.setAttribute('_face', new BufferAttribute(new Float32Array([0, 1, 1]), 1));
  const mesh = new Mesh(geometry);
  Object.assign(mesh.userData, {
    generator: 'cadgen fea', name: 'beam shock', deformation_scale: 80, faces: ['#o1.f1', '#o1.f2'], safety_factor: 14.98,
    analysis: { type: 'shock', tier: 1, word: 'Shock', estimate: false, limits: [], noun: 'this shock', reference_C: null, warnings: [] },
    fields: [
      { attribute: '_VON_MISES', name: 'von Mises stress (peak, modes combined)', units: 'MPa', min: 0, max: 16.7, attribute_scale: 1, field: 'von_mises' },
      { attribute: '_DISPLACEMENT', name: 'displacement (peak, relative to the base)', units: 'mm', min: 0, max: 0.081, attribute_scale: 1000, field: 'displacement' },
    ],
    study: {
      material: { name: 'Steel', yield_MPa: 250 },
      fixtures: [{ type: 'fixed', faces: ['#o1.f1'] }], loads: [],
      srs: { direction: [0, 0, 1], table: [[10, 5], [100, 50], [2000, 50]], damping_ratio: 0.05 }, combination: 'srss',
      mesh: { size_mm: 2, order: 2, elements: 1708, refined_from_mm: null }, margin: 2,
      ...study,
    },
    checks: checks.length ? checks : [{ kind: 'stress', label: 'Shock', value: 16.7, limit: 250, unit: 'MPa', ratio: 0.0668, close_at: 0.5,
      status: 'passes', where: { ref: '#o1.f1', at: [0, 3, 3] } }],
    findings: [],
  });
  const root = new Group();
  root.add(mesh);
  return readFeaResult(root)!;
}

describe('shock', () => {
  it('is Shock: stress labelled Shock and displacement, by this shock, with no routine', () => {
    expect(shock).toMatchObject({ name: 'shock', tier: 1, word: 'Shock', noun: 'this shock', family: null, scalesWithLoad: true,
      checks: ['stress', 'displacement'], checkLabels: { stress: 'Shock' }, markers: ['fixture', 'base_excitation'] });
    const result = shocked();
    expect(feaAnalysis(result)).toBe(shock);
    expect(shock.routine(result)).toBeNull();
    expect(result.series).toBeNull();
  });

  it('opens on the field and the deformation', () => {
    const [field, deformation] = feaControls(shocked());
    expect(field).toMatchObject({ drives: 'field', type: 'enum', defaultValue: '_von_mises' });
    expect(deformation).toMatchObject({ drives: 'deformation', defaultValue: 80 });
  });

  it('says it is held, the shock in a line, and what it is made of', () => {
    const rows = studyRows(shocked());
    expect(rows.slice(0, 3).map((row: { label: string }) => row.label)).toEqual(['Held at', 'Shocked', 'Made of']);
    expect(rows[1]).toMatchObject({ glyph: 'wave' });
    expect(rows[1].children[0]).toMatchObject({ label: '50 g above 100 Hz along Z, 5% damping', hint: 'Modes combined by SRSS',
      faces: ['#o1.f1'], summary: 'Shocked where it is held: 50 g above 100 Hz along Z, 5% damping' });
    expect(shockedRows(shocked({ combination: 'cqc' }))[0].children[0].hint).toBe('Modes combined by CQC');
    expect(shockedRows(shocked({ srs: null }))).toEqual([]);
  });

  it('reads the spectrum and the combination from the study it keeps, not the raw echo', () => {
    const result = shocked();
    expect(result.study).toMatchObject({ srs: { direction: [0, 0, 1], table: [[10, 5], [100, 50], [2000, 50]], dampingRatio: 0.05 },
      combination: 'srss' });
    result.mesh.userData.study = {};
    expect(shockedRows(result)[0].children[0]).toMatchObject({ label: '50 g above 100 Hz along Z, 5% damping', hint: 'Modes combined by SRSS' });
  });

  it('words a spectrum by its highest plateau', () => {
    expect(spectrumLevel([[10, 5], [100, 50], [2000, 50]])).toBe('50 g above 100 Hz');
    expect(spectrumLevel([[10, 50], [2000, 50]])).toBe('50 g from 10 to 2000 Hz');
    expect(spectrumLevel([[10, 50], [400, 50], [2000, 10]])).toBe('50 g up to 400 Hz');
    expect(spectrumLevel([[10, 5], [100, 50], [1000, 50], [2000, 10]])).toBe('50 g from 100 to 1000 Hz');
    expect(spectrumLevel([[10, 5], [400, 30], [2000, 10]])).toBe('up to 30 g at 400 Hz');
    expect(spectrumLevel([[100, 5], [10, 50]])).toBe('');
    expect(spectrumWords({ direction: [1, 0, 0], table: [[10, 5], [400, 30], [2000, 10]], damping_ratio: 0.03 }))
      .toBe('up to 30 g at 400 Hz along X, 3% damping');
  });

  it('judges its stress as Shock, k times larger at k times this shock', () => {
    const result = shocked();
    const verdict = feaVerdict(result)!;
    expect(verdict.rows[0].label).toBe('Shock');
    expect(verdict.caption).toContain('this shock');
    expect(checkTitle(result.checks[0], 'passes')).toBe('Strong enough');
  });
});
