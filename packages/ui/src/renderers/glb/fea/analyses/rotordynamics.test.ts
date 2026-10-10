import { BufferAttribute, BufferGeometry, Group, Mesh } from 'three';
import { describe, expect, it } from 'vitest';
import { checkLine, checkTitle } from '../checkKinds.js';
import { feaControls, feaVerdict, readFeaResult, studyRows } from '../../feaResult.js';
import { madeOfRows } from '../setup.js';
import { deformationAt } from '../series.js';
import { fieldWord } from '../fields.js';
import { feaAnalysis } from './index.js';
import rotordynamics, { ROTOR_SETUP, WHIRL, bearingRows, discRows, rotorOf, rpmWords, spinRows, spinWords, unbalanceRows } from './rotordynamics.js';

const LIMIT = 'Linear bearings: each a spring and a damper (it may change with speed); no fluid-film nonlinearity';
const plain = (text: string) => text.replace(/[  ]/g, ' ');

// A shaft with a disc spinning 0 to 10,800 rpm about Z in bearings at faces 3 and 9, as cadgen writes it: a forward
// critical at 12,400 rpm (14.8% above the top speed), whirl shapes at two criticals, the spinning stress.
function spinningResult(extras: Record<string, unknown> = {}) {
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new BufferAttribute(new Float32Array([0, 0, 0, 0.01, 0, 0, 0, 0, 0.3]), 3));
  geometry.setIndex([0, 1, 2]);
  geometry.setAttribute('color', new BufferAttribute(new Uint8Array(12), 4, true));
  geometry.setAttribute('_von_mises', new BufferAttribute(new Float32Array([12, 3, 30]), 1));
  geometry.setAttribute('_displacement', new BufferAttribute(new Float32Array([0.001, 0, 0, 0.0005, 0, 0, 0, 0, 0]), 3));
  geometry.setAttribute('_whirl_f1', new BufferAttribute(new Float32Array([0, 0.001, 0, 0, 0.0005, 0, 0, 0, 0]), 3));
  geometry.setAttribute('_displacement_im_f0', new BufferAttribute(new Float32Array([0, -0.001, 0, 0, -0.0005, 0, 0, 0, 0]), 3));
  geometry.setAttribute('_displacement_im_f1', new BufferAttribute(new Float32Array([0.001, 0, 0, 0.0005, 0, 0, 0, 0, 0]), 3));
  geometry.setAttribute('_face', new BufferAttribute(new Float32Array([0, 0, 1]), 1));
  const mesh = new Mesh(geometry);
  Object.assign(mesh.userData, {
    generator: 'cadgen fea', name: 'rotor spinning', deformation_scale: 20, faces: ['#o1.f3', '#o1.f9'], occurrence: '#o1',
    analysis: { type: 'rotordynamics', tier: 3, word: 'Spinning', estimate: false, limits: [LIMIT], noun: 'this spin', reference_C: null, warnings: [] },
    fields: [
      { attribute: '_VON_MISES', name: 'von Mises stress (spinning at the top speed)', units: 'MPa', min: 0, max: 30, attribute_scale: 1, field: 'von_mises' },
      { attribute: '_DISPLACEMENT', name: 'whirl orbit', units: 'mm', min: 0, max: 1, attribute_scale: 1000, field: 'whirl', per_frame: true },
    ],
    series: { kind: 'mode', unit: 'rpm', default: 0, frames: [
      { value: 1, label: 'Critical · 12,400 rpm · forward', attributes: { whirl: '_DISPLACEMENT', mode_shape: '_DISPLACEMENT', displacement_im: '_DISPLACEMENT_IM_F0' } },
      { value: 2, label: 'Critical · 31,000 rpm · forward', attributes: { whirl: '_WHIRL_F1', mode_shape: '_WHIRL_F1', displacement_im: '_DISPLACEMENT_IM_F1' } },
    ] },
    study: {
      material: { name: 'Steel', yield_MPa: 250, youngs_GPa: 200, poisson: 0.29 },
      spin: { axis: 'Z', rpm: [0, 10800], sweep_rpm: 16200 },
      bearings: [{ faces: ['#o1.f3'], kxx: 20000, kyy: 20000, cxx: 5, cyy: 5 }, { faces: ['#o1.f9'], kxx: 20000, kyy: 20000, cxx: 5, cyy: 5 }],
      unbalance: [{ faces: ['#o1.f5'], g_mm: 50, phase_deg: 0 }],
      discs: [{ at_mm: 150, mass_kg: 2.5, polar_kg_mm2: 3000, diametral_kg_mm2: 1600 }],
      disc_model: 'rigid', modes_requested: 4,
      mesh: { size_mm: 3, order: 2, elements: 400, refined_from_mm: null },
    },
    checks: [
      { kind: 'critical_speed', label: 'Critical speed', value: 12400, limit: 10800, reference: 0, unit: 'rpm', ratio: 0.871, close_at: 0.869565,
        status: 'passes', mode: 1, where: { ref: '#o1.f5', at: [0, 0, 150] }, at: { frame: 0, value: 12400, unit: 'rpm' } },
      { kind: 'stability', label: 'Stability', value: 0.42, limit: 0.1, unit: '', ratio: 0.214, close_at: 0.9, status: 'passes', mode: 1,
        where: { ref: null, at: null } },
      { kind: 'stress', label: 'Spin stress', value: 30, limit: 250, unit: 'MPa', ratio: 0.12, close_at: 0.5, margin: 2, status: 'passes',
        where: { ref: null, at: [0, 0, 0.3] } },
    ],
    findings: [],
    ...extras,
  });
  const root = new Group();
  root.add(mesh);
  return readFeaResult(root)!;
}

