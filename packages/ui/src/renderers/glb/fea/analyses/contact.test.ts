import { BufferAttribute, BufferGeometry, Group, Mesh } from 'three';
import { describe, expect, it } from 'vitest';
import { checkLine, checkTitle } from '../checkKinds.js';
import { feaControls, feaVerdict, readFeaResult, studyRows } from '../../feaResult.js';
import { activeFrame, activeFrameIndex } from '../series.js';
import { heldRows, madeOfRows, pushedRows, rigidFloorRows } from '../setup.js';
import { feaAnalysis } from './index.js';
import contact, { CONTACT_SETUP, PLAY, contactRows } from './contact.js';

const LIMIT = 'Small sliding: each surface node is paired once, before loading, with the surface it faces';

// A pin pressed on a plate that rests on a rigid floor, as cadgen writes it: two load steps, the last the default.
function pressedResult(extras: Record<string, unknown> = {}) {
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new BufferAttribute(new Float32Array([0, 0, 0, 0.01, 0, 0, 0, 0.01, 0]), 3));
  geometry.setIndex([0, 1, 2]);
  geometry.setAttribute('color', new BufferAttribute(new Uint8Array(12), 4, true));
  geometry.setAttribute('_von_mises', new BufferAttribute(new Float32Array([40, 10, 20]), 1));
  geometry.setAttribute('_displacement', new BufferAttribute(new Float32Array(9), 3));
  geometry.setAttribute('_contact_pressure', new BufferAttribute(new Float32Array([5, 0, 2]), 1));
  geometry.setAttribute('_von_mises_f1', new BufferAttribute(new Float32Array([80, 20, 40]), 1));
  geometry.setAttribute('_displacement_f1', new BufferAttribute(new Float32Array([0, 0, -0.001, 0, 0, 0, 0, 0, 0]), 3));
  geometry.setAttribute('_contact_pressure_f1', new BufferAttribute(new Float32Array([10, 0, 4]), 1));
  geometry.setAttribute('_face', new BufferAttribute(new Float32Array([0, 0, 1]), 1));
  const mesh = new Mesh(geometry);
  Object.assign(mesh.userData, {
    generator: 'cadgen fea', name: 'press contact', deformation_scale: 1, faces: ['#o1.1.f1', '#o1.2.f6'], load_percent: 100, collapsed: false,
    analysis: { type: 'contact', tier: 3, word: 'Contact', estimate: false, limits: [LIMIT], noun: 'this load', reference_C: null, warnings: [] },
    fields: [
      { attribute: '_VON_MISES', name: 'von Mises stress', units: 'MPa', min: 0, max: 80, attribute_scale: 1, field: 'von_mises', per_frame: true },
      { attribute: '_DISPLACEMENT', name: 'displacement', units: 'mm', min: 0, max: 0.001, attribute_scale: 1000, field: 'displacement', per_frame: true },
      { attribute: '_CONTACT_PRESSURE', name: 'contact pressure', units: 'MPa', min: 0, max: 10, attribute_scale: 1, field: 'contact_pressure', per_frame: true },
    ],
    series: { kind: 'time', unit: '%', default: 1, frames: [
      { value: 50, label: '50 % load', attributes: { von_mises: '_VON_MISES', displacement: '_DISPLACEMENT', contact_pressure: '_CONTACT_PRESSURE' } },
      { value: 100, label: '100 % load', attributes: { von_mises: '_VON_MISES_F1', displacement: '_DISPLACEMENT_F1', contact_pressure: '_CONTACT_PRESSURE_F1' } }] },
    parts: [{ ref: '#o1.1', name: 'pin' }, { ref: '#o1.2', name: 'plate' }],
    contacts: [
      { kind: 'pair', name: 'pin on plate', words: 'pin presses on plate, friction 0.2', friction: 0.2, between: ['pin', 'plate'], refs: ['#o1.1', '#o1.2'],
        touching: true, force_N: 1000, peak_MPa: 10 },
      { kind: 'plane', name: 'the rigid plane', words: 'plate on the rigid plane', friction: 0, refs: ['#o1.2'], touching: true, force_N: 1000, peak_MPa: 2.5 },
    ],
    study: {
      material: { name: 'Steel (structural, generic)', yield_MPa: 250, youngs_GPa: 200, poisson: 0.3 },
      fixtures: [], loads: [{ type: 'force', faces: ['#o1.1.f1'], vector_N: [0, 0, -1000] }], steps: 2,
      contact_pairs: [{ between: ['pin', 'plate'], friction: 0.2 }],
      rigid_planes: [{ point_mm: [0, 0, 0], normal: [0, 0, 1], parts: ['plate'], friction: 0 }],
      mesh: { size_mm: 2, order: 2, elements: 900, refined_from_mm: null },
    },
    checks: [{ kind: 'contact_pressure', label: 'Contact', value: 10, limit: 8, unit: 'MPa', ratio: 1.25, close_at: 0.9, status: 'fails',
      where: { ref: '#o1.2.f6', at: [0, 0, 0] }, at: { frame: 1, value: 100, unit: '%' } }],
    findings: [],
    ...extras,
  });
  const root = new Group();
  root.add(mesh);
  return readFeaResult(root)!;
}

