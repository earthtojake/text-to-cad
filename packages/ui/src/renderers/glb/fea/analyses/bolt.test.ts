import { BufferAttribute, BufferGeometry, Group, Mesh } from 'three';
import { describe, expect, it } from 'vitest';
import { checkLine, checkTitle, forceWords } from '../checkKinds.js';
import { feaControls, feaVerdict, readFeaResult, studyRows } from '../../feaResult.js';
import { activeFrameIndex } from '../series.js';
import { heldRows, madeOfRows, pushedRows, rigidFloorRows } from '../setup.js';
import { contactRows } from './contact.js';
import { feaAnalysis } from './index.js';
import bolt, { BOLT_SETUP, PLAY, boltRows, boltWords } from './bolt.js';

const LIMIT = 'Each bolt is a pretensioned spring along its axis, not meshed';
const plain = (text: string) => text.replace(/[\u00a0\u202f]/g, ' ');

// An M6 bolt clamping a plate to a bracket, as cadgen writes it: the preload, then one load step, the last the default.
function boltedResult(extras: Record<string, unknown> = {}) {
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new BufferAttribute(new Float32Array([0, 0, 0, 0.01, 0, 0, 0, 0.01, 0]), 3));
  geometry.setIndex([0, 1, 2]);
  geometry.setAttribute('color', new BufferAttribute(new Uint8Array(12), 4, true));
  geometry.setAttribute('_von_mises', new BufferAttribute(new Float32Array([150, 10, 20]), 1));
  geometry.setAttribute('_displacement', new BufferAttribute(new Float32Array(9), 3));
  geometry.setAttribute('_contact_pressure', new BufferAttribute(new Float32Array([180, 0, 60]), 1));
  geometry.setAttribute('_von_mises_f1', new BufferAttribute(new Float32Array([170, 20, 40]), 1));
  geometry.setAttribute('_displacement_f1', new BufferAttribute(new Float32Array([0, 0, 0.001, 0, 0, 0, 0, 0, 0]), 3));
  geometry.setAttribute('_contact_pressure_f1', new BufferAttribute(new Float32Array([220, 0, 30]), 1));
  geometry.setAttribute('_face', new BufferAttribute(new Float32Array([0, 0, 1]), 1));
  const mesh = new Mesh(geometry);
  Object.assign(mesh.userData, {
    generator: 'cadgen fea', name: 'joint bolt', deformation_scale: 1, faces: ['#o1.1.f1', '#o1.2.f6'], load_percent: 100, collapsed: false,
    analysis: { type: 'bolt', tier: 3, word: 'Bolted joint', estimate: false, limits: [LIMIT], noun: 'this load', reference_C: null, warnings: [] },
    fields: [
      { attribute: '_VON_MISES', name: 'von Mises stress', units: 'MPa', min: 0, max: 170, attribute_scale: 1, field: 'von_mises', per_frame: true },
      { attribute: '_DISPLACEMENT', name: 'displacement', units: 'mm', min: 0, max: 0.001, attribute_scale: 1000, field: 'displacement', per_frame: true },
      { attribute: '_CONTACT_PRESSURE', name: 'contact pressure', units: 'MPa', min: 0, max: 220, attribute_scale: 1, field: 'contact_pressure', per_frame: true },
    ],
    series: { kind: 'time', unit: '%', default: 1, frames: [
      { value: 0, label: 'Preload', attributes: { von_mises: '_VON_MISES', displacement: '_DISPLACEMENT', contact_pressure: '_CONTACT_PRESSURE' } },
      { value: 100, label: '100 % load', attributes: { von_mises: '_VON_MISES_F1', displacement: '_DISPLACEMENT_F1', contact_pressure: '_CONTACT_PRESSURE_F1' } }] },
    parts: [{ ref: '#o1.1', name: 'plate' }, { ref: '#o1.2', name: 'bracket' }],
    contacts: [
      { kind: 'pair', name: 'plate on bracket', words: 'plate presses on bracket, friction 0.2', friction: 0.2, between: ['plate', 'bracket'],
        refs: ['#o1.1', '#o1.2'], touching: true, force_N: 3057, peak_MPa: 130 },
    ],
    bolts: [{ name: 'bolt 1', size: 'M6', between: ['plate', 'bracket'], refs: ['#o1.1', '#o1.2'], preload_N: 5000, force_N: 6057, proof_N: 11658,
      slack: false }],
    joints: [{ name: 'plate and bracket', clamp_N: 3057, preload_clamp_N: 5000, open: false, slips: false }],
    study: {
      material: { name: 'Steel (structural, generic)', yield_MPa: 250, youngs_GPa: 200, poisson: 0.3 },
      fixtures: [{ type: 'fixed', faces: ['#o1.2.f6'] }], loads: [{ type: 'force', faces: ['#o1.1.f1'], vector_N: [0, 0, 3000] }], steps: 1,
      contact_pairs: [], rigid_planes: [],
      bolts: [{ between: ['plate', 'bracket'], size: 'M6', diameter_mm: 6, preload_N: 5000, torque_Nm: null, nut_factor: null, grade: '8.8',
        friction: 0.2, holes: ['#o1.1.f7', '#o1.2.f7'], words: 'M6 bolt, 5 kN preload, clamps plate and bracket' }],
      mesh: { size_mm: 1.5, order: 2, elements: 800, refined_from_mm: null },
    },
    checks: [{ kind: 'bolt_load', label: 'Bolt load', value: 12500, limit: 11658, unit: 'N', ratio: 1.072, close_at: 0.9, status: 'fails',
      where: { ref: null, at: [0, 0, 12] }, at: { frame: 1, value: 100, unit: '%' } }],
    findings: [],
    ...extras,
  });
  const root = new Group();
  root.add(mesh);
  return readFeaResult(root)!;
}

