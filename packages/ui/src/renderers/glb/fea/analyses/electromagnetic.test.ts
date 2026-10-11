import { BufferAttribute, BufferGeometry, Group, Mesh } from 'three';
import { describe, expect, it } from 'vitest';
import { feaControls, feaVerdict, readFeaResult, studyRows } from '../../feaResult.js';
import { faceTitle, heldRows, madeOfRows } from '../setup.js';
import electromagnetic, { ELECTROMAGNETIC_SETUP, coilRows, electrodeRows, hertz } from './electromagnetic.js';
import { feaAnalysis } from './index.js';

// An electric-field result as cadgen writes one: the voltage first (signed), the field's strength beside it.
function electricResult(extras: Record<string, unknown> = {}, attributes: Record<string, number[]> = {}) {
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new BufferAttribute(new Float32Array([0, 0, 0, 0.01, 0, 0, 0, 0.01, 0]), 3));
  geometry.setIndex([0, 1, 2]);
  geometry.setAttribute('color', new BufferAttribute(new Uint8Array(12), 4, true));
  geometry.setAttribute('_displacement', new BufferAttribute(new Float32Array(9), 3));
  geometry.setAttribute('_potential', new BufferAttribute(new Float32Array([0, 500, 1000]), 1));
  geometry.setAttribute('_electric_field', new BufferAttribute(new Float32Array([0.5, 0.5, 2.8]), 1));
  geometry.setAttribute('_face', new BufferAttribute(new Float32Array([0, 0, 1]), 1));
  for (const [name, values] of Object.entries(attributes)) geometry.setAttribute(name, new BufferAttribute(new Float32Array(values), 1));
  const mesh = new Mesh(geometry);
  Object.assign(mesh.userData, {
    generator: 'cadgen fea', name: 'gap electromagnetic', deformation_scale: null, faces: ['#o1.f1', '#o1.f2'],
    analysis: { type: 'electromagnetic', tier: 3, word: 'Magnetic / electric', estimate: false,
      limits: ['Static and DC only: no eddy currents, AC or high frequency; linear materials (no saturation, no hysteresis).'],
      noun: 'this voltage', reference_C: null, warnings: [], mode: 'electrostatic' },
    fields: [
      { attribute: '_POTENTIAL', name: 'voltage', units: 'V', min: 0, max: 1000, attribute_scale: 1, field: 'potential', signed: true },
      { attribute: '_ELECTRIC_FIELD', name: 'electric field', units: 'kV/mm', min: 0, max: 2.8, attribute_scale: 1, field: 'electric_field' },
    ],
    study: {
      material: { name: 'PETG', yield_MPa: 50 },
      mode: 'electrostatic',
      voltages: [{ faces: ['#o1.f1'], V: 1000, name: 'top' }, { faces: ['#o1.f2'], V: 0, name: '0 V' }],
      mesh: { size_mm: 2, order: 2, elements: 100, refined_from_mm: null },
    },
    checks: [{ kind: 'electric_field', label: 'Arcing', value: 2.8, limit: 3, unit: 'kV/mm', ratio: 2.8 / 3, close_at: 0.9,
      status: 'close', where: { ref: null, at: [1, 2, 3] } }],
    findings: [],
    ...extras,
  });
  const root = new Group();
  root.add(mesh);
  return readFeaResult(root)!;
}

