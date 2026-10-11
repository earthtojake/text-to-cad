import { BufferAttribute, BufferGeometry, Group, Mesh } from 'three';
import { describe, expect, it } from 'vitest';
import { checkLine, checkTitle } from '../checkKinds.js';
import { feaControls, feaVerdict, readFeaResult, studyRows } from '../../feaResult.js';
import { activeFrame, activeFrameIndex } from '../series.js';
import { heldRows, madeOfRows, pushedRows } from '../setup.js';
import { feaAnalysis } from './index.js';
import nonlinear, { NONLINEAR_SETUP, PLAY, collapseCaption } from './nonlinear.js';

const LIMIT = 'No rate or temperature effects: the material answers the same however fast it is loaded';

// A cantilever pushed past its collapse, as cadgen writes it: three load steps, the last it carried the default.
function bentResult(extras: Record<string, unknown> = {}) {
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new BufferAttribute(new Float32Array([0, 0, 0, 0.08, 0, 0, 0, 0.006, 0]), 3));
  geometry.setIndex([0, 1, 2]);
  geometry.setAttribute('color', new BufferAttribute(new Uint8Array(12), 4, true));
  geometry.setAttribute('_von_mises', new BufferAttribute(new Float32Array([80, 10, 40]), 1));
  geometry.setAttribute('_displacement', new BufferAttribute(new Float32Array(9), 3));
  geometry.setAttribute('_plastic_strain', new BufferAttribute(new Float32Array([0, 0, 0]), 1));
  for (const index of [1, 2]) {
    geometry.setAttribute(`_von_mises_f${index}`, new BufferAttribute(new Float32Array([250, 30, 120]), 1));
    geometry.setAttribute(`_displacement_f${index}`, new BufferAttribute(new Float32Array([0, 0, 0, 0, 0, -0.004 * index, 0, 0, 0]), 3));
    geometry.setAttribute(`_plastic_strain_f${index}`, new BufferAttribute(new Float32Array([2.6 * index, 0, 0.1]), 1));
  }
  geometry.setAttribute('_face', new BufferAttribute(new Float32Array([0, 0, 1]), 1));
  const mesh = new Mesh(geometry);
  Object.assign(mesh.userData, {
    generator: 'cadgen fea', name: 'cantilever nonlinear', deformation_scale: 1, faces: ['#o1.f1', '#o1.f2'], occurrence: '#o1',
    load_percent: 69.7, collapsed: true,
    analysis: { type: 'nonlinear', tier: 3, word: 'Permanent bend / Stretch', estimate: false, limits: [LIMIT], noun: 'this load',
      reference_C: null, warnings: ['Collapses at about 70 % of the load'] },
    fields: [
      { attribute: '_VON_MISES', name: 'von Mises stress', units: 'MPa', min: 0, max: 250, attribute_scale: 1, field: 'von_mises', per_frame: true },
      { attribute: '_DISPLACEMENT', name: 'displacement', units: 'mm', min: 0, max: 8, attribute_scale: 1000, field: 'displacement', per_frame: true },
      { attribute: '_PLASTIC_STRAIN', name: 'plastic strain', units: '%', min: 0, max: 5.2, attribute_scale: 1, field: 'plastic_strain', per_frame: true },
    ],
    series: { kind: 'time', unit: '%', default: 2, frames: [
      { value: 30, label: '30 % load', attributes: { von_mises: '_VON_MISES', displacement: '_DISPLACEMENT', plastic_strain: '_PLASTIC_STRAIN' } },
      { value: 60, label: '60 % load', attributes: { von_mises: '_VON_MISES_F1', displacement: '_DISPLACEMENT_F1', plastic_strain: '_PLASTIC_STRAIN_F1' } },
      { value: 69.7, label: '69.7 % load', attributes: { von_mises: '_VON_MISES_F2', displacement: '_DISPLACEMENT_F2', plastic_strain: '_PLASTIC_STRAIN_F2' } }] },
    study: {
      material: { name: 'Steel (structural, generic)', yield_MPa: 250, youngs_GPa: 200, poisson: 0.3 },
      fixtures: [{ type: 'fixed', faces: ['#o1.f1'] }], loads: [{ type: 'force', faces: ['#o1.f2'], vector_N: [0, 0, -126.6] }],
      steps: 10, material_model: 'plasticity', mesh: { size_mm: 2, order: 2, elements: 978, refined_from_mm: null },
    },
    checks: [{ kind: 'plastic_strain', label: 'Permanent bend', value: 5.2, limit: 0.2, unit: '%', ratio: 26, close_at: 0.9, status: 'fails',
      where: { ref: '#o1.f6', at: [3.4, -0.75, 3] }, at: { frame: 2, value: 69.7, unit: '%' }, collapsed_at_percent: 69.7 }],
    findings: [],
    ...extras,
  });
  const root = new Group();
  root.add(mesh);
  return readFeaResult(root)!;
}

