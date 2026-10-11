import { BufferAttribute, BufferGeometry, Group, Mesh } from 'three';
import { describe, expect, it } from 'vitest';
import { checkTitle } from '../checkKinds.js';
import { feaControls, feaDefaults, feaShownControls, readFeaResult, studyRows } from '../../feaResult.js';
import { feaAnalysis } from './index.js';
import random, { fieldAndSigma, psdGrms, psdWords, shakenAtRandomRows } from './random_vibration.js';

const TABLE = [[20, 0.01], [80, 0.04], [350, 0.04], [2000, 0.007]];

// A cantilever shaken at random as cadgen writes one: RMS stress first, RMS displacement beside it, nothing deformed.
function shaken(study: Record<string, unknown> = {}) {
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new BufferAttribute(new Float32Array([0, 0, 0, 0.1, 0, 0, 0.1, 0, 0.006]), 3));
  geometry.setIndex([0, 1, 2]);
  geometry.setAttribute('color', new BufferAttribute(new Uint8Array(12), 4, true));
  geometry.setAttribute('_displacement', new BufferAttribute(new Float32Array(9), 3));
  geometry.setAttribute('_von_mises_rms', new BufferAttribute(new Float32Array([9.6, 2, 0]), 1));
  geometry.setAttribute('_displacement_rms', new BufferAttribute(new Float32Array([0, 0.02, 0.045]), 1));
  geometry.setAttribute('_face', new BufferAttribute(new Float32Array([0, 1, 1]), 1));
  const mesh = new Mesh(geometry);
  Object.assign(mesh.userData, {
    generator: 'cadgen fea', name: 'beam random vibration', deformation_scale: null, faces: ['#o1.f1', '#o1.f2'],
    analysis: { type: 'random_vibration', tier: 1, word: 'Random vibration', estimate: false, limits: [], noun: 'this shake', reference_C: null, warnings: [] },
    fields: [
      { attribute: '_VON_MISES_RMS', name: 'von Mises stress (RMS, 1σ)', units: 'MPa', min: 0, max: 9.6, attribute_scale: 1, field: 'von_mises_rms' },
      { attribute: '_DISPLACEMENT_RMS', name: 'displacement (RMS, 1σ, relative to the base)', units: 'mm', min: 0, max: 0.045, attribute_scale: 1, field: 'displacement_rms' },
    ],
    study: {
      material: { name: 'Steel', yield_MPa: 250 },
      fixtures: [{ type: 'fixed', faces: ['#o1.f1'] }],
      psd: { direction: [0, 0, 1], table: TABLE }, damping_ratio: 0.02, sigma: 3,
      mesh: { size_mm: 2, order: 2, elements: 1708, refined_from_mm: null }, margin: 2,
      ...study,
    },
    checks: [{ kind: 'stress', label: 'Random vibration', value: 28.9, limit: 250, unit: 'MPa', ratio: 0.1156, close_at: 0.5, margin: 2,
      status: 'passes', where: { ref: '#o1.f1', at: [0, 3, 3] } }],
    findings: [],
  });
  const root = new Group();
  root.add(mesh);
  return readFeaResult(root)!;
}

describe('random_vibration', () => {
  it('is Random vibration: stress and displacement by this shake, judged at a sigma level, no routine', () => {
    expect(random).toMatchObject({ name: 'random_vibration', tier: 1, word: 'Random vibration', noun: 'this shake', family: null,
      scalesWithLoad: true, checks: ['stress', 'displacement'], checkLabels: { stress: 'Random vibration' },
      markers: ['fixture', 'base_excitation'], displayTitle: 'Shaker and fixtures' });
    const result = shaken();
    expect(feaAnalysis(result)).toBe(random);
    expect(random.routine(result)).toBeNull();
    expect(result.checks[0].label).toBe('Random vibration');
    expect(checkTitle(result.checks[0], 'passes')).toBe('Strong enough');
  });

  it('opens on the field and the Sigma level the study judges at', () => {
    const result = shaken();
    const [field, sigma] = feaControls(result);
    expect(field).toMatchObject({ drives: 'field', defaultValue: '_von_mises_rms',
      options: [{ value: '_von_mises_rms', label: 'Stress (1σ)' }, { value: '_displacement_rms', label: 'Displacement (1σ)' }] });
    expect(sigma).toMatchObject({ drives: 'sigma', label: 'Sigma', defaultValue: '3' });
    expect(feaControls(shaken({ sigma: 1 }))[1]).toMatchObject({ drives: 'sigma', defaultValue: '1' });
    // With no RMS field there is no level to choose.
    expect(fieldAndSigma({ ...result, fields: result.fields.map((entry: { attribute: string }) => ({ ...entry, attribute: '_von_mises' })) })
      .map((control: { drives: string }) => control.drives)).toEqual(['field']);
  });

  it("names the field select's RMS fields at the sigma level shown, as the colour bar does", () => {
    const result = shaken();
    const controls = feaControls(result);
    const labels = (values: Record<string, unknown>) => feaShownControls(result, controls, { ...feaDefaults(controls), ...values })
      .shown[0].options.map((option: { label: string }) => option.label);
    expect(labels({})).toEqual(['Stress (3σ)', 'Displacement (3σ)']);
    expect(labels({ sigma: '1' })).toEqual(['Stress (1σ)', 'Displacement (1σ)']);
  });

  it('says it is held, shaken at random with the PSD summarised, and what it is made of', () => {
    const rows = studyRows(shaken());
    expect(rows.slice(0, 3).map((row: { label: string }) => row.label)).toEqual(['Held at', 'Shaken', 'Made of']);
    expect(rows[1].children[0]).toMatchObject({ label: '6.1 g rms along Z, 20 to 2000 Hz', faces: ['#o1.f1'],
      hint: 'At random, a 4-point PSD, judged at 3σ', summary: 'Shaken at random where it is held: 6.1 g rms along Z, 20 to 2000 Hz' });
  });

  it('reads the g rms the file echoes, else integrates the table log-log', () => {
    expect(psdGrms(TABLE)).toBeCloseTo(6.0582, 4);
    expect(psdGrms([[20, 0.04], [1000, 0.04]])).toBeCloseTo(Math.sqrt(0.04 * 980), 10);
    const echoed = shaken({ psd: { direction: [1, 0, 0], table: [[20, 0.04], [1000, 0.04]], grms: 6.26 } });
    expect(psdWords({ table: [[20, 0.04], [1000, 0.04]], grms: 6.26, direction: [1, 0, 0] })).toBe('6.3 g rms along X, 20 to 1000 Hz');
    expect(shakenAtRandomRows(echoed)[0].children[0].label).toBe('6.3 g rms along X, 20 to 1000 Hz');
    expect(shakenAtRandomRows(shaken({ psd: null }))).toEqual([]);
  });

  it('reads the PSD and its g rms from the study it keeps, not the raw echo', () => {
    const result = shaken({ psd: { direction: [1, 0, 0], table: [[20, 0.04], [1000, 0.04]], grms: 6.26 } });
    expect(result.study.psd).toEqual({ table: [[20, 0.04], [1000, 0.04]], grms: 6.26, direction: [1, 0, 0] });
    expect(shaken().study.psd.grms).toBeNull();
    result.mesh.userData.study = {};
    expect(shakenAtRandomRows(result)[0].children[0].label).toBe('6.3 g rms along X, 20 to 1000 Hz');
  });
});
