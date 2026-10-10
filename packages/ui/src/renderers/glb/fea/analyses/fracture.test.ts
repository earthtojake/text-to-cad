import { BufferAttribute, BufferGeometry, Group, Mesh } from 'three';
import { describe, expect, it } from 'vitest';
import { checkLine, checkTitle } from '../checkKinds.js';
import { feaControls, feaVerdict, readFeaResult, studyRows } from '../../feaResult.js';
import { markerGateText, markerPoses, markerSites } from '../../feaMarkers.js';
import { heldRows, madeOfRows, pushedRows } from '../setup.js';
import { feaAnalysis } from './index.js';
import { LOAD_RAMP } from './static.js';
import fracture, { FRACTURE_SETUP, crackOf, crackRows, crackWords } from './fracture.js';

const LIMIT = 'Linear-elastic fracture mechanics: the material stays elastic around the crack (small-scale yielding); no ductile tearing or plastic collapse';
const plain = (text: string) => text.replace(/[\u00a0\u202f]/g, ' ');

// A plate with a 2 mm edge crack on face 4, as cadgen writes it: its K 18 MPa√m at the deepest point against 29.
function crackedResult(extras: Record<string, unknown> = {}) {
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new BufferAttribute(new Float32Array([0, 0, 0, 0.04, 0, 0, 0, 0.006, 0]), 3));
  geometry.setIndex([0, 1, 2]);
  geometry.setAttribute('color', new BufferAttribute(new Uint8Array(12), 4, true));
  geometry.setAttribute('_von_mises', new BufferAttribute(new Float32Array([67, 10, 30]), 1));
  geometry.setAttribute('_displacement', new BufferAttribute(new Float32Array(9), 3));
  geometry.setAttribute('_face', new BufferAttribute(new Float32Array([0, 0, 1]), 1));
  const mesh = new Mesh(geometry);
  Object.assign(mesh.userData, {
    generator: 'cadgen fea', name: 'plate crack', deformation_scale: 40, faces: ['#o1.f3', '#o1.f4'], occurrence: '#o1',
    crack: { kind: 'edge', words: '2 mm edge crack on #o1.f4', face: '#o1.f4', size_mm: 2, K_max_MPa_sqrt_m: 18.04, K_point: 'the deepest point',
      toughness_MPa_sqrt_m: 29, front_mm: [[0, 2, 0], [0, 2, 1], [0, 2, 2]], K_front: [17.1, 18.04, 17.2] },
    analysis: { type: 'fracture', tier: 3, word: 'Cracks', estimate: false, limits: [LIMIT], noun: 'this load', reference_C: null, warnings: [] },
    fields: [
      { attribute: '_VON_MISES', name: 'von Mises stress', units: 'MPa', min: 0, max: 67, attribute_scale: 1, field: 'von_mises' },
      { attribute: '_DISPLACEMENT', name: 'displacement', units: 'mm', min: 0, max: 0.05, attribute_scale: 1000, field: 'displacement' },
    ],
    study: {
      material: { name: 'Aluminum 6061-T6', yield_MPa: 276, youngs_GPa: 68.9, poisson: 0.33 },
      fixtures: [{ type: 'roller', faces: ['#o1.f3'] }], loads: [{ type: 'pressure', faces: ['#o1.f4'], pressure_MPa: -100 }],
      crack: { kind: 'edge', face: '#o1.f4', at_mm: [0, 0, 1], normal: [0, 1, 0], size_mm: 2, words: '2 mm edge crack on #o1.f4' },
      mesh: { size_mm: 3, order: 2, elements: 400, refined_from_mm: null },
    },
    checks: [{ kind: 'fracture', label: 'Crack', value: 18.04, limit: 29, unit: 'MPa√m', ratio: 0.622, close_at: 0.666667, margin: 1.5,
      status: 'passes', where: { ref: null, at: [0, 2, 1] }, point: 'the deepest point' }],
    findings: [],
    ...extras,
  });
  const root = new Group();
  root.add(mesh);
  return readFeaResult(root)!;
}

