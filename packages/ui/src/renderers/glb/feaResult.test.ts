import { BufferAttribute, BufferGeometry, Group, Mesh, Ray, Vector3 } from 'three';
import { describe, expect, it } from 'vitest';
import {
  applyDeformation, deformationRange, faceLabel, faceTitle, faceRole, feaControls, feaRamp, fieldValues, forceDirection,
  feaVerdict, formatValue, pickFace, readFeaResult, partRows, recolorByField, resultSourcePath, weakestPartIndex,
  studySections, facePromptSummary
} from './feaResult.js';
import { translator } from '../../i18n/core.js';

// The writer's colour ramp (cadgen `_internal/fea/outputs.py` RAMP), as every result carries it: blue -> red.
const RAMP = [
  [0.0, [0.05, 0.10, 0.90]],
  [0.25, [0.05, 0.85, 0.95]],
  [0.5, [0.10, 0.85, 0.15]],
  [0.75, [0.98, 0.90, 0.10]],
  [1.0, [0.90, 0.08, 0.05]],
];

// The study the result was solved for, and the stress check cadgen judged (one over the safety factor), as it writes them into the extras.
const STUDY = {
  material: { name: '6061-T6', yield_MPa: 276, youngs_GPa: 68.9, poisson: 0.33 },
  fixtures: [{ type: 'fixed', faces: ['bracket/face 1'] }],
  loads: [
    { type: 'force', faces: ['bracket/face 2'], vector_N: [0, 0, -2500] },
    { type: 'pressure', faces: ['bracket/face 3', 'bracket/face 4'], pressure_MPa: 2 },
  ],
  mesh: { size_mm: 1.9205, order: 2, elements: 52271, refined_from_mm: 2.7686 },
  margin: 2,
};
const STRESS_CHECK = { kind: 'stress', label: 'Strength', value: 47.3, limit: 276, unit: 'MPa', ratio: 0.171527, close_at: 0.5, margin: 2, status: 'passes',
  where: { ref: 'bracket/face 1', at: [0, 0, 0] } };
/** The stress check at a safety factor, judged against its margin as cadgen judges it. */
const stressAt = (factor: number, margin = 2) => ({ ...STRESS_CHECK, ratio: Number((1 / factor).toFixed(6)), close_at: 1 / margin, margin,
  status: factor < 1 ? 'fails' : factor < margin ? 'close' : 'passes' });

/** A two-triangle "result" the way GLTFLoader hands one over: lower-cased custom attributes, extras in userData. */
function resultMesh({ generator = 'cadgen fea', scale = 10, safetyFactor = 5.83 as number | null } = {}) {
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new BufferAttribute(new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0, 1, 1, 0]), 3));
  geometry.setIndex([0, 1, 2, 1, 3, 2]);
  geometry.setAttribute('color', new BufferAttribute(new Uint8Array(16).fill(7), 4, true));
  geometry.setAttribute('_von_mises', new BufferAttribute(new Float32Array([0, 50, 100, 25]), 1));
  // metres in the file; the field says x1000 to read them in mm
  geometry.setAttribute('_displacement', new BufferAttribute(new Float32Array([0, 0, 0, 0, 0, 0.001, 0, 0, 0.002, 0, 0, 0.0005]), 3));
  geometry.setAttribute('_face', new BufferAttribute(new Float32Array([0, 0, 0, 0]), 1));
  const mesh = new Mesh(geometry);
  Object.assign(mesh.userData, {
    generator,
    name: 'part von Mises',
    document: 'part.step',
    occurrence: 'bracket',
    deformation_scale: scale,
    safety_factor: safetyFactor,
    findings: [],
    checks: [STRESS_CHECK],
    faces: [],
    study: STUDY,
    ramp: RAMP,
    fields: [
      { attribute: '_VON_MISES', name: 'von Mises stress', units: 'MPa', min: 0, max: 47.3, attribute_scale: 1 },
      { attribute: '_DISPLACEMENT', name: 'displacement', units: 'mm', min: 0, max: 0.0288, attribute_scale: 1000 },
    ],
  });
  const root = new Group();
  root.add(mesh);
  return { mesh, root };
}

describe('feaRamp', () => {
  it('runs blue to red through the writer\'s stops', () => {
    expect(feaRamp(0, RAMP)).toEqual([0.05, 0.10, 0.90]);
    expect(feaRamp(1, RAMP)).toEqual([0.90, 0.08, 0.05]);
    expect(feaRamp(0.5, RAMP)).toEqual([0.10, 0.85, 0.15]);
    const [r, g, b] = feaRamp(0.125, RAMP);
    expect(r).toBeCloseTo(0.05);
    expect(g).toBeCloseTo(0.475);
    expect(b).toBeCloseTo(0.925);
    expect(feaRamp(-3, RAMP)).toEqual(feaRamp(0, RAMP));
    expect(feaRamp(9, RAMP)).toEqual(feaRamp(1, RAMP));
  });
});

