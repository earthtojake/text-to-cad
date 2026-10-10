import { BufferAttribute, BufferGeometry, Group, Mesh, Ray, Vector3 } from 'three';
import { describe, expect, it } from 'vitest';
import {
  applyDeformation, deformationRange, faceLabel, faceTitle, faceRole, feaControls, feaMarkerShow, feaPresets, feaRamp, fieldValues, forceDirection,
  feaVerdict, formatValue, pickFace, readFeaResult, partRows, recolorByField, resultSourcePath, studyRows, weakestPartIndex,
  feaChecks, feaFailing, feaSections, feaShownControls, feaDefaults
} from './feaResult.js';

/** A two-triangle "result" the way GLTFLoader hands one over: lower-cased custom attributes, extras in userData. */
function resultMesh({ generator = 'cadgen fea', scale = 10, safetyFactor = 5.83 as number | null } = {}) {
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new BufferAttribute(new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0, 1, 1, 0]), 3));
  geometry.setIndex([0, 1, 2, 1, 3, 2]);
  geometry.setAttribute('color', new BufferAttribute(new Uint8Array(16).fill(7), 4, true));
  geometry.setAttribute('_von_mises', new BufferAttribute(new Float32Array([0, 50, 100, 25]), 1));
  // metres in the file; the field says x1000 to read them in mm
  geometry.setAttribute('_displacement', new BufferAttribute(new Float32Array([0, 0, 0, 0, 0, 0.001, 0, 0, 0.002, 0, 0, 0.0005]), 3));
  const mesh = new Mesh(geometry);
  Object.assign(mesh.userData, {
    generator,
    name: 'part von Mises',
    deformation_scale: scale,
    safety_factor: safetyFactor,
    fields: [
      { attribute: '_VON_MISES', name: 'von Mises stress', units: 'MPa', min: 0, max: 47.3, attribute_scale: 1 },
      { attribute: '_DISPLACEMENT', name: 'displacement', units: 'mm', min: 0, max: 0.0288, attribute_scale: 1000 },
      { attribute: '_MISSING', name: 'not in the file', units: '', min: 0, max: 1 },
    ],
  });
  const root = new Group();
  root.add(mesh);
  return { mesh, root };
}

describe('feaRamp', () => {
  it('runs blue to red through the writer\'s stops', () => {
    expect(feaRamp(0)).toEqual([0.05, 0.10, 0.90]);
    expect(feaRamp(1)).toEqual([0.90, 0.08, 0.05]);
    expect(feaRamp(0.5)).toEqual([0.10, 0.85, 0.15]);
    const [r, g, b] = feaRamp(0.125);
    expect(r).toBeCloseTo(0.05);
    expect(g).toBeCloseTo(0.475);
    expect(b).toBeCloseTo(0.925);
    expect(feaRamp(-3)).toEqual(feaRamp(0));
    expect(feaRamp(9)).toEqual(feaRamp(1));
  });
});