const critical = (value: number, limit: number, reference: number, status: string, mode: number | null = 1) => ({
  kind: 'critical_speed', label: '', value, shown: value, limit, reference, unit: 'rpm', status, times: null, ...(mode ? { mode } : {}),
});

describe('rotordynamics', () => {
  it('is Spinning, Tier 3 and Lite: no load control, its three checks, its setup, Whirl and no markers', () => {
    expect(rotordynamics).toMatchObject({ name: 'rotordynamics', tier: 3, word: 'Spinning', noun: 'this spin', family: null, scalesWithLoad: false,
      limitWord: 'Lite', checks: ['critical_speed', 'stability', 'stress'], displayTitle: 'Bearings' });
    expect(rotordynamics.checkLabels).toEqual({ stress: 'Spin stress' });
    expect(rotordynamics.markers).toEqual([]);
    expect(ROTOR_SETUP).toEqual([spinRows, bearingRows, discRows, unbalanceRows, madeOfRows]);
    const result = spinningResult();
    expect(feaAnalysis(result)).toBe(rotordynamics);
    // Whirl turns the shape through its orbit: the same clip kind as Vibrate (re·cos − im·sin).
    expect(rotordynamics.routine(result)).toBe(WHIRL);
    expect(WHIRL).toMatchObject({ label: 'Whirl', kind: 'vibrate' });
    expect(rotordynamics.routine({ ...result, series: null })).toBeNull();
  });

  it('says a critical speed against the operating speeds, floored so it never overstates the margin', () => {
    expect(plain(checkLine(critical(12400, 10800, 0, 'close')))).toBe('Critical at 12,400 rpm, 14% above the 10,800 rpm top speed');
    expect(plain(checkLine(critical(7000, 8000, 10800, 'close')))).toBe('Critical at 7,000 rpm, 12% below the 8,000 rpm lowest speed');
    expect(plain(checkLine(critical(9200, 10800, 0, 'fails')))).toBe('Critical at 9,200 rpm, inside 0–10,800 rpm');
    expect(plain(checkLine(critical(9200, 10800, 8000, 'fails')))).toBe('Critical at 9,200 rpm, inside 8,000–10,800 rpm');
    expect(plain(checkLine(critical(16200, 10800, 0, 'passes', null)))).toBe('No critical up to 16,200 rpm, 50% above the 10,800 rpm top speed');
    expect(['fails', 'close', 'passes'].map((status) => checkTitle({ kind: 'critical_speed' }, status)))
      .toEqual(['Runs at a critical speed', 'Close to a critical speed', 'Clear of critical speeds']);
    expect([850, 3050, 12437, 120000].map(rpmWords)).toEqual(['850 rpm', '3,050 rpm', '12,400 rpm', '120,000 rpm']);
  });

  it('says the whirl\'s damping, and that an undamped rotor neither grows nor dies away', () => {
    const stability = (value: number, mode: number | null = 1) => ({ kind: 'stability', label: '', value, shown: value, limit: 0.1, unit: '',
      times: null, ...(mode ? { mode } : {}) });
    expect(plain(checkLine(stability(0.0812)))).toBe('Log decrement 0.081, needs 0.1');
    expect(plain(checkLine(stability(-0.03)))).toBe('Log decrement -0.03, needs 0.1');
    expect(plain(checkLine(stability(0, null)))).toBe('No damping modelled, neither grows nor dies away');
    expect(['fails', 'close', 'passes'].map((status) => checkTitle({ kind: 'stability' }, status))).toEqual(['Unstable', 'Barely damped', 'Stable']);
  });

  it('leads its verdict with "Lite · " and its rows with the critical, the damping and the spin stress', () => {
    const verdict = feaVerdict(spinningResult());
    expect(verdict.status).toBe('strong');
    expect(verdict.rows.map((row: { label: string }) => row.label)).toEqual(['Critical speed', 'Stability', 'Spin stress']);
    expect(plain(verdict.rows[0].line)).toBe('Critical at 12,400 rpm, 14% above the 10,800 rpm top speed');
    expect(plain(verdict.rows[1].line)).toBe('Log decrement 0.42, needs 0.1');
    expect(plain(verdict.caption).startsWith('Lite · ')).toBe(true);
    // Inside the operating range: the headline is the critical speed's.
    const inside = spinningResult({ checks: [{ kind: 'critical_speed', label: 'Critical speed', value: 9200, limit: 10800, reference: 0, unit: 'rpm',
      ratio: 1.148, close_at: 0.869565, status: 'fails', mode: 1, where: { ref: null, at: null }, at: { frame: 0, value: 9200, unit: 'rpm' } }] });
    const failing = feaVerdict(inside);
    expect(failing.title).toBe('Runs at a critical speed');
    expect(plain(failing.caption)).toBe('Lite · Critical at 9,200 rpm, inside 0–10,800 rpm');
  });

  it('opens on the whirl picker, the field (stress, whirl) and the deformation; each frame deforms by its own orbit', () => {
    const result = spinningResult();
    const controls = feaControls(result);
    expect(controls.map((control: { drives: string }) => control.drives)).toEqual(['mode', 'field', 'deformation']);
    expect(controls[0]).toMatchObject({ label: 'Whirl', defaultValue: '0' });
    expect(controls[0].options.map((option: { label: string }) => option.label)).toEqual(['Critical · 12,400 rpm · forward', 'Critical · 31,000 rpm · forward']);
    expect(controls[1].options.map((option: { label: string }) => option.label)).toEqual(['Stress', 'Whirl']);
    expect(fieldWord({ attribute: '_displacement', view: 'whirl', name: 'whirl orbit' })).toBe('Whirl');
    expect(deformationAt(result, 0)).toEqual({ attribute: '_displacement', imaginary: '_displacement_im_f0' });
    expect(deformationAt(result, 1)).toEqual({ attribute: '_whirl_f1', imaginary: '_displacement_im_f1' });
  });

  it('sets up how it spins, its bearings, the disc and the unbalance it adds, in plain words, each chosen with its faces', () => {
    const result = spinningResult();
    expect(rotorOf(result)?.axis).toBe('Z');
    expect(spinWords(rotorOf(result))).toBe('Spins 0 to 10,800 rpm about Z');
    expect(spinWords({ axis: 'X', rpm: [3000, 3000] })).toBe('Spins at 3,000 rpm about X');
    expect(spinWords({ axis: 'Z', rpm: [2000, 12000] })).toBe('Spins 2,000 to 12,000 rpm about Z');
    const rows = studyRows(result);
    expect(rows.slice(0, 5).map((row: { label: string }) => row.label)).toEqual(['Spins', 'Bearings', 'Discs added', 'Unbalance', 'Made of']);
    expect(rows[0].children[0]).toMatchObject({ label: 'Spins 0 to 10,800 rpm about Z', refs: ['#o1'] });
    expect(rows[1].children[0]).toMatchObject({ label: 'Bearings at face 3 and face 9', faces: ['#o1.f3', '#o1.f9'],
      hint: '20,000 N/mm, 5 N·s/mm', summary: 'Bearings at face 3 and face 9' });
    expect(rows[2].children[0]).toMatchObject({ label: '2.5 kg disc at 150 mm along Z' });
    expect(rows[3].children[0]).toMatchObject({ label: '50 g·mm at face 5', faces: ['#o1.f5'] });
    // A rigid bearing at a station rather than a face; no study spin, no rows.
    const atStation = spinningResult({ study: { spin: { axis: 'Z', rpm: [0, 6000] }, bearings: [{ at_mm: 0, rigid: true }, { faces: ['#o1.f9'], clamped: true }] } });
    expect(bearingRows(atStation)[0].children[0]).toMatchObject({ label: 'Bearings at 0 mm along Z and face 9', hint: 'Rigid; Clamped: holds the shaft and its tilt' });
    expect(spinRows(spinningResult({ study: {} }))).toEqual([]);
    const details = rows.find((row: { id: string }) => row.id === 'details');
    expect(details.children.find((row: { id: string }) => row.id === 'limits').children.map((row: { label: string }) => row.label)).toEqual([LIMIT]);
  });
});