describe('readFeaResult', () => {
  it('finds the result mesh and reads its fields', () => {
    const { mesh, root } = resultMesh();
    const result = readFeaResult(root);
    expect(result?.mesh).toBe(mesh);
    expect(result?.deformationScale).toBe(10);
    expect(result?.fields.map((f) => f.attribute)).toEqual(['_von_mises', '_displacement']);
    expect(result?.fields[1]).toMatchObject({ units: 'mm', max: 0.0288, attributeScale: 1000 });
    expect(result?.ramp).toEqual(RAMP);
    expect(result?.safetyFactor).toBe(5.83);
  });

  it('is null for a GLB that is not a result', () => {
    expect(readFeaResult(resultMesh({ generator: 'something else' }).root)).toBeNull();
    expect(readFeaResult(null)).toBeNull();
  });

  it('throws for a result without its checks or its study, rather than show less than it holds', () => {
    for (const [key, missing] of [['checks', undefined], ['checks', []], ['study', undefined]] as const) {
      const { mesh, root } = resultMesh();
      mesh.userData[key] = missing;
      expect(() => readFeaResult(root)).toThrow(new RegExp(`no ${key}`));
    }
  });

  it('throws for a result without the vertex data cadgen writes on every vertex', () => {
    for (const [name, said] of [['color', /no vertex colours/], ['_face', /no face per vertex/]] as const) {
      const { mesh, root } = resultMesh();
      mesh.geometry.deleteAttribute(name);
      expect(() => readFeaResult(root)).toThrow(said);
    }
    const flat = resultMesh();
    flat.mesh.geometry.setAttribute('_displacement', new BufferAttribute(new Float32Array(4), 1));
    expect(() => readFeaResult(flat.root)).toThrow(/displacement is not a vector/);
    const { mesh, root } = resultMesh();
    Object.assign(mesh.userData, { parts: [{ ref: 'part1', name: 'post', material: 'Steel' }], weakest_part: 'part1' });
    expect(() => readFeaResult(root)).toThrow(/assembly has no part per vertex/);
  });

  it('throws for what cadgen always writes, missing or malformed, rather than stand a default in for it', () => {
    const cases: [Record<string, unknown>, RegExp][] = [
      [{ ramp: undefined }, /no colour ramp/],
      [{ ramp: [[0, [0, 0, 1]]] }, /no colour ramp/],
      [{ deformation_scale: undefined }, /no deformation scale/],
      [{ deformation_scale: 0 }, /no deformation scale/],
      [{ fields: [{ attribute: '_VON_MISES', name: 'von Mises stress', units: 'MPa', min: 0, max: 47.3 }] }, /field _VON_MISES has no name, units, range or scale/],
      [{ parts: [{ ref: 'part1', name: '', material: 'Steel' }] }, /part 0 has no ref, name or material/],
      [{ connections: [{ between: ['part1', 'part2'], names: ['post', 'base'], type: 'contact' }] }, /connection 0 is not a pair of parts, their names and bonded or free/],
      [{ connections: [{ between: ['part1', 'part2'], type: 'bonded' }] }, /connection 0 is not a pair/],
      [{ connections: [{ between: ['part1', 'part2'], names: ['post', 'base'], type: 'bonded', faces: [] }] }, /connection 0 has no contact area or gap/],
      // The fields: every one on the geometry, the stress and the displacement among them.
      [{ fields: undefined }, /no fields/],
      [{ fields: [{ attribute: '_MISSING', name: 'not in the file', units: '', min: 0, max: 1, attribute_scale: 1 }] }, /field _MISSING is not on its geometry/],
      [{ fields: [{ attribute: '_VON_MISES', name: 'von Mises stress', units: 'MPa', min: 0, max: 47.3, attribute_scale: 1 }] }, /no von Mises or displacement field/],
      // What names the result, and its answer: a study no load reaches is refused by cadgen, so every result has a factor.
      [{ name: undefined }, /no name, document or occurrence/],
      [{ document: '' }, /no name, document or occurrence/],
      [{ occurrence: undefined }, /no name, document or occurrence/],
      [{ safety_factor: null }, /no safety factor/],
      [{ faces: undefined }, /faces are not a list of face refs/],
      [{ faces: ['bracket/face 1', ''] }, /faces are not a list of face refs/],
      [{ parts: [{ ref: 'part1', name: 'post', material: 'Steel' }] }, /names no weakest part/],
      // Each check as cadgen judges one: no default stands in for a number, a status or a margin, and a kind it does not know is refused.
      [{ checks: [{ ...STRESS_CHECK, kind: 'temperature' }] }, /check 0 is of a kind this viewer does not know/],
      [{ checks: [{ ...STRESS_CHECK, close_at: undefined }] }, /check 0 is not a stress check as cadgen judges one/],
      [{ checks: [{ ...STRESS_CHECK, status: 'unknown' }] }, /check 0 is not a stress check/],
      [{ checks: [{ ...STRESS_CHECK, margin: undefined }] }, /check 0 is not a stress check/],
      [{ checks: [{ ...STRESS_CHECK, label: '' }] }, /check 0 is not a stress check/],
      [{ checks: [{ ...STRESS_CHECK, value: 0, ratio: 0 }] }, /check 0 is not a stress check/],
      [{ checks: [{ ...STRESS_CHECK, where: undefined }] }, /check 0 is not a stress check/],
      [{ checks: [STRESS_CHECK, { kind: 'displacement', label: 'Tip sag', value: 0.62, limit: 0, unit: 'mm', ratio: 1.24, close_at: 0.9, status: 'fails', where: { ref: null, at: [0, 0, 0] } }] },
        /check 1 is not a displacement check/],
      // The study as cadgen echoes it.
      [{ study: { ...STUDY, margin: undefined } }, /study has no margin/],
      [{ study: { ...STUDY, mesh: undefined } }, /study has no mesh size/],
      [{ study: { ...STUDY, material: { name: '6061-T6' } } }, /study material has no name or yield/],
      [{ study: { ...STUDY, fixtures: undefined } }, /study has no fixtures or loads/],
      [{ study: { ...STUDY, fixtures: [{ faces: ['bracket/face 1'] }] } }, /fixture 0 is not fixed or a roller/],
      [{ study: { ...STUDY, loads: [{ type: 'force', faces: ['bracket/face 2'] }] } }, /load 0 has no force vector/],
      [{ study: { ...STUDY, loads: [{ type: 'pressure', faces: ['bracket/face 2'] }] } }, /load 0 has no pressure/],
      [{ study: { ...STUDY, loads: [{ type: 'gravity' }] } }, /load 0 has no g vector/],
      [{ study: { ...STUDY, loads: [{ type: 'torque', faces: ['bracket/face 2'] }] } }, /load 0 is not a force, a pressure, gravity or an acceleration/],
    ];
    for (const [extras, said] of cases) {
      const { mesh, root } = resultMesh();
      Object.assign(mesh.userData, extras);
      expect(() => readFeaResult(root)).toThrow(said);
    }
  });

  it('names its source STEP beside the GLB unless it is absolute', () => {
    expect(resultSourcePath('/work/results/bracket.glb', 'bracket.step')).toBe('/work/results/bracket.step');
    expect(resultSourcePath('/work/results/bracket.glb', '../STEP/bracket.step')).toBe('/work/STEP/bracket.step');
    expect(resultSourcePath('/work/results/bracket.glb', '/parts/bracket.step')).toBe('/parts/bracket.step');
    expect(resultSourcePath('/work/results/bracket.glb', '')).toBe('');
    expect(resultSourcePath('FEA/x.glb', '../part.step')).toBe('part.step');
  });
});