describe('bolt', () => {
  it('is Bolted joint, Tier 3 and Lite: no load control, its checks and markers, playing its steps', () => {
    expect(bolt).toMatchObject({ name: 'bolt', tier: 3, word: 'Bolted joint', noun: 'this load', family: null, scalesWithLoad: false,
      limitWord: 'Lite', checks: ['bolt_load', 'joint_separation', 'joint_slip', 'stress', 'displacement', 'contact_pressure'],
      displayTitle: 'Loads and fixtures' });
    expect(BOLT_SETUP).toEqual([heldRows, pushedRows, boltRows, contactRows, rigidFloorRows, madeOfRows]);
    const result = boltedResult();
    expect(feaAnalysis(result)).toBe(bolt);
    expect(bolt.routine(result)).toBe(PLAY);
    expect(bolt.routine({ series: null })).toBeNull();
  });

  it('opens on a load-step scrubber from the preload, the field (with the contact pressure) and the deformation, on the last step', () => {
    const result = boltedResult();
    const [step, field, deformation] = feaControls(result);
    expect(step).toMatchObject({ drives: 'frame', type: 'number', label: 'Load step', min: 0, max: 100, defaultValue: 100, unit: '%',
      snaps: [0, 100], frameLabels: ['Preload', '100 % load'] });
    expect(field.options.map((option: { label: string }) => option.label)).toEqual(['Stress', 'Displacement', 'Contact pressure']);
    expect(deformation).toMatchObject({ drives: 'deformation' });
    expect(feaControls(result).some((control: { drives: string }) => control.drives === 'load_scale')).toBe(false);
    expect(activeFrameIndex(result)).toBe(1);
  });

  it('names each bolt in its setup in plain words, with its force after loading', () => {
    const rows = studyRows(boltedResult());
    expect(rows.slice(0, 3).map((row: { label: string }) => row.label)).toEqual(['Held at', 'Pushed', 'Bolted']);
    const [bolted] = boltRows(boltedResult());
    expect(bolted).toMatchObject({ id: 'bolts', label: 'Bolted', glyph: 'load' });
    expect(bolted.children).toEqual([{ id: 'bolt:0', label: 'M6 bolt, 5 kN preload, clamps plate and bracket', detail: '', wrap: true,
      hint: '6.1 kN after loading', refs: ['#o1.1', '#o1.2'], summary: 'Bolt: M6 bolt, 5 kN preload, clamps plate and bracket' }]);
    // The bolted pair's own contact is not a second "Pressed together" row.
    expect(contactRows(boltedResult())).toEqual([]);
    expect(boltWords({ size: 'M10', between: ['lid', 'base_plate'], preload_N: 12500 })).toBe('M10 bolt, 13 kN preload, clamps lid and base plate');
    const slack = boltedResult({ bolts: [{ refs: ['#o1.1', '#o1.2'], force_N: 0, slack: true }] });
    expect(boltRows(slack)[0].children[0].hint).toBe('goes slack');
    expect(boltRows(boltedResult({ study: { fixtures: [], loads: [] } }))).toEqual([]);
  });

  it('leads its verdict with "Lite · ", words its three checks in plain words and says its limits in Details', () => {
    const verdict = feaVerdict(boltedResult());
    expect(verdict.title).toBe('Bolt overloaded');
    expect(verdict.caption.startsWith('Lite · ')).toBe(true);
    const details = studyRows(boltedResult()).find((row: { id: string }) => row.id === 'details');
    const limits = details.children.find((row: { id: string }) => row.id === 'limits');
    expect(limits.children.map((row: { label: string }) => row.label)).toEqual([LIMIT]);
    const check = (kind: string, value: number, limit: number) => ({ kind, value, shown: value, limit, unit: 'N' });
    expect(['fails', 'close', 'passes'].map((status) => checkTitle(check('bolt_load', 1, 2), status)))
      .toEqual(['Bolt overloaded', 'Close to the limit', 'Bolt holds']);
    expect(['fails', 'close', 'passes'].map((status) => checkTitle(check('joint_separation', 1, 2), status)))
      .toEqual(['Joint opens', 'Close to opening', 'Joint stays shut']);
    expect(['fails', 'close', 'passes'].map((status) => checkTitle(check('joint_slip', 1, 2), status)))
      .toEqual(['Joint slips', 'Close to slipping', 'Joint holds by friction']);
    expect(plain(checkLine(check('bolt_load', 6057, 11658)))).toBe('Bolt 6.1 kN, limit 12 kN');
    expect(plain(checkLine(check('joint_separation', 1943, 5000)))).toBe('Lost 1.9 kN, of 5 kN clamp');
    expect(plain(checkLine(check('joint_slip', 950, 1000)))).toBe('Sideways 950 N, friction holds 1 kN');
    expect([forceWords(800), forceWords(5000), forceWords(12500)]).toEqual(['800 N', '5 kN', '13 kN']);
  });
});
