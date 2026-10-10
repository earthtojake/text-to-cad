import { BufferAttribute, BufferGeometry, Group, Mesh } from 'three';
import { describe, expect, it } from 'vitest';
import { feaControls, feaVerdict, readFeaResult, studyRows } from '../../feaResult.js';
import { activeFrameIndex } from '../series.js';
import impact, { PLAY, fallWords, impactDroppedRows } from './impact.js';
import { ANALYSES, feaAnalysis } from './index.js';

const LIMITS = 'Rigid floor; linear tets; elastic unless plasticity is given.';

/** A drop impact as cadgen writes one (`analysis impact`): frame 0 at first contact in the fields' own attributes, the peak the default. */
function impactResult(drop: Record<string, unknown> = {}, extras: Record<string, unknown> = {}) {
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new BufferAttribute(new Float32Array([0, 0, 0, 0.01, 0, 0, 0, 0.1, 0]), 3));
  geometry.setIndex([0, 1, 2]);
  geometry.setAttribute('_von_mises', new BufferAttribute(new Float32Array([0, 0, 0]), 1));
  geometry.setAttribute('_displacement', new BufferAttribute(new Float32Array(9), 3));
  geometry.setAttribute('_von_mises_peak', new BufferAttribute(new Float32Array([90, 120, 180]), 1));
  geometry.setAttribute('_displacement_peak', new BufferAttribute(new Float32Array([0, 0.02, 0.04]), 1));
  geometry.setAttribute('_face', new BufferAttribute(new Float32Array([0, 0, 1]), 1));
  for (const [index, top] of [[1, 120], [2, 180], [3, 60]]) {
    geometry.setAttribute(`_von_mises_f${index}`, new BufferAttribute(new Float32Array([0, top / 2, top]), 1));
    geometry.setAttribute(`_displacement_f${index}`, new BufferAttribute(new Float32Array(9).fill(index * 1e-5), 3));
  }
  const mesh = new Mesh(geometry);
  Object.assign(mesh.userData, {
    generator: 'cadgen fea', name: 'bar drop impact', deformation_scale: 100, safety_factor: 1.385, peak_g: 22848,
    faces: ['#o1.f5', '#o1.f6'], occurrence: '#o1',
    analysis: { type: 'impact', tier: 3, word: 'Drop impact', estimate: false, limits: [LIMITS], noun: 'this drop', reference_C: null, warnings: [] },
    fields: [
      { attribute: '_VON_MISES', name: 'von Mises stress', units: 'MPa', min: 0, max: 180, attribute_scale: 1, field: 'von_mises', per_frame: true },
      { attribute: '_DISPLACEMENT', name: 'displacement', units: 'mm', min: 0, max: 0.04, attribute_scale: 1000, field: 'displacement', per_frame: true },
      { attribute: '_VON_MISES_PEAK', name: 'von Mises stress (peak over time)', units: 'MPa', min: 0, max: 180, attribute_scale: 1, field: 'von_mises_peak' },
      { attribute: '_DISPLACEMENT_PEAK', name: 'displacement (largest over time)', units: 'mm', min: 0, max: 0.04, attribute_scale: 1, field: 'displacement_peak' },
    ],
    series: { kind: 'time', unit: 's', default: 2, frames: [
      { value: 0, label: '0 s', attributes: { von_mises: '_VON_MISES', displacement: '_DISPLACEMENT' } },
      { value: 5e-6, label: '5 µs', attributes: { von_mises: '_VON_MISES_F1', displacement: '_DISPLACEMENT_F1' } },
      { value: 1.01e-5, label: '10.1 µs', attributes: { von_mises: '_VON_MISES_F2', displacement: '_DISPLACEMENT_F2' } },
      { value: 1.19e-4, label: '119 µs', attributes: { von_mises: '_VON_MISES_F3', displacement: '_DISPLACEMENT_F3' } }] },
    checks: [
      { kind: 'stress', label: 'Strength', value: 180.5, limit: 250, unit: 'MPa', ratio: 0.722, close_at: 0.5, margin: 2, status: 'close',
        where: { ref: '#o1.f5', at: [0, 0, 0] }, at: { frame: 2, value: 1.01e-5, unit: 's', time_s: 1.01e-5 } },
      { kind: 'acceleration', label: 'Peak g', value: 22848, limit: 30000, unit: 'g', ratio: 0.7616, close_at: 0.9, status: 'passes',
        where: { ref: null, at: [0, 0, 50] }, at: { frame: 2, value: 1.34e-5, unit: 's', time_s: 1.34e-5 } }],
    study: { material: { name: 'Steel (structural, generic)', yield_MPa: 250 },
      drop: { height_mm: 1000, direction: [0, 0, -1], floor: 'rigid', friction: 0, onto: ['#o1.f5'], ...drop },
      window_ms: 'auto', mesh: { size_mm: 3, order: 1, elements: 2209, refined_from_mm: null } },
    findings: [],
    ...extras,
  });
  const root = new Group();
  root.add(mesh);
  return readFeaResult(root)!;
}