describe('fracture', () => {
  it('is Cracks, Tier 3 and Lite: it follows the load, its checks, static setup with its crack, the Load ramp and the front', () => {
    expect(fracture).toMatchObject({ name: 'fracture', tier: 3, word: 'Cracks', noun: 'this load', family: null, scalesWithLoad: true,
      limitWord: 'Lite', checks: ['fracture', 'crack_life', 'stress', 'displacement'], displayTitle: 'Loads, fixtures and the crack' });
    expect(fracture.markers).toEqual(['load', 'fixture', 'body_load', 'crack_front']);
    expect(FRACTURE_SETUP).toEqual([heldRows, pushedRows, crackRows, madeOfRows]);
    const result = crackedResult();
    expect(feaAnalysis(result)).toBe(fracture);
    expect(fracture.routine(result)).toBe(LOAD_RAMP);
  });

  it('says its verdict with "Lite · " and the load the crack takes, its row line with where K peaks', () => {
    const verdict = feaVerdict(crackedResult());
    expect(verdict.title).toBe('Crack is safe');
    expect(verdict.status).toBe('strong');
    expect(plain(verdict.caption)).toBe('Lite · OK up to 1.6× this load');
    expect(plain(verdict.rows[0].line)).toBe('K 18 MPa√m at the deepest point, toughness 29 MPa√m');
    // Twice the load: K 36 against 29, the crack grows.
    const doubled = feaVerdict(crackedResult(), 2);
    expect(doubled.title).toBe('Crack grows');
    expect(plain(doubled.rows[0].line)).toBe('K 36 MPa√m at the deepest point, toughness 29 MPa√m');
    expect(feaControls(crackedResult()).map((control: { drives: string }) => control.drives)).toContain('field');
  });

  it('lists the crack in Study, its K the hint, chosen with its face; Details lists its limits', () => {
    const rows = studyRows(crackedResult());
    expect(rows.slice(0, 4).map((row: { label: string }) => row.label)).toEqual(['Slides on', 'Pushed', 'Crack', 'Made of']);
    const crack = rows.find((row: { id: string }) => row.id === 'crack');
    expect(crack.children[0]).toMatchObject({ label: '2 mm edge crack on face 4', hint: 'K 18 MPa√m at the deepest point', faces: ['#o1.f4'],
      summary: 'Crack: 2 mm edge crack on face 4 (K 18 MPa√m at the deepest point)' });
    const details = rows.find((row: { id: string }) => row.id === 'details');
    expect(details.children.find((row: { id: string }) => row.id === 'limits').children.map((row: { label: string }) => row.label)).toEqual([LIMIT]);
    expect(crackRows({ mesh: { userData: {} } })).toEqual([]);
  });

  it('says every kind of crack in words', () => {
    const crack = (kind: string, more: Record<string, unknown> = {}) => crackOf({ mesh: { userData: { study: { crack: { kind, size_mm: 1.5, face: '#o1.f4', ...more } } } } });
    expect(crackWords(crack('edge'))).toBe('1.5 mm edge crack on face 4');
    expect(crackWords(crack('surface', { length_mm: 6 }))).toBe('1.5 mm deep surface crack, 6 mm long, on face 4');
    expect(crackWords(crack('surface'))).toBe('1.5 mm deep surface crack, 3 mm long, on face 4');
    expect(crackWords(crack('through', { face: '#o1.f6' }))).toBe('3 mm through crack across face 6');
    expect(crackWords(crack('embedded', { face: null }))).toBe('3 mm embedded crack');
    expect(crackOf({ mesh: { userData: { study: { crack: { kind: 'notch', size_mm: 1 } } } } })).toBeNull();
  });

  it('draws a dot at each station of the crack front, where the file puts it', () => {
    const result = crackedResult();
    const placed = markerSites(result);
    const front = placed.sites.filter((site: { kind: string }) => site.kind === 'crack_front');
    expect(front.length).toBe(3);
    expect(markerGateText(['load', 'crack_front'])).toBe("Arrows where the study loads the part, dots along the crack's front.");
    const positions = result.mesh.geometry.getAttribute('position').array;
    const poses = markerPoses(result, placed, positions).filter((pose: { kind: string }) => pose.kind === 'crack_front');
    // CAD (0, 2, 1) mm is the mesh's (0, 0.001, -0.002) m: glTF axes (x, z, -y).
    expect(poses[1].tip.map((c: number) => Number(c.toFixed(6)))).toEqual([0, 0.001, -0.002]);
  });

  it('words its checks as cadgen writes them', () => {
    const check = { kind: 'fracture', value: 18.04, shown: 18.04, limit: 29, unit: 'MPa√m', point: 'the deepest point' };
    expect(['fails', 'close', 'passes'].map((status) => checkTitle(check, status))).toEqual(['Crack grows', 'Close to the limit', 'Crack is safe']);
    expect(plain(checkLine(check))).toBe('K 18 MPa√m at the deepest point, toughness 29 MPa√m');
    expect(plain(checkLine({ ...check, point: undefined }))).toBe('K 18 MPa√m, toughness 29 MPa√m');
    const life = { kind: 'crack_life', value: 346700, shown: 346700, limit: 100000, need: 100000, unit: 'cycles' };
    expect(['fails', 'close', 'passes'].map((status) => checkTitle(life, status))).toEqual(['Breaks too soon', 'Close to the limit', 'Lasts long enough']);
    expect(plain(checkLine(life))).toBe('Grows to critical in 347 thousand cycles, needs 100 thousand');
  });
});