describe('fields on the geometry', () => {
  it('reads a scalar as is and a vector as its scaled magnitude', () => {
    const { mesh, root } = resultMesh();
    const [vm, disp] = readFeaResult(root)!.fields;
    expect(Array.from(fieldValues(mesh, vm)!)).toEqual([0, 50, 100, 25]);
    expect(Array.from(fieldValues(mesh, disp)!)).toEqual([0, 1, 2, 0.5]);
  });

  it('recolours the byte colour attribute over the field range', () => {
    const { mesh, root } = resultMesh();
    const [vm] = readFeaResult(root)!.fields;
    expect(recolorByField(mesh, vm, RAMP)).toBe(true);
    expect(recolorByField(mesh, vm, RAMP)).toBe(false);  // already shown
    const bytes = Array.from(mesh.geometry.getAttribute('color').array as Uint8Array);
    expect(bytes.slice(0, 4)).toEqual([13, 26, 230, 255]);   // 0 MPa: blue
    expect(bytes.slice(8, 12)).toEqual([230, 20, 13, 255]);  // 100 MPa: red
    expect(mesh.geometry.getAttribute('color').version).toBeGreaterThan(0);
  });

  it('re-scales the deformation from the file positions and the true displacement', () => {
    const { mesh } = resultMesh({ scale: 10 });
    const position = mesh.geometry.getAttribute('position');
    // asking for the file's own scale first is a no-op
    expect(applyDeformation(mesh, 10, 10)).toBe(false);
    // vertex 2 sits at (0, 1, 0) with 10x of 0.002 m already baked in; at 0x it moves back by 0.02
    expect(applyDeformation(mesh, 0, 10)).toBe(true);
    expect(position.getZ(2)).toBeCloseTo(-0.02, 6);
    expect(applyDeformation(mesh, 20, 10)).toBe(true);
    expect(position.getZ(2)).toBeCloseTo(0.02, 6);
    expect(applyDeformation(mesh, 10, 10)).toBe(true);
    expect(position.getZ(2)).toBeCloseTo(0, 6);
    expect(mesh.geometry.boundingSphere).not.toBeNull();
  });
});

describe('legend helpers', () => {
  it('bounds the deformation slider by the file\'s own scale', () => {
    expect(deformationRange(190)).toEqual({ min: 0, max: 760, step: 1 });
    expect(deformationRange(1)).toEqual({ min: 0, max: 4, step: 0.1 });
  });

  it('formats ticks with the figures that tell them apart', () => {
    expect(['0', '47', '4.7', '0.470', '0.0288'].map((v) => formatValue(Number(v)))).toEqual(['0', '47.0', '4.70', '0.470', '0.0288']);
  });
});

// The face each vertex came from, and the study's faces; an assembly's, the part each vertex belongs to, as cadgen writes it.
function studyResult(extras: Record<string, unknown> = { study: STUDY, faces: ['bracket/face 1', 'bracket/face 2', 'bracket/face 3', 'bracket/face 4'] }) {
  const built = resultMesh();
  built.mesh.geometry.setAttribute('_face', new BufferAttribute(new Float32Array([0, 0, 0, 1]), 1));
  if (Array.isArray(extras.parts) && extras.parts.length) {
    built.mesh.geometry.setAttribute('_part', new BufferAttribute(new Float32Array([0, 0, 0, 1]), 1));
  }
  Object.assign(built.mesh.userData, extras);
  return { ...built, result: readFeaResult(built.root)! };
}
/** Study's rows for a result, in order: its setup, then Details. */
const studyRows = (result: any): any[] => { const { setup, details } = studySections(result) as { setup: any[]; details: any[] }; return [...setup, ...details]; };
const strip = (rows: any[]): any[] => rows.map(({ id, label, detail, hint, glyph, collapsed, summary, faces, children }) =>
  ({ id, label, detail, ...(hint ? { hint } : {}), ...(glyph ? { glyph } : {}), ...(collapsed ? { collapsed } : {}), ...(summary ? { summary, faces } : {}), ...(children ? { children: strip(children) } : {}) }));