describe('readFeaResult', () => {
  it('finds the result mesh and keeps only the fields the geometry carries', () => {
    const { mesh, root } = resultMesh();
    const result = readFeaResult(root);
    expect(result?.mesh).toBe(mesh);
    expect(result?.deformationScale).toBe(10);
    expect(result?.fields.map((f) => f.attribute)).toEqual(['_von_mises', '_displacement']);
    expect(result?.fields[1]).toMatchObject({ units: 'mm', max: 0.0288, attributeScale: 1000 });
    expect(result?.ramp.length).toBe(5);  // no ramp in the file: the default
    expect(result?.safetyFactor).toBe(5.83);
  });

  it('is null for a GLB that is not a result', () => {
    expect(readFeaResult(resultMesh({ generator: 'something else' }).root)).toBeNull();
    expect(readFeaResult(null)).toBeNull();
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
    expect(recolorByField(mesh, vm)).toBe(true);
    expect(recolorByField(mesh, vm)).toBe(false);  // already shown
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

describe('a result\'s findings', () => {
  const finding = { check: 'fea', severity: 'error', type: 'peak', summary: 'Too much', description: 'Far too much.', items: [{ text: 'the peak', ref: '#o1.f3', at: [1, 2, 3] }, { text: 'a face', ref: null }] };
  it('are read in the file\'s order with their places, malformed ones left out', () => {
    const { mesh, root } = resultMesh();
    mesh.userData.findings = [finding, 'nope', { severity: 'note', summary: 'Soft', items: [{ at: [1, 2] }, { ref: '', at: [0, 0, NaN] }] }];
    const found = readFeaResult(root)!.findings;
    expect(found.map(entry => [entry.index, entry.severity, entry.summary])).toEqual([[0, 'error', 'Too much'], [1, 'warning', 'Soft']]);
    expect(found[0].items).toEqual([{ text: 'the peak', ref: '#o1.f3', at: [1, 2, 3] }, { text: 'a face', ref: null, at: null }]);
    expect(found[1].items.map(item => [item.ref, item.at])).toEqual([[null, null], [null, null]]);
    expect(readFeaResult(resultMesh().root)!.findings).toEqual([]);
  });

  it('name their source STEP beside the GLB unless it is absolute', () => {
    expect(resultSourcePath('/work/results/bracket.glb', 'bracket.step')).toBe('/work/results/bracket.step');
    expect(resultSourcePath('/work/results/bracket.glb', '../STEP/bracket.step')).toBe('/work/STEP/bracket.step');
    expect(resultSourcePath('/work/results/bracket.glb', '/parts/bracket.step')).toBe('/parts/bracket.step');
    expect(resultSourcePath('/work/results/bracket.glb', '')).toBe('');
    expect(resultSourcePath('FEA/x.glb', '../part.step')).toBe('part.step');
  });
});

// What S1 adds: the study the result was solved for, and the face each vertex came from.
const STUDY = {
  material: { name: '6061-T6', yield_MPa: 276, youngs_GPa: 68.9, poisson: 0.33 },
  fixtures: [{ type: 'fixed', faces: ['#o1.f1'] }],
  loads: [
    { type: 'force', faces: ['#o1.f2'], vector_N: [0, 0, -2500] },
    { type: 'pressure', faces: ['#o1.f3', '#o1.f4'], pressure_MPa: 2 },
  ],
  mesh: { size_mm: 1.9205, order: 2, elements: 52271, refined_from_mm: 2.7686 },
  margin: 2,
};
function studyResult(extras: Record<string, unknown> = { study: STUDY, faces: ['#o1.f1', '#o1.f2', '#o1.f3', '#o1.f4'] }) {
  const built = resultMesh();
  built.mesh.geometry.setAttribute('_face', new BufferAttribute(new Float32Array([0, 0, 0, 1]), 1));
  Object.assign(built.mesh.userData, extras);
  return { ...built, result: readFeaResult(built.root)! };
}
const strip = (rows: any[]): any[] => rows.map(({ id, label, detail, hint, glyph, collapsed, summary, faces, children }) =>
  ({ id, label, detail, ...(hint ? { hint } : {}), ...(glyph ? { glyph } : {}), ...(collapsed ? { collapsed } : {}), ...(summary ? { summary, faces } : {}), ...(children ? { children: strip(children) } : {}) }));

describe('a result\'s study', () => {
  it('reads as Study\'s rows in plain words: where it is held, what pushes it, what it is made of, then Details, shut', () => {
    expect(strip(studyRows(studyResult().result))).toEqual([
      { id: 'fixed', label: 'Held at', detail: '', glyph: 'fixture', children: [
        { id: 'fixed:0:#o1.f1', label: 'Face 1', detail: '', summary: 'Fixed face 1', faces: ['#o1.f1'] },
      ] },
      { id: 'loads', label: 'Pushed', detail: '', glyph: 'load', children: [
        { id: 'load:0', label: '2500 N down', detail: '', collapsed: true, summary: '2500 N load on face 2', faces: ['#o1.f2'], children: [
          { id: 'load:0:#o1.f2', label: 'Face 2', detail: '', summary: '2500 N load on face 2', faces: ['#o1.f2'] },
        ] },
        { id: 'load:1', label: '2 MPa pressure', detail: '', collapsed: true, summary: '2 MPa pressure on faces 3, 4', faces: ['#o1.f3', '#o1.f4'], children: [
          { id: 'load:1:#o1.f3', label: 'Face 3', detail: '', summary: '2 MPa pressure on face 3', faces: ['#o1.f3'] },
          { id: 'load:1:#o1.f4', label: 'Face 4', detail: '', summary: '2 MPa pressure on face 4', faces: ['#o1.f4'] },
        ] },
      ] },
      { id: 'material', label: 'Made of', detail: '', glyph: 'material', children: [{ id: 'material:name', label: '6061-T6', detail: '' }] },
      { id: 'details', label: 'Details', detail: '', collapsed: true, children: [
        { id: 'mesh', label: 'Mesh', detail: '1.9 mm elements', hint: 'refined from 2.8 mm' },
      ] },
    ]);
  });

  it('says a mesh was not refined, and a result written before the study was recorded has no rows', () => {
    const plain = studyResult({ study: { ...STUDY, mesh: { ...STUDY.mesh, refined_from_mm: null } }, faces: [] });
    expect(studyRows(plain.result).at(-1)!.children![0]).toMatchObject({ id: 'mesh', detail: '1.9 mm elements', hint: 'not refined' });
    const old = resultMesh();
    expect(readFeaResult(old.root)!.study).toBeNull();
    expect(studyRows(readFeaResult(old.root)!)).toEqual([]);
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
    expect(faceLabel('#o1.1.f17')).toBe('Face 17');
    expect(faceLabel('#o1')).toBe('#o1');
    expect(faceRole(result, '#o1.f1')).toBe('fixed');
    expect(faceRole(result, '#o1.f2')).toBe('2500 N load, down');
    expect(faceRole(result, '#o1.f4')).toBe('2 MPa pressure');
    expect(faceRole(result, '#o1.f9')).toBe('free');
  });

  it('names a face both fixed and loaded for both, in either row', () => {
    const { result } = studyResult({ study: { ...STUDY, loads: [{ type: 'force', faces: ['#o1.f1'], vector_N: [0, 0, -2500] }] }, faces: ['#o1.f1'] });
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
    expect(pickFace(result, down(0.2, 0.2))).toMatchObject({ id: '#o1.f1', ref: '#o1.f1' });
    expect(pickFace(result, down(5, 5))).toBeNull();
  });
});

// A two-part assembly: the post is vertices 0-2 (face index 0), the base vertex 3 (face index 1).
const ASSEMBLY = {
  study: STUDY,
  faces: ['#o1.1.f1', '#o1.2.f1'],
  weakest_part: 'post', weakest_part_peak_MPa: 180, safety_factor: 1.46, max_displacement_mm: 0.2,
  parts: [
    { ref: '#o1.1', name: 'post', material: '6061-T6', yield_MPa: 276, peak_MPa: 180, safety_factor: 1.46, max_displacement_mm: 0.2 },
    { ref: '#o1.2', name: 'base', material: 'Steel', yield_MPa: 250, peak_MPa: 40, safety_factor: 2.5, max_displacement_mm: 0.01 },
  ],
  connections: [
    { between: ['#o1.1', '#o1.2'], names: ['post', 'base'], type: 'bonded', area_mm2: 100, gap_mm: 0, faces: ['#o1.1.f1', '#o1.2.f1'] },
    { between: ['#o1.1', '#o1.3'], names: ['post', 'lid'], type: 'free', area_mm2: 0, gap_mm: 0.5, faces: [] },
  ],
};
function assemblyResult() {
  const built = studyResult(ASSEMBLY);
  built.mesh.geometry.setAttribute('_part', new BufferAttribute(new Float32Array([0, 0, 0, 1]), 1));
  return built;
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
    expect(rows[0]).toMatchObject({ refs: ['#o1.1'], parts: [0], summary: "Part 'post'" });
    // Either copy of a joint is the same choice: the same id, faces, tint and summary.
    const [underPost, underBase] = [rows[0].children[0], rows[1].children[0]];
    const { label: _a, ...post } = underPost;
    const { label: _b, ...base } = underBase;
    expect(post).toEqual(base);
    expect(underPost).toMatchObject({ faces: ['#o1.1.f1', '#o1.2.f1'], softParts: [0, 1], name: 'post ↔ base', summary: "Bonded joint between 'post' and 'base'" });
    expect(underPost.refs).toBeUndefined();
    // A free pair has no faces: both parts' refs go instead.
    expect(rows[0].children[1]).toMatchObject({ refs: ['#o1.1', '#o1.3'], summary: "'post' and 'lid' aren't connected" });
    expect(rows[0].children[1].faces).toBeUndefined();
    expect(studyRows(result).map((row) => row.id)).toEqual(['fixed', 'loads', 'material', 'details']);
    expect(weakestPartIndex(result)).toBe(0);
  });

  it('says a part that yields, and names a picked face\'s part', () => {
    const { result } = studyResult({ ...ASSEMBLY, parts: [{ ...ASSEMBLY.parts[0], safety_factor: 0.8 }, ASSEMBLY.parts[1]] });
    expect((partRows(result)[0] as any).detail).toBe('6061-T6 · yields');
    expect(faceTitle(result, '#o1.1.f1')).toBe('post · face 1');
    expect(faceTitle(studyResult().result, '#o1.f1')).toBe('Face 1');
  });

  it('notes a gap that was closed to bond a pair', () => {
    const { result } = studyResult({ ...ASSEMBLY, connections: [{ ...ASSEMBLY.connections[0], gap_mm: 0.1 }] });
    expect((partRows(result)[1] as any).children[0].detail).toBe('bonded · 100 mm² · 0.1 mm gap closed');
  });

  it('finds the weakest part by the name the file gives, else by the lowest factor', () => {
    const { result } = studyResult({ ...ASSEMBLY, weakest_part: 'base' });
    expect(weakestPartIndex(result)).toBe(1);
    const unnamed = studyResult({ ...ASSEMBLY, weakest_part: undefined, parts: [ASSEMBLY.parts[1], ASSEMBLY.parts[0]] }).result;
    expect(weakestPartIndex(unnamed)).toBe(1);
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
    expect(faceTitle(result, '#o1.1.f1')).toBe('bulkhead right support block · face 1');
  });

  it('names the part on an assembly\'s fixed and load rows, and leaves a single part\'s as Face N', () => {
    const study = { ...STUDY, fixtures: [{ type: 'fixed', faces: ['#o1.2.f9'] }], loads: [{ type: 'force', faces: ['#o1.1.f23'], vector_N: [0, 0, -5] }] };
    const { result } = studyResult({ ...ASSEMBLY, study });
    const rows = studyRows(result) as any[];
    const fixed = rows.find((row) => row.id === 'fixed');
    const loads = rows.find((row) => row.id === 'loads');
    expect(fixed.children[0].label).toBe('base · face 9');
    expect(loads.children[0].children[0].label).toBe('post · face 23');
    expect(loads.children[0].label).toBe('5 N down');
    // Parts that differ, one material each: how many; each part's own is the hint.
    expect(rows.find((row) => row.id === 'material').children[0]).toMatchObject({ label: '2 materials', hint: '6061-T6: 1 part, Steel: 1 part' });
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

describe('the study\'s view', () => {
  const VIEW = {
    controls: [
      { drives: 'load_scale', type: 'number', label: 'Rider weight', min: 0.5, max: 3, default: 1, unit: '×' },
      { drives: 'field', type: 'enum', label: 'Show', options: ['displacement', 'von_mises'], default: 'von_mises' },
      { drives: 'threshold', type: 'number', label: 'Show above', field: 'von_mises', min: 0, max: 300, default: 138, unit: 'MPa' },
      { drives: 'deformation', type: 'number', label: 'Exaggerate', min: 0, max: 50, default: 12 },
    ],
    presets: [{ label: 'Landing (3×)', load_scale: 3 }],
    show: { loads: true, fixtures: false },
  };
  const withView = (view: unknown) => {
    const { mesh, root } = resultMesh();
    mesh.userData.view = view;
    return readFeaResult(root)!;
  };

  it('is the agent\'s controls in its order, labels and ranges, as generic parameters', () => {
    const controls = feaControls(withView(VIEW));
    expect(controls.map((control: any) => [control.id, control.type, control.label])).toEqual([
      ['load_scale', 'number', 'Rider weight'], ['field', 'enum', 'Show'], ['threshold', 'number', 'Show above'], ['deformation', 'number', 'Exaggerate']]);
    expect(controls[0]).toMatchObject({ min: 0.5, max: 3, defaultValue: 1, unit: '×' });
    expect(controls[1].options.map((option: any) => option.label)).toEqual(['Displacement', 'Stress']);
    expect(controls[1].defaultValue).toBe('_von_mises');
    expect(controls[2]).toMatchObject({ field: '_von_mises', defaultValue: 138, unit: 'MPa' });
    expect(controls[3]).toMatchObject({ min: 0, max: 50, defaultValue: 12, unit: '×' });
  });

  it('with no view, is today\'s: a field over every field opening on stress, and deformation from 0 to four times the file\'s', () => {
    const controls = feaControls(readFeaResult(resultMesh().root)!);
    expect(controls.map((control: any) => control.id)).toEqual(['field', 'deformation']);
    expect(controls[0]).toMatchObject({ defaultValue: '_von_mises', hideLabel: true, ariaLabel: 'Result field' });
    expect(controls[1]).toMatchObject({ min: 0, max: 40, step: 0.5, defaultValue: 10, ariaLabel: 'Deformation scale' });
    // A view's deformation with no range is that slider, under the view's own label.
    expect(feaControls(withView({ controls: [{ drives: 'deformation', type: 'number', label: 'Exaggerate' }] }))[0])
      .toMatchObject({ label: 'Exaggerate', min: 0, max: 40, step: 0.5, defaultValue: 10, unit: '×' });
  });

  it('skips what this viewer does not know: a drives or a type, a field the file lacks, a range it cannot use', () => {
    const controls = feaControls(withView({ controls: [
      { drives: 'speed', type: 'number', max: 3 },
      { drives: 'deformation', type: 'enum', options: [] },
      { drives: 'field', options: ['safety_factor'] },
      { drives: 'threshold', field: 'strain', max: 3 },
      { drives: 'load_scale', min: 2, max: 1 },
      { drives: 'load_scale', max: 2, type: 'number' },
    ] }));
    expect(controls.map((control: any) => control.id)).toEqual(['load_scale']);
    expect(controls[0]).toMatchObject({ min: 0, max: 2, defaultValue: 1 });
  });

  it('falls back to the default controls when the view names none this viewer can draw, and its presets set them', () => {
    for (const controls of [[], [{ drives: 'gravity', type: 'number', max: 2 }]]) {
      expect(feaControls(withView({ controls })).map((control: any) => control.id)).toEqual(['field', 'deformation']);
    }
    const result = withView({ presets: [{ label: 'Exaggerated', deformation: 30, field: 'displacement' }] });
    expect(feaPresets(result, feaControls(result))[0].values).toEqual({ field: '_displacement', deformation: 30 });
  });

  it('names its presets as full states over the controls, and says which markers it draws', () => {
    const result = withView(VIEW);
    const presets = feaPresets(result, feaControls(result));
    expect(presets).toEqual([{ value: 'preset:0', label: 'Landing (3×)', values: { load_scale: 3, field: '_von_mises', threshold: 138, deformation: 12 } }]);
    expect(feaMarkerShow(result)).toEqual({ on: true, loads: true, fixtures: false });
    expect(feaMarkerShow(withView({ show: { loads: false, fixtures: false } }))).toEqual({ on: false, loads: true, fixtures: true });
    expect(feaMarkerShow(readFeaResult(resultMesh().root)!)).toEqual({ on: true, loads: true, fixtures: true });
  });
});

describe('a load other than the solved one', () => {
  it('halves what each part holds at twice the load, and a part can flip to yields', () => {
    const { mesh, root } = resultMesh();
    mesh.userData.parts = [{ ref: '#o1.1', name: 'post', material: 'steel', safety_factor: 3.1 }, { ref: '#o1.2', name: 'base', material: 'steel', safety_factor: 1.5 }];
    const result = readFeaResult(root)!;
    expect(partRows(result).map((row: any) => row.detail)).toEqual(['steel · holds 3.1×', 'steel · holds 1.5×']);
    expect(partRows(result, 2).map((row: any) => row.detail)).toEqual(['steel · holds 1.5×', 'steel · yields']);
    expect(partRows(result, 0).map((row: any) => row.detail)).toEqual(['steel', 'steel']);
  });

  it('draws the values at the load over the range at that load, and the values alone climbing while a ramp plays', () => {
    const { mesh, root } = resultMesh();
    const [vm] = readFeaResult(root)!.fields;
    recolorByField(mesh, vm);
    const solved = Array.from(mesh.geometry.getAttribute('color').array as Uint8Array);
    // Values and range both doubled: every colour keeps its place on the doubled bar.
    expect(recolorByField(mesh, vm, undefined, null, null, null, { valueScale: 2, rangeScale: 2 })).toBe(true);
    expect(Array.from(mesh.geometry.getAttribute('color').array as Uint8Array)).toEqual(solved);
    // Halfway up the ramp to that load: half the values under the same doubled range, so cooler.
    recolorByField(mesh, vm, undefined, null, null, null, { valueScale: 1, rangeScale: 2 });
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
    for (let frame = 1; frame <= 10; frame += 1) recolorByField(mesh, vm, undefined, null, null, null, { valueScale: frame / 10 });
    expect(reads).toBe(1);
  });

  it('greys every vertex under a threshold, comparing the threshold field at the load', () => {
    const { mesh, root } = resultMesh();
    const [vm, displacement] = readFeaResult(root)!.fields;
    recolorByField(mesh, vm, undefined, null, null, null, { threshold: { field: vm, value: 40, scale: 1 } });
    const bytes = Array.from(mesh.geometry.getAttribute('color').array as Uint8Array);
    // 0 and 25 MPa are under 40: grey. 50 and 100 keep the ramp.
    expect([bytes.slice(0, 3), bytes.slice(12, 15)]).toEqual([[150, 150, 150], [150, 150, 150]]);
    expect(bytes.slice(8, 11)).toEqual([230, 20, 13]);
    // At twice the load 25 MPa is 50: over it. On another field, the stress decides all the same.
    recolorByField(mesh, displacement, undefined, null, null, null, { valueScale: 2, rangeScale: 2, threshold: { field: vm, value: 40, scale: 2 } });
    const doubled = Array.from(mesh.geometry.getAttribute('color').array as Uint8Array);
    expect(doubled.slice(0, 3)).toEqual([150, 150, 150]);
    expect(doubled.slice(12, 15)).not.toEqual([150, 150, 150]);
  });
});

/** The ramp's colour (with alpha) for a stress over the 47.3 MPa range. */
function solvedAt(field: any, value: number) {
  // The byte table rounds t to 1/255 first.
  const [r, g, b] = feaRamp(Math.round(Math.min(1, value / field.max) * 255) / 255);
  return [Math.round(r * 255), Math.round(g * 255), Math.round(b * 255), 255];
}

describe('the verdict', () => {
  const single = (safety_factor: number | null, extras: Record<string, unknown> = {}) => studyResult({ study: STUDY, faces: [], safety_factor, ...extras }).result;

  it('says too weak under a safety factor of 1, close to the limit under the margin, strong enough from it up', () => {
    expect(feaVerdict(single(0.68))).toMatchObject({ status: 'weak', title: 'Too weak', caption: 'OK only to 0.6× this load' });
    expect(feaVerdict(single(1.5))).toMatchObject({ status: 'close', title: 'Close to the limit', caption: 'OK up to 1.5× this load' });
    expect(feaVerdict(single(2))).toMatchObject({ status: 'strong', title: 'Strong enough', caption: 'OK up to 2.0× this load' });
    // Its one check: the peak against the limit, each half kept whole; how hard the part works is the peak over the limit.
    const [row] = feaVerdict(single(0.68))!.rows;
    expect(row).toMatchObject({ status: 'weak', label: 'Strength', margin: 2, part: '' });
    expect(plain(row.line)).toBe('47 MPa, limit 276 MPa');
    expect(row.use).toBeCloseTo(1 / 0.68, 6);
    // The study's own margin sets where "close" ends.
    expect(feaVerdict(single(2.5, { study: { ...STUDY, margin: 3 } }))).toMatchObject({ status: 'close', rows: [{ margin: 3 }] });
    // A study that records no margin is held to cadgen's default.
    expect(feaVerdict(single(1.9, { study: { ...STUDY, margin: undefined } }))).toMatchObject({ status: 'close', rows: [{ margin: 2 }] });
  });

  it('follows the load shown: twice the load halves the factor and can change the word, half of it doubles it', () => {
    const result = single(1.5);
    expect(feaVerdict(result, 2)).toMatchObject({ status: 'weak', caption: 'OK only to 0.7× this load' });
    expect(plain(feaVerdict(result, 2)!.rows[0].line)).toBe('95 MPa, limit 276 MPa');
    expect(feaVerdict(result, 0.5)).toMatchObject({ status: 'strong', caption: 'OK up to 3.0× this load' });
  });

  it('with no stress says so in a neutral tone, and a result too old to judge has no verdict', () => {
    const none = single(null);
    none.fields[0].max = 0;
    expect(feaVerdict(none)).toEqual({ status: 'none', title: 'No stress', caption: 'Check the load reaches the part', rows: [] });
    expect(feaVerdict(single(1.5), 0)).toMatchObject({ status: 'none', title: 'No load', rows: [] });
    expect(feaVerdict(single(null))).toBeNull();
  });

  it('in an assembly, the stress check\'s numbers are the weakest part\'s, which its choice names', () => {
    const { result } = studyResult(ASSEMBLY);
    const [row] = feaVerdict(result)!.rows;
    expect(row).toMatchObject({ status: 'close', part: 'post' });
    expect(plain(row.line)).toBe('180 MPa, limit 276 MPa');
    expect(row.choice.summary).toMatch(/^Strength is close to its limit in post: peak 180 MPa/);
  });

  it('says what an assembly is mostly made of, a part with no material of its own taking the study\'s', () => {
    const parts = [...ASSEMBLY.parts, { ...ASSEMBLY.parts[0], ref: '#o1.3', name: 'lid', material: '' }];
    const made = (list: object[]) => (studyRows(studyResult({ ...ASSEMBLY, parts: list }).result) as any[]).find((row) => row.id === 'material').children[0];
    expect(made(parts)).toMatchObject({ label: 'Mostly 6061-T6', hint: '6061-T6: 2 parts, Steel: 1 part' });
    expect(made([ASSEMBLY.parts[0], { ...ASSEMBLY.parts[1], material: '6061-T6' }]).label).toBe('6061-T6');
  });
});

// The checks cadgen judged, as it writes them into the extras: the stress check (one over the safety
// factor) and a displacement check named in the person's words.
const STRESS_CHECK = { kind: 'stress', label: 'Strength', value: 47.3, limit: 276, unit: 'MPa', ratio: 0.171527, close_at: 0.5, margin: 2, status: 'passes',
  where: { ref: '#o1.f1', at: [0, 0, 0] } };
const SAG_CHECK = { kind: 'displacement', label: 'Tip sag', value: 0.62, limit: 0.5, unit: 'mm', ratio: 1.24, close_at: 0.9, status: 'fails',
  where: { ref: '#o1.f2', at: [60, 0, 0] }, faces: ['#o1.f2'] };
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
    expect(feaFailing(result, 1)).toBe(true);
    expect(feaFailing(result, 0.5)).toBe(false);
    expect(feaFailing(result, 0.75)).toBe(true); // 0.93 of the limit: close, within the model's own tenth
    expect(feaVerdict(result, 0.75)).toMatchObject({ status: 'close', title: 'Close to the limit' });
  });

  it('with no checks in the file, judge today\'s stress check from its safety factor, and say exactly what the safety factor says', () => {
    for (const factor of [0.68, 1.5, 2, 5.83]) {
      const old = studyResult({ study: STUDY, faces: [], safety_factor: factor }).result;
      const fresh = checked([{ ...STRESS_CHECK, ratio: Number((1 / factor).toFixed(6)), status: factor < 1 ? 'fails' : factor < 2 ? 'close' : 'passes' }], { safety_factor: factor });
      expect(feaChecks(old).map((check: any) => check.kind)).toEqual(['stress']);
      // What each says is the same; only the file's check names the face it peaks on, for a prompt.
      const said = (verdict: any) => JSON.parse(JSON.stringify(verdict, (key, value) => (key === 'choice' ? undefined : value)));
      for (const k of [1, 2, 0.5, 1.5]) expect(said(feaVerdict(fresh, k))).toEqual(said(feaVerdict(old, k)));
    }
  });

  it('skip a kind this viewer does not know, and a file whose checks it knows none of judges nothing', () => {
    const frequency = { kind: 'frequency', label: 'First mode', value: 40, limit: 60, unit: 'Hz', ratio: 0.67, status: 'passes' };
    expect(feaChecks(checked([frequency, SAG_CHECK])).map((check: any) => check.label)).toEqual(['Tip sag']);
    expect(feaVerdict(checked([frequency]))).toBeNull();
    expect(feaFailing(checked([frequency]))).toBeNull();
  });

  it('show a control `when` they fail or pass at the load shown, the load control judged where it opens, so dragging it never hides it', () => {
    const view = { controls: [
      { drives: 'load_scale', label: 'Load', min: 0.1, max: 2, default: 1, when: 'failing' },
      { drives: 'threshold', label: 'Show above', field: 'von_mises', min: 0, max: 100, default: 0, when: 'failing' },
      { drives: 'deformation', label: 'Exaggerate', min: 0, max: 50, default: 12, when: 'passing' },
      { drives: 'field', label: 'Show', when: 'sometimes' },
    ] };
    const result = checked([STRESS_CHECK, SAG_CHECK], { view });
    const controls = feaControls(result);
    const at = (values: Record<string, unknown>) => {
      const { shown, effective, loadScale } = feaShownControls(result, controls, { ...feaDefaults(controls), ...values });
      return { shown: shown.map((control: any) => control.id), effective, loadScale };
    };
    // As solved the sag fails: the load and the threshold show, the deformation waits for a pass; an unknown `when` always shows.
    expect(at({}).shown).toEqual(['load_scale', 'threshold', 'field']);
    // Dragged to half the load everything passes: the threshold hides and acts at its default, its value kept; the load stays.
    expect(at({ load_scale: 0.5, threshold: 40, deformation: 30 })).toMatchObject({
      shown: ['load_scale', 'deformation', 'field'], loadScale: 0.5, effective: { threshold: 0, deformation: 30 } });
    // While failing, the deformation is hidden and drawn at its default, whatever was chosen.
    expect(at({ deformation: 30 }).effective.deformation).toBe(12);
    // A load control shown only while passing hides on a failing result, and the load shown is its default.
    const passing = checked([STRESS_CHECK, SAG_CHECK], { view: { controls: [{ ...view.controls[0], when: 'passing' }] } });
    const loadOnly = feaControls(passing);
    expect(feaShownControls(passing, loadOnly, { load_scale: 0.5 })).toMatchObject({ shown: [], loadScale: 1 });
    // With nothing judged (no checks, no safety factor) every control shows.
    const unjudged = studyResult({ study: STUDY, faces: [], safety_factor: null, view }).result;
    expect(feaShownControls(unjudged, feaControls(unjudged), feaDefaults(feaControls(unjudged))).shown).toHaveLength(4);
  });

  it('order Study\'s sections as the view lists them, leaving out the rest and any this viewer does not know', () => {
    expect(feaSections(checked(null))).toEqual(['verdict', 'setup', 'controls', 'details']);
    expect(feaSections(checked(null, { view: { sections: ['controls', 'chart', 'verdict', 'controls'] } }))).toEqual(['controls', 'verdict']);
    expect(feaSections(checked(null, { view: { sections: ['chart'] } }))).toEqual(['verdict', 'setup', 'controls', 'details']);
  });
});