describe('nonlinear', () => {
  it('is Permanent bend / Stretch, Tier 3 and Lite: no load control, its checks, static setup, playing its steps', () => {
    expect(nonlinear).toMatchObject({ name: 'nonlinear', tier: 3, word: 'Permanent bend / Stretch', noun: 'this load', family: null,
      scalesWithLoad: false, limitWord: 'Lite', checks: ['plastic_strain', 'stress', 'displacement'], displayTitle: 'Loads and fixtures' });
    expect(nonlinear.markers).toEqual(['load', 'fixture', 'body_load']);
    expect(NONLINEAR_SETUP).toEqual([heldRows, pushedRows, madeOfRows]);
    const result = bentResult();
    expect(feaAnalysis(result)).toBe(nonlinear);
    expect(nonlinear.routine(result)).toBe(PLAY);
    expect(PLAY).toEqual({ id: 'fea:play', label: 'Play', kind: 'play' });
    expect(nonlinear.routine({ series: null })).toBeNull();
  });

  it('opens on a load-step scrubber that snaps to the steps, the field and the deformation, on the last load carried', () => {
    const result = bentResult();
    const [step, field, deformation] = feaControls(result);
    expect(step).toMatchObject({ drives: 'frame', type: 'number', label: 'Load step', min: 30, max: 69.7, defaultValue: 69.7, unit: '%',
      snaps: [30, 60, 69.7], frameLabels: ['30 % load', '60 % load', '69.7 % load'] });
    expect(field).toMatchObject({ drives: 'field', defaultValue: '_von_mises' });
    expect(field.options.map((option: { label: string }) => option.label)).toEqual(['Stress', 'Displacement', 'Plastic strain']);
    expect(deformation).toMatchObject({ drives: 'deformation' });
    expect(feaControls(result).some((control: { drives: string }) => control.drives === 'load_scale')).toBe(false);
    expect(activeFrameIndex(result)).toBe(2);
    expect(activeFrameIndex(result, { frame: 58 })).toBe(1);
    const shown = activeFrame(result, { frame: 60 }, result.fields[2]);
    expect(shown.field.attribute).toBe('_plastic_strain_f1');
    expect(shown.deformation.attribute).toBe('_displacement_f1');
  });

  it('leads its verdict with "Lite · ", fails a collapse and says its limits in Details', () => {
    const verdict = feaVerdict(bentResult());
    expect(verdict.status).toBe('weak');
    expect(verdict.title).toBe('Bends for good');
    expect(verdict.caption.startsWith('Lite · ')).toBe(true);
    const details = studyRows(bentResult()).find((row: { id: string }) => row.id === 'details');
    const limits = details.children.find((row: { id: string }) => row.id === 'limits');
    expect(limits.children.map((row: { label: string }) => row.label)).toEqual([LIMIT]);
    expect(studyRows(bentResult()).slice(0, 3).map((row: { label: string }) => row.label)).toEqual(['Held at', 'Pushed', 'Made of']);
  });

  it('leads a collapse\'s takeaway with the collapse, not the worst check\'s words', () => {
    const result = bentResult();
    expect(result).toMatchObject({ collapsed: true, loadPercent: 69.7 });
    expect(feaVerdict(result).caption).toBe('Lite · Collapses at about 70 % of the load');
    // Without the file's sentence, from the last load it carried.
    const unsaid = bentResult({ analysis: { type: 'nonlinear', tier: 3, word: 'Permanent bend / Stretch', limits: [LIMIT], warnings: [] } });
    expect(collapseCaption(unsaid)).toBe('Collapses at about 70 % of the load');
    // A run that carried the full load says its worst check, as before.
    const carried = bentResult({ collapsed: false, load_percent: 100, analysis: { type: 'nonlinear', tier: 3, warnings: [] } });
    expect(collapseCaption(carried)).toBe('');
    expect(feaVerdict(carried).caption.startsWith('Lite · ')).toBe(true);
    expect(feaVerdict(carried).caption).not.toContain('Collapses');
  });

  it('words its check as cadgen writes it', () => {
    const check = { kind: 'plastic_strain', value: 0.4, shown: 0.4, limit: 0.2, unit: '%' };
    expect(checkTitle(check, 'fails')).toBe('Bends for good');
    expect(checkTitle(check, 'passes')).toBe('Springs back');
    expect(checkLine(check).replace(/[\u00a0\u202f]/g, ' ')).toBe('0.4 % permanent, limit 0.2 %');
  });

  it('says its worst check\'s own sentence, never a load multiple: the response is not proportional to the load', () => {
    // The file's checks say they do not scale; an older file without that still reads them so (the analysis's own scaling).
    for (const scaling of [{ scaling: 'none' }, {}]) {
      const verdict = feaVerdict(bentResult({ collapsed: false, checks: [{ kind: 'stress', label: 'Strength', value: 13.8, limit: 250, unit: 'MPa', ratio: 0.0552, close_at: 0.5, margin: 2, status: 'passes', where: { ref: null, at: [0, 0, 0] }, ...scaling }] }))!;
      expect(verdict.caption).not.toMatch(/×/);
      expect(verdict.caption.replace(/[\u00a0\u202f]/g, ' ')).toBe('Lite · Peak 14 MPa, limit 250 MPa');
    }
  });
});