describe('contact', () => {
  it('is Contact, Tier 3 and Lite: no load control, its checks and markers, playing its steps', () => {
    expect(contact).toMatchObject({ name: 'contact', tier: 3, word: 'Contact', noun: 'this load', family: null, scalesWithLoad: false,
      limitWord: 'Lite', checks: ['stress', 'displacement', 'contact_pressure'], displayTitle: 'Loads and fixtures' });
    expect(contact.markers).toEqual(['load', 'fixture', 'rigid_plane']);
    expect(CONTACT_SETUP).toEqual([heldRows, pushedRows, contactRows, rigidFloorRows, madeOfRows]);
    const result = pressedResult();
    expect(feaAnalysis(result)).toBe(contact);
    expect(contact.routine(result)).toBe(PLAY);
    expect(PLAY).toEqual({ id: 'fea:play', label: 'Play', kind: 'play' });
    expect(contact.routine({ series: null })).toBeNull();
  });

  it('opens on a load-step scrubber, the field (with the contact pressure) and the deformation, on the last step', () => {
    const result = pressedResult();
    const [step, field, deformation] = feaControls(result);
    expect(step).toMatchObject({ drives: 'frame', type: 'number', label: 'Load step', min: 50, max: 100, defaultValue: 100, unit: '%',
      snaps: [50, 100], frameLabels: ['50 % load', '100 % load'] });
    expect(field).toMatchObject({ drives: 'field', defaultValue: '_von_mises' });
    expect(field.options.map((option: { label: string }) => option.label)).toEqual(['Stress', 'Displacement', 'Contact pressure']);
    expect(deformation).toMatchObject({ drives: 'deformation' });
    expect(feaControls(result).some((control: { drives: string }) => control.drives === 'load_scale')).toBe(false);
    expect(activeFrameIndex(result)).toBe(1);
    const shown = activeFrame(result, { frame: 50 }, result.fields[2]);
    expect(shown.field.attribute).toBe('_contact_pressure');
    expect(activeFrame(result, { frame: 100 }, result.fields[2]).field.attribute).toBe('_contact_pressure_f1');
  });

  it('names each contact pair in its setup, with what it did, and the rigid floor under it', () => {
    const rows = studyRows(pressedResult());
    expect(rows.slice(0, 3).map((row: { label: string }) => row.label)).toEqual(['Pushed', 'Pressed together', 'Rigid floor']);
    const [pressed] = contactRows(pressedResult());
    expect(pressed).toMatchObject({ id: 'contacts', label: 'Pressed together', glyph: 'load' });
    expect(pressed.children).toEqual([{ id: 'contact:0', label: 'pin presses on plate, friction 0.2', detail: '', wrap: true,
      hint: '1000 N, peak 10 MPa', refs: ['#o1.1', '#o1.2'], summary: 'Contact: pin presses on plate, friction 0.2' }]);
    const floor = rows.find((row: { id: string }) => row.id === 'rigid');
    expect(floor.children.map((row: { label: string }) => row.label)).toEqual(['Facing up']);
    // A pair that separated says so; a frictionless one says it has none.
    const apart = pressedResult({
      contacts: [{ kind: 'pair', between: ['pin', 'plate'], refs: ['#o1.1', '#o1.2'], touching: false, force_N: 0, peak_MPa: 0 }],
      study: { fixtures: [], loads: [], contact_pairs: [{ between: ['pin', 'plate'], friction: 0 }], rigid_planes: [] },
    });
    expect(contactRows(apart)[0].children[0]).toMatchObject({ label: 'pin presses on plate, no friction', hint: 'no longer touching' });
    expect(contactRows(pressedResult({ study: { fixtures: [], loads: [] } }))).toEqual([]);
  });

  it('leads its verdict with "Lite · ", words the contact pressure check and says its limits in Details', () => {
    const verdict = feaVerdict(pressedResult());
    expect(verdict.title).toBe('Presses too hard');
    expect(verdict.caption.startsWith('Lite · ')).toBe(true);
    const details = studyRows(pressedResult()).find((row: { id: string }) => row.id === 'details');
    const limits = details.children.find((row: { id: string }) => row.id === 'limits');
    expect(limits.children.map((row: { label: string }) => row.label)).toEqual([LIMIT]);
    const check = { kind: 'contact_pressure', value: 380, shown: 380, limit: 400, unit: 'MPa' };
    expect(checkTitle(check, 'close')).toBe('Close to the limit');
    expect(checkTitle(check, 'passes')).toBe('Within the limit');
    expect(checkLine(check).replace(/[  ]/g, ' ')).toBe('Peak 380 MPa, limit 400 MPa');
  });

  it('says it is not reliable where its contact did not settle, in the takeaway and in Details, its checks still failing', () => {
    const sentence = 'Contact did not settle at 80% of the load: the forces here do not balance, so this result is not reliable';
    const result = pressedResult({
      analysis: { type: 'contact', tier: 3, word: 'Contact', estimate: false, limits: [LIMIT], noun: 'this load', reference_C: null,
        warnings: [sentence], unsettled: { at_percent: [80], first_percent: 80 } },
      checks: [{ kind: 'contact_pressure', label: 'Contact', value: 4, limit: 8, unit: 'MPa', ratio: 0.5, close_at: 0.9, status: 'fails',
        unsettled_at_percent: 80, where: { ref: '#o1.2.f6', at: [0, 0, 0] } }],
    });
    expect(result.analysis.unsettled).toEqual({ atPercent: [80], firstPercent: 80 });
    const verdict = feaVerdict(result);
    expect(verdict.caption.startsWith(`Not reliable · contact did not settle at 80% · ${contact.limitWord} · `)).toBe(true);
    expect(verdict.status).toBe('weak');
    expect(verdict.rows.map((row: { status: string }) => row.status)).toEqual(['weak']);
    const details = studyRows(result).find((row: { id: string }) => row.id === 'details');
    expect(details.children[0]).toMatchObject({ id: 'unsettled', label: sentence, summary: sentence });
    expect(feaVerdict(pressedResult()).caption.startsWith('Not reliable')).toBe(false);
  });

  it('says its worst check\'s own sentence, never a load multiple: contact opens, closes and slides', () => {
    for (const scaling of [{ scaling: 'none' }, {}]) {
      const verdict = feaVerdict(pressedResult({ checks: [{ kind: 'stress', label: 'Strength', value: 13.8, limit: 250, unit: 'MPa', ratio: 0.0552, close_at: 0.5, margin: 2, status: 'passes', where: { ref: null, at: [0, 0, 0] }, ...scaling }] }));
      expect(verdict.caption).not.toMatch(/×/);
      expect(verdict.caption.replace(/[\u00a0\u202f]/g, ' ')).toBe('Lite · Peak 14 MPa, limit 250 MPa');
    }
  });
});