describe('a result\'s study', () => {
  it('reads as Study\'s rows in plain words: where it is held, what pushes it, what it is made of, then Details, shut', () => {
    expect(strip(studyRows(studyResult().result))).toEqual([
      { id: 'fixed', label: 'Held at', detail: '', glyph: 'fixture', children: [
        { id: 'fixed:0:bracket/face 1', label: 'Face 1', detail: '', summary: 'Fixed face 1', faces: ['bracket/face 1'] },
      ] },
      { id: 'loads', label: 'Pushed', detail: '', glyph: 'load', children: [
        { id: 'load:0', label: '2500 N down', detail: '', collapsed: true, summary: '2500 N load on face 2', faces: ['bracket/face 2'], children: [
          { id: 'load:0:bracket/face 2', label: 'Face 2', detail: '', summary: '2500 N load on face 2', faces: ['bracket/face 2'] },
        ] },
        { id: 'load:1', label: '2 MPa pressure', detail: '', collapsed: true, summary: '2 MPa pressure on faces 3, 4', faces: ['bracket/face 3', 'bracket/face 4'], children: [
          { id: 'load:1:bracket/face 3', label: 'Face 3', detail: '', summary: '2 MPa pressure on face 3', faces: ['bracket/face 3'] },
          { id: 'load:1:bracket/face 4', label: 'Face 4', detail: '', summary: '2 MPa pressure on face 4', faces: ['bracket/face 4'] },
        ] },
      ] },
      // The material and the mesh are about the whole part (the occurrence), so they carry no faces.
      { id: 'material', label: 'Made of', detail: '', glyph: 'material', children: [
        { id: 'material:name', label: '6061-T6', detail: '', summary: 'Made of 6061-T6 (yield 276 MPa)' },
      ] },
      { id: 'details', label: 'Details', detail: '', collapsed: true, children: [
        { id: 'mesh', label: 'Mesh', detail: '1.9 mm elements', hint: 'refined from 2.8 mm', summary: 'Mesh of 1.9 mm elements, refined from 2.8 mm' },
      ] },
    ]);
  });

  it('says a mesh was not refined', () => {
    const plain = studyResult({ study: { ...STUDY, mesh: { ...STUDY.mesh, refined_from_mm: null } }, faces: [] });
    expect(studyRows(plain.result).at(-1)!.children![0]).toMatchObject({ id: 'mesh', detail: '1.9 mm elements', hint: 'not refined' });
  });

  it('puts a force\'s direction in words: up and down are CAD Z, the rest an axis or the unit vector', () => {
    expect(forceDirection([0, 0, -2500])).toBe('down');
    expect(forceDirection([0, 0, 10])).toBe('up');
    expect(forceDirection([5, 0, 0])).toBe('along +X');
    expect(forceDirection([0, -2500, 0])).toBe('along \u2212Y');
    expect(forceDirection([3, 0, -4])).toBe('along (0.6, 0, \u22120.8)');
    expect(forceDirection([0, 0, 0])).toBe('');
  });

  it('names a face by its number, and says what the study does to it', () => {
    const { result } = studyResult();
    expect(faceLabel('part1/face 17')).toBe('Face 17');
    expect(faceLabel('bracket')).toBe('bracket');
    expect(faceRole(result, 'bracket/face 1')).toBe('fixed');
    expect(faceRole(result, 'bracket/face 2')).toBe('2500 N load, down');
    expect(faceRole(result, 'bracket/face 4')).toBe('2 MPa pressure');
    expect(faceRole(result, 'bracket/face 9')).toBe('free');
  });

  it('reads a roller fixture as "Slides on", right after Held at, which keeps only the fixed ones; a picked face says it slides', () => {
    const rolling = { ...STUDY, fixtures: [{ type: 'fixed', faces: ['bracket/face 1'] }, { type: 'fixed', faces: ['bracket/face 3'] }, { type: 'roller', faces: ['bracket/face 2', 'bracket/face 4'] }] };
    const { result } = studyResult({ study: rolling, faces: ['bracket/face 1', 'bracket/face 2', 'bracket/face 3', 'bracket/face 4'] });
    const rows = strip(studyRows(result));
    expect(rows.slice(0, 2)).toEqual([
      { id: 'fixed', label: 'Held at', detail: '', glyph: 'fixture', children: [
        { id: 'fixed:0:bracket/face 1', label: 'Face 1', detail: '', summary: 'Fixed face 1', faces: ['bracket/face 1'] },
        { id: 'fixed:1:bracket/face 3', label: 'Face 3', detail: '', summary: 'Fixed and loaded face 3', faces: ['bracket/face 3'] },
      ] },
      { id: 'roller', label: 'Slides on', detail: '', glyph: 'roller', children: [
        { id: 'roller:2:bracket/face 2', label: 'Face 2', detail: '', hint: 'May slide along the face, not move off it', summary: 'Sliding and loaded face 2', faces: ['bracket/face 2'] },
        { id: 'roller:2:bracket/face 4', label: 'Face 4', detail: '', hint: 'May slide along the face, not move off it', summary: 'Sliding and loaded face 4', faces: ['bracket/face 4'] },
      ] },
    ]);
    expect(rows[2].id).toBe('loads');
    expect(faceRole(result, 'bracket/face 2')).toBe('slides along it; 2500 N load, down');
    expect(facePromptSummary(result, 'bracket/face 2')).toBe('Sliding and loaded face 2');
    const unloaded = studyResult({ study: { ...rolling, loads: [] }, faces: ['bracket/face 2'] }).result;
    expect(facePromptSummary(unloaded, 'bracket/face 2')).toBe('Slides on face 2');
    expect(faceRole(unloaded, 'bracket/face 2')).toBe('slides along it');
  });

  it('names a face both fixed and loaded for both, in either row', () => {
    const { result } = studyResult({ study: { ...STUDY, loads: [{ type: 'force', faces: ['bracket/face 1'], vector_N: [0, 0, -2500] }] }, faces: ['bracket/face 1'] });
    const rows = studyRows(result);
    expect(rows[0].children[0].summary).toBe('Fixed and loaded face 1');
    expect(rows[1].children[0].children[0].summary).toBe('Fixed and loaded face 1');
    expect(rows[1].children[0].summary).toBe('2500 N load on face 1');
  });

  it('tints the chosen faces\' vertices over the field colours, and only those', () => {
    const { mesh, result } = studyResult();
    const stress = result.fields[0];
    recolorByField(mesh, stress, result.ramp);
    const plain = Array.from(mesh.geometry.getAttribute('color').array as Uint8Array);
    expect(recolorByField(mesh, stress, result.ramp, [1])).toBe(true);
    const tinted = Array.from(mesh.geometry.getAttribute('color').array as Uint8Array);
    // Vertex 3 is face index 1's; the other three keep their colours.
    expect(tinted.slice(0, 12)).toEqual(plain.slice(0, 12));
    expect(tinted.slice(12, 15)).not.toEqual(plain.slice(12, 15));
    // Two thirds of the way to magenta: vertex 3's stress colour moves well over half way there.
    const toward = [255, 64, 242];
    for (let k = 0; k < 3; k += 1) {
      const span = toward[k] - plain[12 + k];
      if (Math.abs(span) > 20) expect((tinted[12 + k] - plain[12 + k]) / span).toBeGreaterThan(0.6);
    }
    expect(recolorByField(mesh, stress, result.ramp, [1])).toBe(false);
    recolorByField(mesh, stress, result.ramp, null);
    expect(Array.from(mesh.geometry.getAttribute('color').array as Uint8Array)).toEqual(plain);
  });

  it('picks the source face of the triangle under a ray', () => {
    const { mesh, result } = studyResult();
    mesh.updateMatrixWorld(true);
    // Above the first triangle (vertices 0, 1, 2: face index 0) and the second (1, 3, 2: its first vertex is face 0's too).
    const down = (x: number, y: number) => new Ray(new Vector3(x, y, 1), new Vector3(0, 0, -1));
    expect(pickFace(result, down(0.2, 0.2))).toMatchObject({ id: 'bracket/face 1', ref: 'bracket/face 1' });
    expect(pickFace(result, down(5, 5))).toBeNull();
  });
});