describe('electromagnetic', () => {
  it('is Magnetic / electric, Tier 3: judged by the field, the heat or the force, not by a load control, with no routine', () => {
    expect(electromagnetic).toMatchObject({ name: 'electromagnetic', tier: 3, word: 'Magnetic / electric', noun: 'this voltage',
      family: null, scalesWithLoad: false, limitWord: 'Static', checks: ['electric_field', 'temperature', 'stress', 'displacement'] });
    expect(electromagnetic.routine(electricResult())).toBeNull();
    expect(feaAnalysis(electricResult())).toBe(electromagnetic);
  });

  it('opens on the Field select across its fields, voltage first, with no deformation to draw', () => {
    const controls = feaControls(electricResult());
    expect(controls.map((control: { drives: string }) => control.drives)).toEqual(['field']);
    expect(controls[0].options).toEqual([{ value: '_potential', label: 'Voltage' }, { value: '_electric_field', label: 'Electric field' }]);
  });

  it('sets up as electrodes ("Held at 1000 V"), coils ("Coil 2 A × 100 turns") and what it is made of', () => {
    expect(electromagnetic.setupGroups).toEqual(ELECTROMAGNETIC_SETUP);
    expect(ELECTROMAGNETIC_SETUP).toContain(heldRows);
    expect(ELECTROMAGNETIC_SETUP).toContain(madeOfRows);
    const rows = studyRows(electricResult());
    expect(rows.slice(0, 2).map((row: { label: string }) => row.label)).toEqual(['Electrodes', 'Made of']);
    expect(rows[0].children.map((row: { label: string }) => row.label)).toEqual(['Held at 1000 V', 'Held at 0 V']);
    expect(rows[0].children[0]).toMatchObject({ hint: 'top', summary: 'Held at 1000 V on face 1', faces: ['#o1.f1'] });
    expect(rows[0].children[1].hint).toBeUndefined();

    const coil = electricResult({ study: { material: { name: 'Aluminum 6061-T6', yield_MPa: 276 }, mode: 'magnetostatic',
      coils: [{ part: 'winding_a', turns: 100, A: 2, name: 'coil 1', axis: { direction: [0, 0, 1] } }],
      currents: [{ faces: ['#o1.f2'], A: 3, name: 'in' }] } });
    expect(coilRows(coil)[0].children[0]).toMatchObject({ label: 'Coil 2 A × 100 turns', hint: 'Wound on winding a' });
    expect(electrodeRows(coil)[0].children[0]).toMatchObject({ label: '3 A in', summary: '3 A in through face 2' });
  });

  it('says the strongest field against the gap\'s limit in plain words', () => {
    const verdict = feaVerdict(electricResult());
    expect(verdict.title).toBe('Close to arcing');
    const arcs = feaVerdict(electricResult({ checks: [{ kind: 'electric_field', label: 'Arcing', value: 3.6, limit: 3, unit: 'kV/mm',
      ratio: 1.2, close_at: 0.9, status: 'fails', where: { ref: null, at: [0, 0, 0] } }] }));
    expect(arcs.title).toBe('Arcs over');
    const holds = feaVerdict(electricResult({ checks: [{ kind: 'electric_field', label: 'Arcing', value: 0.5, limit: 3, unit: 'kV/mm',
      ratio: 0.5 / 3, close_at: 0.9, status: 'passes', where: { ref: null, at: [0, 0, 0] } }] }));
    expect(holds.title).toBe('Holds the voltage');
    expect(JSON.stringify(holds)).not.toContain('No stress');
  });

  it("lists each part's own material and names a face by its part in an assembly", () => {
    const result = electricResult({
      faces: ['#o1.1.f1', '#o1.2.f1'],
      parts: [{ ref: '#o1.1', name: 'coil', material: 'Copper', yield_MPa: 69 }, { ref: '#o1.2', name: 'shaft', material: 'Stainless steel 304', yield_MPa: 215 }],
      study: { material: { name: 'Stainless steel 304', yield_MPa: 215 }, mode: 'ac_magnetic', frequencyHz: 25000 },
    });
    const [made] = madeOfRows(result);
    expect(made.children[0]).toMatchObject({ label: '2 materials', hint: 'Copper: 1 part, Stainless steel 304: 1 part',
      summary: 'Made of Copper (coil) and Stainless steel 304 (shaft)' });
    expect(faceTitle(result, '#o1.2.f1')).toBe('shaft · face 1');
  });

  it('says where a peak out in the air is, so it does not read against the colour bar on the parts', () => {
    const verdict = feaVerdict(electricResult({ checks: [{ kind: 'electric_field', label: 'Arcing', value: 4.512, limit: 3, unit: 'kV/mm',
      ratio: 1.504, close_at: 0.9, status: 'fails', where: { ref: null, at: [0, 0, 6], in: 'air', near: 'hv-rod', gap_mm: 0 } }] }));
    expect(verdict.rows[0].line.replace(/\u00a0/g, ' ')).toBe('Peak 4.5 kV/mm, in the air by hv-rod, limit 3 kV/mm');
    expect(verdict.rows[0].choice.summary).toContain('in the air by hv-rod');
    // A peak inside a part, or one judged over named faces, reads as ever.
    expect(feaVerdict(electricResult()).rows[0].line.replace(/\u00a0/g, ' ')).toBe('Peak 2.8 kV/mm, limit 3 kV/mm');
  });

  it('says the current a magnetic force\'s stress allows as the square root of its room: force grows with the current squared', () => {
    const stress = { kind: 'stress', label: 'Plunger strength', value: 0.00525, limit: 250, unit: 'MPa', ratio: 2.1e-5, close_at: 0.5,
      margin: 2, status: 'passes', where: { ref: '#o1.2.f3', at: [0, 0, 48] }, part: 'plunger' };
    const magnetic = (check: Record<string, unknown>) => electricResult({
      analysis: { type: 'electromagnetic', tier: 3, word: 'Magnetic / electric', estimate: false, limits: [], noun: 'this current',
        reference_C: null, warnings: [], mode: 'magnetostatic' }, checks: [check] });
    // sqrt(250 / 0.00525) = 218, not 47619.
    expect(feaVerdict(magnetic({ ...stress, scaling: 'quadratic' })).caption).toBe('Static · OK up to 218× this current');
    // A file written before checks said how they scale reads as it did.
    expect(feaVerdict(magnetic(stress)).caption).toBe('Static · OK up to 47619× this current');
  });

  it('reads an AC field: Field select with Eddy current, "Coil 2 A at 50 kHz", and a takeaway that leads with "AC · "', () => {
    const ac = electricResult({
      analysis: { type: 'electromagnetic', tier: 3, word: 'Magnetic / electric', estimate: false,
        limits: ['Time-harmonic at one frequency: a sine steady state, no switching transients or harmonics.'],
        noun: 'this current', reference_C: 20, warnings: [], mode: 'ac_magnetic', frequency_Hz: 50000 },
      fields: [
        { attribute: '_EDDY_CURRENT', name: 'eddy current density', units: 'A/mm²', min: 0, max: 4.2, attribute_scale: 1, field: 'eddy_current' },
        { attribute: '_MAGNETIC_FIELD', name: 'magnetic flux density', units: 'mT', min: 0, max: 12, attribute_scale: 1, field: 'magnetic_field' },
        { attribute: '_TEMPERATURE', name: 'temperature', units: '°C', min: 20, max: 64, attribute_scale: 1, field: 'temperature', signed: true },
      ],
      study: {
        material: { name: 'Aluminum 6061-T6', yield_MPa: 276 }, mode: 'ac_magnetic', frequency_Hz: 50000,
        coils: [{ part: 'winding', turns: 100, A: 2, name: 'coil 1', axis: { direction: [0, 0, 1] } }],
        applied_field: { mT: 10, direction: [1, 0, 0] },
        currents: [{ faces: ['#o1.f2'], A: 30, name: 'in' }], voltages: [{ faces: ['#o1.f1'], V: 0, name: 'out' }],
      },
      checks: [{ kind: 'temperature', label: 'Heat', value: 64, limit: 80, unit: '°C', ratio: 0.73, close_at: 0.9, status: 'passes',
        reference: 20, where: { ref: null, at: [0, 0, 0] } }],
    }, { _eddy_current: [0, 1, 4.2], _magnetic_field: [3, 6, 12], _temperature: [20, 40, 64] });
    const controls = feaControls(ac);
    expect(controls.map((control: { drives: string }) => control.drives)).toEqual(['field']);
    expect(controls[0].options.map((option: { label: string }) => option.label)).toEqual(['Eddy current', 'Magnetic field', 'Temperature']);
    const driven = coilRows(ac)[0].children;
    expect(driven[0]).toMatchObject({ label: 'Coil 2 A at 50 kHz', hint: '100 turns, wound on winding',
      summary: 'Coil 2 A × 100 turns at 50 kHz wound on winding' });
    expect(driven[1]).toMatchObject({ label: 'Field 10 mT at 50 kHz', summary: 'A uniform 10 mT field along x at 50 kHz' });
    expect(electrodeRows(ac)[0].children.map((row: { label: string }) => row.label)).toEqual(['Held at 0 V', '30 A in at 50 kHz']);
    expect(feaVerdict(ac).caption.startsWith('AC · ')).toBe(true);
    expect(feaVerdict(electricResult()).caption.startsWith('Static · ')).toBe(true);
    expect([hertz(50), hertz(15791.86), hertz(2e6)]).toEqual(['50 Hz', '15.8 kHz', '2 MHz']);
  });

  it('reads its voltages, currents, coils and AC source through the study it keeps, not the raw echo', () => {
    const ac = electricResult({ study: {
      material: { name: 'Aluminum 6061-T6', yield_MPa: 276 }, mode: 'ac_magnetic', frequency_Hz: 50000,
      voltages: [{ faces: ['#o1.f1'], V: 12, name: 'feed' }], currents: [{ faces: ['#o1.f2'], A: 3, name: '' }],
      coils: [{ part: 'winding_a', turns: 100, A: 2, name: 'coil', axis: { direction: [0, 0, 1], point_mm: [0, 0, 5] } }],
      applied_field: { mT: 10, direction: [0, 0, 1] },
    } });
    expect(ac.study).toMatchObject({ mode: 'ac_magnetic', frequencyHz: 50000,
      voltages: [{ faces: ['#o1.f1'], value: 12, name: 'feed' }], currents: [{ faces: ['#o1.f2'], value: 3, name: '' }],
      coils: [{ part: 'winding_a', turns: 100, amps: 2, name: 'coil', axis: { direction: [0, 0, 1], point: [0, 0, 5] } }],
      appliedField: { mT: 10, direction: [0, 0, 1] } });
    const before = [electrodeRows(ac), coilRows(ac)];
    ac.mesh.userData.study = {};
    expect([electrodeRows(ac), coilRows(ac)]).toEqual(before);
    expect(electrodeRows(ac)[0].children.map((row: { label: string }) => row.label)).toEqual(['Held at 12 V', '3 A in at 50 kHz']);
    expect(coilRows(ac)[0].children.map((row: { label: string }) => row.label)).toEqual(['Coil 2 A at 50 kHz', 'Field 10 mT at 50 kHz']);
    expect(feaVerdict(ac).caption.startsWith('AC · ')).toBe(true);
  });
});
