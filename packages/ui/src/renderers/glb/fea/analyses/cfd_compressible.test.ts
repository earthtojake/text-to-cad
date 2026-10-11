import { BufferAttribute, BufferGeometry, Group, Mesh } from 'three';
import { describe, expect, it } from 'vitest';
import { feaControls, feaVerdict, machWarning, readFeaResult, reynoldsWarning, studyRows } from '../../feaResult.js';
import { FLOW_SETUP } from './cfd.js';
import cfdCompressible from './cfd_compressible.js';
import { feaAnalysis } from './index.js';

const LIMIT = 'Steady, ideal gas, adiabatic (one total temperature); an inviscid core with frictionless walls past the laminar range, '
  + 'laminar walls in it; no turbulence model; shocks are captured over a few elements.';

// A gas flow result as cadgen writes one: wall pressure first, then the Mach number and the gas temperature; nothing deformed.
function gasResult(checks: Record<string, unknown>[] = []) {
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new BufferAttribute(new Float32Array([0, 0, 0, 0.04, 0, 0, 0, 0.004, 0]), 3));
  geometry.setIndex([0, 1, 2]);
  geometry.setAttribute('color', new BufferAttribute(new Uint8Array(12), 4, true));
  geometry.setAttribute('_displacement', new BufferAttribute(new Float32Array(9), 3));
  geometry.setAttribute('_pressure', new BufferAttribute(new Float32Array([2400, -13000, 0]), 1));
  geometry.setAttribute('_mach', new BufferAttribute(new Float32Array([0.19, 0.53, 0.27]), 1));
  geometry.setAttribute('_temperature', new BufferAttribute(new Float32Array([17.9, 4.5, 15.7]), 1));
  geometry.setAttribute('_face', new BufferAttribute(new Float32Array([0, 0, 0]), 1));
  const mesh = new Mesh(geometry);
  Object.assign(mesh.userData, {
    generator: 'cadgen fea', name: 'nozzle gas flow', deformation_scale: null, faces: ['#o1.f2'], occurrence: '#o1',
    analysis: { type: 'cfd_compressible', tier: 3, word: 'Fast gas flow', estimate: false, limits: [LIMIT], noun: 'this flow',
      reference_C: null, warnings: [], mach: { value: 0.53, limit: 1.8, regime: 'subsonic', checked: true }, walls: 'slip' },
    fields: [
      { attribute: '_PRESSURE', name: "wall pressure (above the outlet's)", units: 'Pa', min: -13000, max: 2400, attribute_scale: 1, field: 'pressure', signed: true },
      { attribute: '_MACH', name: 'Mach number', units: '', min: 0, max: 0.53, attribute_scale: 1, field: 'mach' },
      { attribute: '_TEMPERATURE', name: 'gas temperature', units: '°C', min: 4.5, max: 17.9, attribute_scale: 1, field: 'temperature', signed: true },
    ],
    study: {
      flow: { kind: 'internal', gas: { name: 'air', gamma: 1.4, gas_constant_J_kgK: 287 }, walls: 'auto',
        inlets: [{ opening: 'x_min', total_pressure_Pa: 106658, total_temperature_C: 20 }], outlets: [{ opening: 'x_max', pressure_Pa: 101325 }] },
      mesh: { size_mm: 1.6, order: 2, elements: 900, refined_from_mm: null },
    },
    checks,
    findings: [],
  });
  const root = new Group();
  root.add(mesh);
  return readFeaResult(root)!;
}

const mach = (value: number, status: string) => ({ kind: 'mach', label: 'Mach number', value, limit: 0.8, unit: '', ratio: value / 0.8,
  close_at: 0.9, status, where: { ref: null, at: [15, 0, 0] } });