// A two-part assembly: the post is vertices 0-2 (face index 0), the base vertex 3 (face index 1).
const ASSEMBLY = {
  study: STUDY,
  checks: [{ ...stressAt(1.46), value: 180, part: 'post' }],
  faces: ['part1/face 1', 'part2/face 1'],
  weakest_part: 'post', weakest_part_peak_MPa: 180, safety_factor: 1.46, max_displacement_mm: 0.2,
  parts: [
    { ref: 'part1', name: 'post', material: '6061-T6', yield_MPa: 276, peak_MPa: 180, safety_factor: 1.46, max_displacement_mm: 0.2 },
    { ref: 'part2', name: 'base', material: 'Steel', yield_MPa: 250, peak_MPa: 40, safety_factor: 2.5, max_displacement_mm: 0.01 },
  ],
  connections: [
    { between: ['part1', 'part2'], names: ['post', 'base'], type: 'bonded', area_mm2: 100, gap_mm: 0, faces: ['part1/face 1', 'part2/face 1'] },
    { between: ['part1', 'part3'], names: ['post', 'lid'], type: 'free', area_mm2: 0, gap_mm: 0.5, faces: [] },
  ],
};
function assemblyResult() {
  return studyResult(ASSEMBLY);
}
const colours = (mesh: Mesh) => Array.from(mesh.geometry.getAttribute('color').array as Uint8Array);
const vertexColour = (bytes: number[], vertex: number) => bytes.slice(vertex * 4, vertex * 4 + 3);