describe('impact', () => {
  it('is Drop impact, Tier 3: judged by stress, peak g and permanent strain, playing its frames, over a rigid floor', () => {
    expect(ANALYSES.impact).toBe(impact);
    expect(impact).toMatchObject({ name: 'impact', tier: 3, word: 'Drop impact', noun: 'this drop', family: null, estimate: false,
      scalesWithLoad: false, checks: ['stress', 'acceleration', 'plastic_strain'], checkLabels: { acceleration: 'Peak g' },
      markers: ['drop', 'rigid_plane'], displayTitle: 'Drop and floor', limitWord: 'Rigid floor' });
    const result = impactResult();
    expect(feaAnalysis(result)).toBe(impact);
    expect(impact.routine(result)).toBe(PLAY);
    expect(PLAY).toEqual({ id: 'fea:play', label: 'Play', kind: 'play' });
    expect(impact.routine({ series: null })).toBeNull();
  });

  it('opens on the Time scrubber at the peak, then the field and the deformation, with no load control', () => {
    const result = impactResult();
    const controls = feaControls(result);
    expect(controls.map((control: { drives: string }) => control.drives)).toEqual(['frame', 'field', 'deformation']);
    expect(controls[0]).toMatchObject({ type: 'number', label: 'Time', min: 0, max: 1.19e-4, defaultValue: 1.01e-5, unit: 's',
      snaps: [0, 5e-6, 1.01e-5, 1.19e-4], frameLabels: ['0 s', '5 µs', '10.1 µs', '119 µs'] });
    expect(activeFrameIndex(result)).toBe(2);
    expect(activeFrameIndex(result, { frame: 1e-4 })).toBe(3);
  });

  it('leads its takeaway with "Rigid floor", and keeps each check\'s moment so choosing it can jump there', () => {
    const result = impactResult();
    const verdict = feaVerdict(result)!;
    expect(verdict.caption.startsWith('Rigid floor · ')).toBe(true);
    expect(verdict.rows.map((row: { label: string }) => row.label)).toEqual(['Strength', 'Peak g']);
    expect(result.checks.map((check: { at: { frame: number } }) => check.at.frame)).toEqual([2, 2]);
  });

  it('sets up as Dropped, "1 m drop onto a rigid floor", how it falls its hint and the faces that landed under it, then Made of', () => {
    const result = impactResult();
    const [dropped, material] = studyRows(result);
    expect(dropped).toMatchObject({ id: 'drop', label: 'Dropped', glyph: 'drop', children: [
      { id: 'drop:0', label: '1 m drop onto a rigid floor', hint: 'Falling down, no friction', faces: ['#o1.f5'],
        summary: '1 m drop onto a rigid floor, landing on face 5' }] });
    expect(material).toMatchObject({ id: 'material', label: 'Made of' });
    expect(studyRows(result).map((row: { id: string }) => row.id)).toEqual(['drop', 'material', 'details']);
    expect(fallWords(impactResult({ direction: [1, 0, 0], friction: 0.3 }))).toBe('Falling along +X, friction 0.3');
    // No faces met the floor (none recorded): the drop is chosen with the whole part.
    const [whole] = impactDroppedRows(impactResult({ onto: [], height_mm: 500 }));
    expect(whole.children[0]).toMatchObject({ label: '500 mm drop onto a rigid floor', refs: ['#o1'] });
  });

  it('lists its limits in Details', () => {
    const details = studyRows(impactResult()).find((row: { id: string }) => row.id === 'details');
    const labels = JSON.stringify(details);
    expect(labels).toContain(LIMITS);
  });
});