describe('cfd_compressible', () => {
  it('is Fast gas flow, Tier 3 and Ideal gas: judged by drop, speed and Mach number, of no static family, with no routine', () => {
    expect(cfdCompressible).toMatchObject({ name: 'cfd_compressible', tier: 3, word: 'Fast gas flow', noun: 'this flow', limitWord: 'Ideal gas',
      family: null, scalesWithLoad: false, checks: ['pressure_drop', 'velocity', 'mach', 'stress', 'displacement'], displayTitle: 'Flow openings' });
    expect(cfdCompressible.markers).toEqual(['inlet', 'outlet', 'fixture']);
    expect(cfdCompressible.routine(gasResult())).toBeNull();
    expect(feaAnalysis(gasResult())).toBe(cfdCompressible);
  });

  it('opens on the field alone, pressure first, then Mach number and temperature, and sets up as Flow does', () => {
    const controls = feaControls(gasResult());
    expect(controls.map((control: { drives: string }) => control.drives)).toEqual(['field']);
    expect(controls[0].options).toEqual([{ value: '_pressure', label: 'Pressure' }, { value: '_mach', label: 'Mach number' },
      { value: '_temperature', label: 'Temperature' }]);
    expect(cfdCompressible.setupGroups).toEqual(FLOW_SETUP);
    const rows = studyRows(gasResult());
    expect(rows[0].label).toBe('Flow in/out');
    expect(rows[0].children.map((row: { label: string }) => row.label)).toEqual(['In at the low X side', 'Out at 101325 Pa, the high X side']);
  });

  it('leads its verdict with "Ideal gas · ", judges the Mach number in its own words, and says its limits in Details', () => {
    expect(feaVerdict(gasResult([mach(0.53, 'passes')])).title).toBe('Within the speed limit');
    expect(feaVerdict(gasResult([mach(0.75, 'close')])).title).toBe('Close to the limit');
    const fast = feaVerdict(gasResult([mach(1.52, 'fails')]));
    expect(fast.title).toBe('Too fast');
    expect(fast.caption.startsWith('Ideal gas · ')).toBe(true);
    expect(fast.caption).toContain('Peak Mach 1.5');
    const details = studyRows(gasResult()).find((row: { id: string }) => row.id === 'details');
    expect(JSON.stringify(details)).toContain(LIMIT);
    expect(reynoldsWarning(gasResult())).toBeNull();
  });

  it('says its fastest flow in Details, and where the file warns, leads the takeaway with how far past it ran', () => {
    const within = studyRows(gasResult()).find((row: { id: string }) => row.id === 'details');
    expect(within.children[0]).toMatchObject({ id: 'mach', label: 'Fastest flow Mach 0.53', hint: 'Subsonic, checked to Mach 1.8',
      refs: ['#o1'], summary: 'Fastest flow Mach 0.53 (subsonic), within the Mach 1.8 its solver is checked to' });
    expect(machWarning(gasResult())).toBeNull();
    expect(feaVerdict(gasResult([mach(0.53, 'passes')])).caption.startsWith('Ideal gas · Peak')).toBe(true);

    const sentence = 'Mach 2.10 is past Mach 1.8, the fastest this solver is checked to: shocks are captured over a few elements and their strength and place are approximate';
    const past = gasResult([mach(2.1, 'fails')]);
    past.analysis.mach = { value: 2.1, limit: 1.8, regime: 'supersonic', checked: false };
    past.analysis.warnings = [sentence];
    expect(feaVerdict(past).caption.startsWith('Ideal gas · past Mach 1.8 · ')).toBe(true);
    const row = studyRows(past).find((entry: { id: string }) => entry.id === 'details').children[0];
    expect(row).toMatchObject({ id: 'mach', label: sentence, refs: ['#o1'], summary: sentence });

    // Within the range, but the gas leaves the outlet faster than sound: still not checked.
    const outlet = gasResult([mach(1.2, 'fails')]);
    outlet.analysis.mach = { value: 1.2, limit: 1.8, regime: 'supersonic', checked: false };
    expect(feaVerdict(outlet).caption.startsWith('Ideal gas · supersonic outlet · ')).toBe(true);
    expect(machWarning(outlet)!.sentence).toContain('faster than sound');
  });
});