describe('an assembly result', () => {
  it('lists its parts for the Parts panel, each joint under both its parts naming the other, and leaves them out of Study', () => {
    const { result } = assemblyResult();
    const rows = partRows(result) as any[];
    const shape = (row: any): any => [row.id, row.label, row.detail, ...(row.children ? [row.children.map(shape)] : [])];
    expect(rows.map(shape)).toEqual([
      ['part:0', 'post', '6061-T6 · holds 1.4×', [['joint:0', '↔ base', 'bonded · 100 mm²'], ['joint:1', '↔ lid', 'not connected · 0.5 mm apart']]],
      ['part:1', 'base', 'Steel · holds 2.5×', [['joint:0', '↔ post', 'bonded · 100 mm²']]],
    ]);
    expect(rows[0]).toMatchObject({ refs: ['part1'], parts: [0], summary: "Part 'post'" });
    // Either copy of a joint is the same choice: the same id, faces, tint and summary.
    const [underPost, underBase] = [rows[0].children[0], rows[1].children[0]];
    const { label: _a, ...post } = underPost;
    const { label: _b, ...base } = underBase;
    expect(post).toEqual(base);
    expect(underPost).toMatchObject({ faces: ['part1/face 1', 'part2/face 1'], softParts: [0, 1], name: 'post ↔ base', summary: "Bonded joint between 'post' and 'base'" });
    expect(underPost.refs).toBeUndefined();
    // A free pair has no faces: both parts' refs go instead.
    expect(rows[0].children[1]).toMatchObject({ refs: ['part1', 'part3'], summary: "'post' and 'lid' aren't connected" });
    expect(rows[0].children[1].faces).toBeUndefined();
    expect(studyRows(result).map((row) => row.id)).toEqual(['fixed', 'loads', 'material', 'details']);
    expect(weakestPartIndex(result)).toBe(0);
  });

  it('says a part that yields, and names a picked face\'s part', () => {
    const { result } = studyResult({ ...ASSEMBLY, parts: [{ ...ASSEMBLY.parts[0], safety_factor: 0.8 }, ASSEMBLY.parts[1]] });
    expect((partRows(result)[0] as any).detail).toBe('6061-T6 · yields');
    expect(faceTitle(result, 'part1/face 1')).toBe('post · face 1');
    expect(faceTitle(studyResult().result, 'bracket/face 1')).toBe('Face 1');
  });

  it('notes a gap that was closed to bond a pair', () => {
    const { result } = studyResult({ ...ASSEMBLY, connections: [{ ...ASSEMBLY.connections[0], gap_mm: 0.1 }] });
    expect((partRows(result)[1] as any).children[0].detail).toBe('bonded · 100 mm² · 0.1 mm gap closed');
  });

  it('finds the weakest part by the name the file gives; a single part has none', () => {
    const { result } = studyResult({ ...ASSEMBLY, weakest_part: 'base' });
    expect(weakestPartIndex(result)).toBe(1);
    expect(weakestPartIndex(studyResult().result)).toBe(-1);
  });

  it('tints a part\'s triangles by _part, and a joint\'s interface faces by _face, and only those', () => {
    const { mesh, result } = assemblyResult();
    const stress = result.fields[0];
    recolorByField(mesh, stress, result.ramp);
    const plain = colours(mesh);
    expect(recolorByField(mesh, stress, result.ramp, null, [0])).toBe(true);
    const part = colours(mesh);
    for (const v of [0, 1, 2]) expect(vertexColour(part, v)).not.toEqual(vertexColour(plain, v));
    expect(vertexColour(part, 3)).toEqual(vertexColour(plain, 3));
    recolorByField(mesh, stress, result.ramp, [1]);
    const joint = colours(mesh);
    for (const v of [0, 1, 2]) expect(vertexColour(joint, v)).toEqual(vertexColour(plain, v));
    expect(vertexColour(joint, 3)).not.toEqual(vertexColour(plain, 3));
    recolorByField(mesh, stress, result.ramp);
    expect(colours(mesh)).toEqual(plain);
  });

  it('spaces a part\'s underscores so names wrap at words, in rows and titles', () => {
    const named = [{ ...ASSEMBLY.parts[0], name: 'bulkhead_right_support_block' }, ASSEMBLY.parts[1]];
    const { result } = studyResult({ ...ASSEMBLY, parts: named, weakest_part: 'bulkhead_right_support_block',
      connections: [{ ...ASSEMBLY.connections[0], names: ['bulkhead_right_support_block', 'base'] }] });
    const [post, base] = partRows(result) as any[];
    expect(post).toMatchObject({ label: 'bulkhead right support block', summary: "Part 'bulkhead_right_support_block'" });
    expect(base.children[0]).toMatchObject({ label: '↔ bulkhead right support block', name: 'bulkhead right support block ↔ base',
      summary: "Bonded joint between 'bulkhead_right_support_block' and 'base'" });
    expect(faceTitle(result, 'part1/face 1')).toBe('bulkhead right support block · face 1');
  });

  it('names the part on an assembly\'s fixed and load rows, and leaves a single part\'s as Face N', () => {
    const study = { ...STUDY, fixtures: [{ type: 'fixed', faces: ['part2/face 9'] }], loads: [{ type: 'force', faces: ['part1/face 23'], vector_N: [0, 0, -5] }] };
    const { result } = studyResult({ ...ASSEMBLY, study });
    const rows = studyRows(result) as any[];
    const fixed = rows.find((row) => row.id === 'fixed');
    const loads = rows.find((row) => row.id === 'loads');
    expect(fixed.children[0].label).toBe('base · face 9');
    expect(loads.children[0].children[0].label).toBe('post · face 23');
    expect(loads.children[0].label).toBe('5 N down');
    // Parts that differ, one material each: each material inline with its part.
    expect(rows.find((row) => row.id === 'material').children[0]).toMatchObject({ label: '6061-T6 post, Steel base' });
    expect((studyRows(studyResult().result) as any[])[0].children[0].label).toBe('Face 1');
  });

  it('tints a chosen joint\'s two parts lightly while its interface faces keep the full tint', () => {
    const { mesh, result } = assemblyResult();
    const stress = result.fields[0];
    recolorByField(mesh, stress, result.ramp);
    const plain = colours(mesh);
    const [post] = partRows(result) as any[];
    expect(post.children[0].softParts).toEqual([0, 1]);
    // Interface face index 1 (vertex 3, the base) is full; the post (vertices 0-2) only soft.
    expect(recolorByField(mesh, stress, result.ramp, [1], null, [0, 1])).toBe(true);
    const both = colours(mesh);
    recolorByField(mesh, stress, result.ramp, [1]);
    const full = colours(mesh);
    expect(vertexColour(both, 3)).toEqual(vertexColour(full, 3));
    for (const v of [0, 1, 2]) {
      expect(vertexColour(both, v)).not.toEqual(vertexColour(plain, v));
      expect(vertexColour(both, v)).not.toEqual(vertexColour(full, 3));
    }
    // A free pair names parts only by ref; one that is not in the result adds none.
    expect(post.children[1].softParts).toEqual([0]);
  });

  it('leaves a single part exactly as it was: no groups', () => {
    const { result } = studyResult();
    expect(result.parts).toEqual([]);
    expect(partRows(result)).toEqual([]);
    expect(studyRows(result).map((row) => row.id)).toEqual(['fixed', 'loads', 'material', 'details']);
  });
});

describe('What you see\'s controls', () => {
  it('are the field over every field opening on stress, the deformation from 0 to four times the file\'s, and the load from 0.1 to 3', () => {
    const controls = feaControls(readFeaResult(resultMesh().root)!);
    expect(controls.map((control: any) => [control.id, control.type])).toEqual([['field', 'enum'], ['deformation', 'number'], ['load_scale', 'number']]);
    expect(controls[0]).toMatchObject({ defaultValue: '_von_mises', hideLabel: true, ariaLabel: 'Result field' });
    expect(controls[0].options.map((option: any) => option.label)).toEqual(['Stress', 'Displacement']);
    expect(controls[1]).toMatchObject({ min: 0, max: 40, step: 0.5, defaultValue: 10, ariaLabel: 'Deformation scale', unit: '×' });
    expect(controls[2]).toMatchObject({ label: 'Load', min: 0.1, max: 3, defaultValue: 1, unit: '×' });
  });
});

