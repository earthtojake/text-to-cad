import { BufferAttribute, BufferGeometry, Group, Mesh, Ray, Vector3 } from 'three';
import { describe, expect, it } from 'vitest';
import {
  applyDeformation, deformationRange, faceLabel, faceTitle, faceRole, feaRamp, feaSummaryLine, fieldValues, forceDirection, formatValue, pickFace, readFeaResult,
  recolorByField, resultSourcePath, ringPoint, ringTargets, studyRows
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

describe('the plain line', () => {
  it('says the peak, what it holds and how far it moves for the stress field', () => {
    const result = readFeaResult(resultMesh().root)!;
    expect(feaSummaryLine(result, result.fields[0])).toBe('Peak stress 47 MPa · holds 5.8× this load · moves up to 0.029 mm');
  });

  it('says only how far it moves for the displacement field', () => {
    const result = readFeaResult(resultMesh().root)!;
    expect(feaSummaryLine(result, result.fields[1])).toBe('Moves up to 0.029 mm');
  });

  it('says it yields under a safety factor below 1, and holds 1.0× at exactly 1', () => {
    const under = readFeaResult(resultMesh({ safetyFactor: 0.4 }).root)!;
    expect(feaSummaryLine(under, under.fields[0])).toBe('Peak stress 47 MPa · yields under this load · moves up to 0.029 mm');
    const exactly = readFeaResult(resultMesh({ safetyFactor: 1 }).root)!;
    expect(feaSummaryLine(exactly, exactly.fields[0])).toBe('Peak stress 47 MPa · holds 1.0× this load · moves up to 0.029 mm');
  });

  it('floors the factor as the findings do, so the bar and the finding agree', () => {
    const line = (safetyFactor: number) => {
      const result = readFeaResult(resultMesh({ safetyFactor }).root)!;
      return feaSummaryLine(result, result.fields[0]);
    };
    expect(line(1.96)).toContain('holds 1.9× this load');
    expect(line(12.9)).toContain('holds 12× this load');
    expect(line(0.9996)).toContain('yields under this load');
  });

  it('leaves out "holds" when there is no safety factor, and says nothing for a field it does not know', () => {
    const result = readFeaResult(resultMesh({ safetyFactor: null }).root)!;
    expect(result.safetyFactor).toBeNull();
    expect(feaSummaryLine(result, result.fields[0])).toBe('Peak stress 47 MPa · moves up to 0.029 mm');
    expect(feaSummaryLine(result, { ...result.fields[0], attribute: '_other' })).toBe('');
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

  it('ring the CAD point in the mesh\'s metres, moved by the displacement there at the scale shown', () => {
    // Two vertices whose positions carry 10x their displacement, as the writer bakes it.
    const geometry = new BufferGeometry();
    const displacement = [0, 0, 0, 0.001, 0, 0];
    geometry.setAttribute('_displacement', new BufferAttribute(new Float32Array(displacement), 3));
    geometry.setAttribute('position', new BufferAttribute(new Float32Array([0, 0, 0, 0.1 + 0.01, 0, 0]), 3));
    const mesh = new Mesh(geometry);
    const result = { mesh, deformationScale: 10 } as any;
    // CAD (100, 0, 0) mm is (0.1, 0, 0) m: the second vertex, undeformed.
    const [target] = ringTargets(result, [[100, 0, 0]]);
    expect(target.base).toEqual([0.1, 0, 0]);
    expect(ringPoint(target, 0)[0]).toBeCloseTo(0.1, 9);
    expect(ringPoint(target, 10)[0]).toBeCloseTo(0.11, 9);
    // The CAD axes become glTF's: z up is Y, y is -Z.
    expect(ringTargets(result, [[0, 20, 5]])[0].base).toEqual([0, 0.005, -0.02]);
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
const strip = (rows: any[]): any[] => rows.map(({ id, label, detail, summary, faces, children }) =>
  ({ id, label, detail, ...(summary ? { summary, faces } : {}), ...(children ? { children: strip(children) } : {}) }));

describe('a result\'s study', () => {
  it('reads as Study\'s rows: material, each fixed face, each load with its faces, and the mesh', () => {
    expect(strip(studyRows(studyResult().result))).toEqual([
      { id: 'material', label: 'Material', detail: '6061-T6 · yield 276 MPa' },
      { id: 'fixed', label: 'Fixed', detail: '', children: [
        { id: 'fixed:0:#o1.f1', label: 'Face 1', detail: 'fixed', summary: 'Fixed face 1', faces: ['#o1.f1'] },
      ] },
      { id: 'loads', label: 'Loads', detail: '', children: [
        { id: 'load:0', label: '2500 N', detail: 'down', summary: '2500 N load on face 2', faces: ['#o1.f2'], children: [
          { id: 'load:0:#o1.f2', label: 'Face 2', detail: 'loaded', summary: '2500 N load on face 2', faces: ['#o1.f2'] },
        ] },
        { id: 'load:1', label: '2 MPa pressure', detail: '', summary: '2 MPa pressure on faces 3, 4', faces: ['#o1.f3', '#o1.f4'], children: [
          { id: 'load:1:#o1.f3', label: 'Face 3', detail: 'loaded', summary: '2 MPa pressure on face 3', faces: ['#o1.f3'] },
          { id: 'load:1:#o1.f4', label: 'Face 4', detail: 'loaded', summary: '2 MPa pressure on face 4', faces: ['#o1.f4'] },
        ] },
      ] },
      { id: 'mesh', label: 'Mesh', detail: '1.9 mm elements · refined from 2.8 mm' },
    ]);
  });

  it('says a mesh was not refined, and a result written before the study was recorded has no rows', () => {
    const plain = studyResult({ study: { ...STUDY, mesh: { ...STUDY.mesh, refined_from_mm: null } }, faces: [] });
    expect(studyRows(plain.result).at(-1)).toMatchObject({ id: 'mesh', detail: '1.9 mm elements · not refined' });
    const old = resultMesh();
    expect(readFeaResult(old.root)!.study).toBeNull();
    expect(studyRows(readFeaResult(old.root)!)).toEqual([]);
  });

  it('puts a force\'s direction in words: up and down are CAD Z, the rest an axis or the unit vector', () => {
    expect(forceDirection([0, 0, -2500])).toBe('down');
    expect(forceDirection([0, 0, 10])).toBe('up');
    expect(forceDirection([5, 0, 0])).toBe('along +X');
    expect(forceDirection([0, -2500, 0])).toBe('along -Y');
    expect(forceDirection([3, 0, -4])).toBe('along (0.6, 0, -0.8)');
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
    expect(rows[1].children[0].summary).toBe('Fixed and loaded face 1');
    expect(rows[2].children[0].children[0].summary).toBe('Fixed and loaded face 1');
    expect(rows[2].children[0].summary).toBe('2500 N load on face 1');
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
  it('lists its parts and joints ahead of the study, each carrying what Quick Edit gets and what it tints', () => {
    const rows = studyRows(assemblyResult().result);
    expect(rows.slice(0, 2).map(({ id, label, detail, children }: any) => ({ id, label, detail, children: children.map((c: any) => [c.id, c.label, c.detail]) }))).toEqual([
      { id: 'parts', label: 'Parts', detail: '', children: [
        ['part:0', 'post', '6061-T6 · holds 1.4×'],
        ['part:1', 'base', 'Steel · holds 2.5×'],
      ] },
      { id: 'connections', label: 'Connections', detail: '', children: [
        ['joint:0', 'post ↔ base', 'bonded · 100 mm²'],
        ['joint:1', 'post ↔ lid', 'not connected · 0.5 mm apart'],
      ] },
    ]);
    const [parts, joints] = rows as any[];
    expect(parts.children[0]).toMatchObject({ refs: ['#o1.1'], parts: [0], summary: "Part 'post'" });
    expect(joints.children[0]).toMatchObject({ faces: ['#o1.1.f1', '#o1.2.f1'], summary: "Bonded joint between 'post' and 'base'" });
    expect(joints.children[0].refs).toBeUndefined();
    // A free pair has no faces: both parts' refs go instead.
    expect(joints.children[1]).toMatchObject({ refs: ['#o1.1', '#o1.3'], summary: "'post' and 'lid' aren't connected" });
    expect(joints.children[1].faces).toBeUndefined();
    expect(rows[2]).toMatchObject({ id: 'material' });
  });

  it('says a part that yields, and names a picked face\'s part', () => {
    const { result } = studyResult({ ...ASSEMBLY, parts: [{ ...ASSEMBLY.parts[0], safety_factor: 0.8 }, ASSEMBLY.parts[1]] });
    expect((studyRows(result)[0] as any).children[0].detail).toBe('6061-T6 · yields');
    expect(faceTitle(result, '#o1.1.f1')).toBe('post · face 1');
    expect(faceTitle(studyResult().result, '#o1.f1')).toBe('Face 1');
  });

  it('notes a gap that was closed to bond a pair', () => {
    const { result } = studyResult({ ...ASSEMBLY, connections: [{ ...ASSEMBLY.connections[0], gap_mm: 0.1 }] });
    expect((studyRows(result)[1] as any).children[0].detail).toBe('bonded · 100 mm² · 0.1 mm gap closed');
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

  it('names the weakest part on the colour bar, and the assembly as what moves', () => {
    const { result } = assemblyResult();
    expect(feaSummaryLine(result, result.fields[0])).toBe('Weakest: post · peak stress 180 MPa · holds 1.4× this load · the assembly moves up to 0.029 mm');
    expect(feaSummaryLine(result, result.fields[1])).toBe('Moves up to 0.029 mm');
  });

  it('leaves a single part exactly as it was: no groups, the plain line', () => {
    const { result } = studyResult();
    expect(result.parts).toEqual([]);
    expect(studyRows(result).map((row) => row.id)).toEqual(['material', 'fixed', 'loads', 'mesh']);
    expect(feaSummaryLine(result, result.fields[0])).toBe('Peak stress 47 MPa · holds 5.8× this load · moves up to 0.029 mm');
  });
});