describe('a load other than the solved one', () => {
  it('halves what each part holds at twice the load, and a part can flip to yields', () => {
    const { mesh, root } = resultMesh();
    mesh.userData.parts = [{ ref: 'part1', name: 'post', material: 'Steel', safety_factor: 3.1 }, { ref: 'part2', name: 'base', material: 'Steel', safety_factor: 1.5 }];
    mesh.userData.weakest_part = 'base';
    mesh.geometry.setAttribute('_part', new BufferAttribute(new Float32Array([0, 0, 0, 1]), 1));
    const result = readFeaResult(root)!;
    expect(partRows(result).map((row: any) => row.detail)).toEqual(['Steel · holds 3.1×', 'Steel · holds 1.5×']);
    expect(partRows(result, 2).map((row: any) => row.detail)).toEqual(['Steel · holds 1.5×', 'Steel · yields']);
    expect(partRows(result, 0).map((row: any) => row.detail)).toEqual(['Steel', 'Steel']);
  });

  it('draws the values at the load over the range at that load, and the values alone climbing while a ramp plays', () => {
    const { mesh, root } = resultMesh();
    const [vm] = readFeaResult(root)!.fields;
    recolorByField(mesh, vm, RAMP);
    const solved = Array.from(mesh.geometry.getAttribute('color').array as Uint8Array);
    // Values and range both doubled: every colour keeps its place on the doubled bar.
    expect(recolorByField(mesh, vm, RAMP, null, null, null, { valueScale: 2, rangeScale: 2 })).toBe(true);
    expect(Array.from(mesh.geometry.getAttribute('color').array as Uint8Array)).toEqual(solved);
    // Halfway up the ramp to that load: half the values under the same doubled range, so cooler.
    recolorByField(mesh, vm, RAMP, null, null, null, { valueScale: 1, rangeScale: 2 });
    const bytes = Array.from(mesh.geometry.getAttribute('color').array as Uint8Array);
    expect(bytes.slice(4, 8)).toEqual(solvedAt(vm, 50 / 2));
  });

  it('reads a field\'s values from the geometry once, however many frames a ramp recolours', () => {
    const { mesh, root } = resultMesh();
    const [vm] = readFeaResult(root)!.fields;
    const attribute = mesh.geometry.getAttribute(vm.attribute) as any;
    const array = attribute.array;
    let reads = 0;
    Object.defineProperty(attribute, 'array', { configurable: true, get: () => { reads += 1; return array; } });
    for (let frame = 1; frame <= 10; frame += 1) recolorByField(mesh, vm, RAMP, null, null, null, { valueScale: frame / 10 });
    expect(reads).toBe(1);
  });

});

/** The ramp's colour (with alpha) for a stress over the 47.3 MPa range. */
function solvedAt(field: any, value: number) {
  // The byte table rounds t to 1/255 first.
  const [r, g, b] = feaRamp(Math.round(Math.min(1, value / field.max) * 255) / 255, RAMP);
  return [Math.round(r * 255), Math.round(g * 255), Math.round(b * 255), 255];
}

describe('the verdict', () => {
  const single = (safety_factor: number, extras: Record<string, unknown> = {}) =>
    studyResult({ study: STUDY, faces: [], safety_factor, checks: [stressAt(safety_factor)], ...extras }).result;

  it('says too weak under a safety factor of 1, close to the limit under the margin, strong enough from it up', () => {
    expect(feaVerdict(single(0.68))).toMatchObject({ status: 'weak', title: 'Too weak', caption: 'OK only to 0.6× this load' });
    expect(feaVerdict(single(1.5))).toMatchObject({ status: 'close', title: 'Close to the limit', caption: 'OK up to 1.5× this load' });
    expect(feaVerdict(single(2))).toMatchObject({ status: 'strong', title: 'Strong enough', caption: 'OK up to 2.0× this load' });
    // Its one check: the peak against the limit, each half kept whole; how hard the part works is the peak over the limit.
    const [row] = feaVerdict(single(0.68))!.rows;
    expect(row).toMatchObject({ status: 'weak', label: 'Strength', margin: 2, part: '' });
    expect(plain(row.line)).toBe('47 MPa, limit 276 MPa');
    expect(row.use).toBeCloseTo(1 / 0.68, 6);
    // The check's own margin sets where "close" ends, at any load.
    const strict = single(2.5, { study: { ...STUDY, margin: 3 }, checks: [stressAt(2.5, 3)] });
    expect(feaVerdict(strict)).toMatchObject({ status: 'close', rows: [{ margin: 3 }] });
    expect(feaVerdict(strict, 0.9)).toMatchObject({ status: 'close', caption: 'OK up to 2.7× this load' });
    expect(feaVerdict(strict, 0.8)).toMatchObject({ status: 'strong' });
  });

  it('follows the load shown: twice the load halves the factor and can change the word, half of it doubles it', () => {
    const result = single(1.5);
    expect(feaVerdict(result, 2)).toMatchObject({ status: 'weak', caption: 'OK only to 0.7× this load' });
    expect(plain(feaVerdict(result, 2)!.rows[0].line)).toBe('95 MPa, limit 276 MPa');
    expect(feaVerdict(result, 0.5)).toMatchObject({ status: 'strong', caption: 'OK up to 3.0× this load' });
  });

  it('at no load says that, in a neutral tone', () => {
    expect(feaVerdict(single(1.5), 0)).toMatchObject({ status: 'none', title: 'No load', rows: [] });
  });

  it('in an assembly, the stress check\'s numbers are the weakest part\'s, which its choice names', () => {
    const { result } = studyResult(ASSEMBLY);
    const [row] = feaVerdict(result)!.rows;
    expect(row).toMatchObject({ status: 'close', part: 'post' });
    expect(plain(row.line)).toBe('180 MPa, limit 276 MPa');
    expect(row.choice.summary).toMatch(/^Strength is close to its limit in post: peak 180 MPa/);
  });

  it('names two or three materials inline with their parts, a part with no material of its own taking the study\'s', () => {
    const parts = [...ASSEMBLY.parts, { ...ASSEMBLY.parts[0], ref: 'part3', name: 'lid', material: '' }];
    const made = (list: object[]) => (studyRows(studyResult({ ...ASSEMBLY, parts: list }).result) as any[]).find((row) => row.id === 'material').children[0];
    expect(made(parts)).toMatchObject({ label: '6061-T6 post and lid, Steel base' });
    expect(made(parts).hint).toBeUndefined();
    expect(made([ASSEMBLY.parts[0], { ...ASSEMBLY.parts[1], material: '6061-T6' }]).label).toBe('6061-T6');
    const part = (name: string, material: string) => ({ ...ASSEMBLY.parts[0], ref: `bracket.${name}`, name, material });
    // Three parts or more of one material say how many; three materials still inline.
    expect(made([part('a', 'Steel'), part('b', 'Steel'), part('c', 'Steel'), part('d', 'Copper'), part('e', 'PZT-5A')]).label)
      .toBe('Steel (3 parts), Copper d, PZT-5A e');
    // Past three materials: what most of the parts are made of, else how many, each part's own in the hint.
    const four = [part('a', 'Steel'), part('b', 'Copper'), part('c', 'PZT-5A'), part('d', 'Brass')];
    expect(made(four)).toMatchObject({ label: '4 materials', hint: 'Steel: 1 part, Copper: 1 part, PZT-5A: 1 part, Brass: 1 part' });
    expect(made([...four, part('e', 'Steel'), part('f', 'Steel'), part('g', 'Steel')])).toMatchObject({ label: 'Mostly Steel' });
  });
});

// A displacement check cadgen judged, named in the person's words, beside the stress check.
const SAG_CHECK = { kind: 'displacement', label: 'Tip sag', value: 0.62, limit: 0.5, unit: 'mm', ratio: 1.24, close_at: 0.9, status: 'fails',
  where: { ref: 'bracket/face 2', at: [60, 0, 0] }, faces: ['bracket/face 2'] };
const checked = (checks: unknown, extras: Record<string, unknown> = {}) => studyResult({ study: STUDY, faces: [], safety_factor: 5.83, checks, ...extras }).result;
const plain = (text: string) => text.replace(/\u00a0/g, ' ');

describe('the study\'s checks', () => {
  it('head the verdict with how many fail and the load the weakest takes, then every check, worst first', () => {
    const verdict = feaVerdict(checked([STRESS_CHECK, SAG_CHECK]))!;
    expect(verdict).toMatchObject({ status: 'weak', title: 'Fails 1 of 2 checks', caption: 'OK only to 0.8× this load' });
    expect(verdict.rows.map((row: any) => [row.status, row.label, plain(row.line), row.margin])).toEqual([
      ['weak', 'Tip sag', '0.62 mm, limit 0.5 mm', null], ['strong', 'Strength', '47 MPa, limit 276 MPa', 2]]);
    expect(verdict.rows[0].use).toBeCloseTo(1.24, 6);
    expect(feaVerdict(checked([{ ...STRESS_CHECK, status: 'fails', ratio: 1.2 }, SAG_CHECK]))!.title).toBe('Fails both checks');
    // A failing check comes before one that uses more of its limit but passes; then the most used.
    const big = { ...SAG_CHECK, label: 'Base sag', value: 0.3, ratio: 0.6, status: 'passes' };
    expect(feaVerdict(checked([big, STRESS_CHECK]))!.rows.map((row: any) => row.label)).toEqual(['Base sag', 'Strength']);
    expect(feaVerdict(checked([STRESS_CHECK, { ...big, status: 'close', close_at: 0.5 }, SAG_CHECK]))!.rows.map((row: any) => row.label))
      .toEqual(['Tip sag', 'Base sag', 'Strength']);
  });

  it('scale with the load: every value and share of its limit k times the solved, and a check can change its word', () => {
    const result = checked([STRESS_CHECK, SAG_CHECK]);
    const half = feaVerdict(result, 0.5)!;
    // At half the load the sag uses 0.62 of its limit: both pass, and the sag still takes the least load.
    expect(half).toMatchObject({ status: 'strong', title: 'Passes all checks', caption: 'OK up to 1.6× this load' });
    expect(half.rows.map((row: any) => [row.status, plain(row.line)])).toEqual([['strong', '0.31 mm, limit 0.5 mm'], ['strong', '24 MPa, limit 276 MPa']]);
    // 0.93 of the limit: close, within the model's own tenth.
    expect(feaVerdict(result, 0.75)).toMatchObject({ status: 'close', title: 'Close to the limit' });
  });

});

describe('a body load', () => {
  it('reads in Pushed after the face loads, chosen with the whole part, an acceleration hinted', () => {
    const study = { ...STUDY, loads: [...STUDY.loads, { type: 'gravity', vector_g: [0, 0, -1] }, { type: 'acceleration', vector_g: [5, 0, 0] }] };
    const result = studyResult({ study, faces: ['bracket/face 1', 'bracket/face 2', 'bracket/face 3', 'bracket/face 4'], occurrence: 'bracket' }).result;
    const rows = studyRows(result) as any[];
    expect(rows.map((row) => row.id)).toEqual(['fixed', 'loads', 'material', 'details']);
    expect(rows[1].children.map((row: any) => row.label)).toEqual(['2500 N down', '2 MPa pressure', '1 g down', '5 g along +X']);
    expect(rows[1].children[2]).toMatchObject({ id: 'body:0', refs: ['bracket'], summary: 'Its weight, 1 g down' });
    expect(rows[1].children[3]).toMatchObject({ id: 'body:1', refs: ['bracket'], summary: 'Accelerated 5 g along +X', hint: 'Accelerated: every part of it pushed the other way' });
  });

  it('reads Study\'s setup and Details in the person\'s language, through the locale files', () => {
    const { result } = studyResult();
    const japanese = studySections(result, translator('ja')) as { setup: any[]; details: any[] };
    expect(japanese.setup.at(-1).label).toBe(translator('ja')('fea.madeOf'));
    expect(japanese.setup.at(-1).label).not.toBe('Made of');
    expect(japanese.details[0].label).toBe(translator('ja')('fea.details'));
  });
});
