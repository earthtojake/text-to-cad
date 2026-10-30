import * as THREE from 'three';
import { BoxGeometry, BufferAttribute, Group, Mesh } from 'three';
import { describe, expect, it } from 'vitest';
import { readFeaResult } from './feaResult.js';
import { ARROW_LENGTH, GHOST_OPACITY, MARKER_KINDS, createFeaMarkers, labelOutside, loadLabel, markerGateText, markerPoses, markerSites, pastOutline } from './feaMarkers.js';

// A unit cube in the result's glTF space, its six faces in BoxGeometry's order (+X, -X, +Y, -Y, +Z,
// -Z) as `_FACE` 0..5, wound outward as the writer winds it.
const FACES = ['bracket/face 1', 'bracket/face 2', 'bracket/face 3', 'bracket/face 4', 'bracket/face 5', 'bracket/face 6'];
function cube(study: Record<string, unknown>, displacement = [0, 0, 0], extras: Record<string, unknown> = {}) {
  const geometry = new BoxGeometry(1, 1, 1, 4, 4, 4);
  const count = geometry.getAttribute('position').count;
  const face = new Float32Array(count);
  const index = geometry.getIndex()!.array;
  for (const group of geometry.groups) for (let i = group.start; i < group.start + group.count; i += 1) face[index[i]] = group.materialIndex!;
  geometry.setAttribute('_face', new BufferAttribute(face, 1));
  geometry.setAttribute('_von_mises', new BufferAttribute(new Float32Array(count), 1));
  geometry.setAttribute('_displacement', new BufferAttribute(new Float32Array(Array.from({ length: count }, () => displacement).flat()), 3));
  geometry.setAttribute('color', new BufferAttribute(new Uint8Array(count * 4), 4, true));
  const mesh = new Mesh(geometry);
  Object.assign(mesh.userData, {
    generator: 'cadgen fea', name: 'bracket von Mises', document: 'bracket.step', occurrence: 'bracket', deformation_scale: 1, safety_factor: 276,
    faces: FACES, study: { material: { name: '6061-T6', yield_MPa: 276 }, mesh: { size_mm: 1, refined_from_mm: null }, margin: 2, ...study },
    checks: [CHECK], ramp: [[0, [0, 0, 1]], [1, [1, 0, 0]]],
    fields: [{ attribute: '_VON_MISES', name: 'von Mises stress', units: 'MPa', min: 0, max: 1, attribute_scale: 1 },
      { attribute: '_DISPLACEMENT', name: 'displacement', units: 'mm', min: 0, max: 1, attribute_scale: 1000 }], ...extras,
  });
  const root = new Group();
  root.add(mesh);
  return readFeaResult(root)!;
}
// The stress check cadgen judged: the markers draw the study, not it.
const CHECK = { kind: 'stress', label: 'Strength', value: 1, limit: 276, unit: 'MPa', ratio: 0.003623, close_at: 0.5, margin: 2, status: 'passes', where: { ref: 'bracket/face 1', at: [0, 0, 0] } };
const DOWN_ON_TOP = { type: 'force', faces: ['bracket/face 3'], vector_N: [0, 0, -300] };  // CAD -Z is glTF -Y: onto the +Y face
const STUDY = { fixtures: [{ type: 'fixed', faces: ['bracket/face 4'] }], loads: [DOWN_ON_TOP, { type: 'pressure', faces: ['bracket/face 1'], pressure_MPa: 2 }] };
const near = (a: number[], b: number[]) => a.forEach((value, k) => expect(value).toBeCloseTo(b[k], 6));
const positionsOf = (result: any) => result.mesh.geometry.getAttribute('position').array;

describe('loads and fixtures on the model', () => {
  it('stands one to five markers on each loaded or fixed face, spread over it', () => {
    const placed = markerSites(cube(STUDY));
    expect(placed.diagonal).toBeCloseTo(Math.sqrt(3), 6);
    const byFace = (ref: string) => placed.sites.filter((site: any) => site.ref === ref);
    for (const ref of ['bracket/face 3', 'bracket/face 1', 'bracket/face 4']) {
      expect(byFace(ref).length).toBeGreaterThanOrEqual(1);
      expect(byFace(ref).length).toBeLessThanOrEqual(5);
    }
    // A whole face of the cube is large for it: it gets the most, on distinct triangles.
    expect(byFace('bracket/face 3').length).toBe(5);
    expect(new Set(byFace('bracket/face 3').map((site: any) => site.triangle.join())).size).toBe(5);
    expect(placed.sites.filter((site: any) => site.ref === 'bracket/face 2')).toEqual([]);
  });

  it('points a force\'s arrows along it with their tips on the face, and a pressure\'s along the inward normal', () => {
    const result = cube(STUDY);
    const poses = markerPoses(result, markerSites(result), positionsOf(result));
    const length = ARROW_LENGTH * Math.sqrt(3);
    for (const pose of poses.filter((entry: any) => entry.kind === 'load' && entry.group === 0)) {
      near(pose.direction, [0, -1, 0]);
      expect(pose.tip[1]).toBeCloseTo(0.5, 6);
      expect(Math.abs(pose.tip[0])).toBeLessThan(0.5);
      near(pose.tail, [pose.tip[0], 0.5 + length, pose.tip[2]]);
    }
    for (const pose of poses.filter((entry: any) => entry.kind === 'load' && entry.group === 1)) {
      near(pose.direction, [-1, 0, 0]);
      expect(pose.tip[0]).toBeCloseTo(0.5, 6);
      expect(pose.tail[0]).toBeCloseTo(0.5 + length, 6);
    }
  });

  it('stands a pulling force\'s arrows on the face by their tails, pointing away', () => {
    const result = cube({ fixtures: [], loads: [{ type: 'force', faces: ['bracket/face 3'], vector_N: [0, 0, 300] }] });
    const [pose] = markerPoses(result, markerSites(result), positionsOf(result));
    near(pose.direction, [0, 1, 0]);
    expect(pose.tail[1]).toBeCloseTo(0.5, 6);
    expect(pose.tip[1]).toBeCloseTo(0.5 + ARROW_LENGTH * Math.sqrt(3), 6);
  });

  it('points each fixture\'s cone into its fixed face, its tip on it', () => {
    const result = cube(STUDY);
    const cones = markerPoses(result, markerSites(result), positionsOf(result)).filter((pose: any) => pose.kind === 'fixture');
    expect(cones.length).toBeGreaterThan(0);
    for (const cone of cones) {
      expect(cone.ref).toBe('bracket/face 4');
      expect(cone.tip[1]).toBeCloseTo(-0.5, 6);
      near(cone.direction, [0, 1, 0]);
    }
  });

  it('follows the positions drawn: deformed, the markers move with the face', () => {
    const result = cube(STUDY, [0, -0.1, 0]);
    const markers = createFeaMarkers(THREE, result);
    const rest = positionsOf(result);
    markers.update(rest);
    const before = markers.poses().map((pose: any) => pose.tip[1]);
    const moved = Float32Array.from(rest, (value: number, i: number) => (i % 3 === 1 ? value - 0.25 : value));
    markers.update(moved);
    markers.poses().forEach((pose: any, i: number) => expect(pose.tip[1]).toBeCloseTo(before[i] - 0.25, 6));
    // The instanced arrows were stood there too.
    const heads = markers.object3D.children[1] as THREE.InstancedMesh;
    const matrix = new THREE.Matrix4();
    heads.getMatrixAt(0, matrix);
    expect(new THREE.Vector3().setFromMatrixPosition(matrix).y).toBeCloseTo(0.25, 6);
    markers.dispose();
    expect(markers.object3D.parent).toBeNull();
  });

  it('draws each marker solid where it is in view and as a faint ghost where the model hides it', () => {
    const result = cube(STUDY);
    const markers = createFeaMarkers(THREE, result);
    markers.update(positionsOf(result));
    markers.style({ colours: { load: '#18181b', fixture: '#71717a' }, visible: true, chosen: () => false });
    const byName = (name: string) => markers.object3D.getObjectByName(name) as THREE.InstancedMesh;
    for (const kind of ['fea-load-shafts', 'fea-load-heads', 'fea-fixture-cones']) {
      const solid = byName(kind);
      const ghost = byName(`${kind}-ghost`);
      const solidMaterial = solid.material as THREE.MeshBasicMaterial;
      const ghostMaterial = ghost.material as THREE.MeshBasicMaterial;
      // In view: tested against the model's depth as the model is, opaque.
      expect([solidMaterial.depthTest, solidMaterial.depthFunc, solidMaterial.opacity]).toEqual([true, THREE.LessEqualDepth, 1]);
      // Hidden: only where the model is nearer, faint, writing no depth, drawn before the solid pass.
      expect([ghostMaterial.depthTest, ghostMaterial.depthFunc, ghostMaterial.depthWrite, ghostMaterial.transparent]).toEqual([true, THREE.GreaterDepth, false, true]);
      expect(ghostMaterial.opacity).toBe(GHOST_OPACITY);
      expect(ghost.renderOrder).toBeLessThan(solid.renderOrder);
      // The same markers, in the same places and colours.
      expect(ghost.count).toBe(solid.count);
      const [a, b] = [new THREE.Matrix4(), new THREE.Matrix4()];
      solid.getMatrixAt(0, a);
      ghost.getMatrixAt(0, b);
      expect(b.equals(a)).toBe(true);
      const [c, d] = [new THREE.Color(), new THREE.Color()];
      solid.getColorAt(0, c);
      ghost.getColorAt(0, d);
      expect(d.getHexString()).toBe(c.getHexString());
    }
    const disposed: string[] = [];
    markers.object3D.traverse((object: any) => object.material?.addEventListener('dispose', () => disposed.push(object.name)));
    markers.dispose();
    expect(disposed).toHaveLength(6);
  });

  it('labels each load with its amount at the load shown, beside its arrows', () => {
    const force = { type: 'force', faces: [], vector: [0, 0, -300], pressure: null } as any;
    expect(loadLabel(force)).toBe('300 N');
    expect(loadLabel(force, 1.5)).toBe('450 N');
    expect(loadLabel({ type: 'pressure', faces: [], vector: null, pressure: 2 } as any)).toBe('2 MPa');
    const result = cube(STUDY);
    const markers = createFeaMarkers(THREE, result);
    markers.update(positionsOf(result));
    const [first] = markers.labels(2);
    expect(first.text).toBe('600 N');
    expect(first.at[1]).toBeCloseTo(0.5 + ARROW_LENGTH * Math.sqrt(3), 6);
    expect(first.face[1]).toBeCloseTo(0.5, 6);
    markers.dispose();
  });

  it('labels a pulling force past its arrows\' tips, off the part, not over it at their tails', () => {
    const result = cube({ fixtures: [], loads: [{ type: 'force', faces: ['bracket/face 3'], vector_N: [0, 0, 300] }] });
    const markers = createFeaMarkers(THREE, result);
    markers.update(positionsOf(result));
    const [label] = markers.labels();
    expect(label.at[1]).toBeCloseTo(0.5 + ARROW_LENGTH * Math.sqrt(3), 6);
    expect(label.face[1]).toBeCloseTo(0.5, 6);
    markers.dispose();
  });

  it('offers a load its own arrow\'s outer end, but stands it outside the model\'s box wherever that end is inside it', () => {
    // Down along the +X face: its arrows' tails lie inside the model's box. The label's place is out of the box,
    // along the arrow; the arrow's own end is offered beside it, for the view to use only where it is in sight.
    const result = cube({ fixtures: [], loads: [{ type: 'force', faces: ['bracket/face 1'], vector_N: [0, 0, -300] }] });
    const markers = createFeaMarkers(THREE, result);
    markers.update(positionsOf(result));
    const [label] = markers.labels();
    const inside = (p: number[]) => p.every((v) => Math.abs(v) <= 0.5 + 1e-9);
    expect(inside(label.end.at)).toBe(true);
    expect(inside(label.at)).toBe(false);
    expect(label.corners).toHaveLength(8);
    const own = markers.poses().filter((pose: any) => pose.kind === 'load');
    const mine = own.find((pose: any) => pose.tail.every((value: number, k: number) => Math.abs(value - label.end.at[k]) < 1e-9));
    near(label.end.face, mine.tip);
    markers.dispose();
    // A body load runs through the part: always outside, no end offered.
    const weighed = cube({ fixtures: [], loads: [{ type: 'gravity', vector_g: [0, 0, -1] }] });
    const weight = createFeaMarkers(THREE, weighed);
    weight.update(positionsOf(weighed));
    expect(weight.labels().map((entry: any) => [entry.kind, entry.end])).toEqual([['body_load', undefined]]);
    weight.dispose();
  });
});

// A roller and a body load, from the same table as loads and fixtures, each in the ink or the muted grey.
const STYLE = { colours: { load: '#18181b', fixture: '#71717a' }, visible: true, chosen: () => false };
const colourOf = (mesh: THREE.InstancedMesh) => { const colour = new THREE.Color(); mesh.getColorAt(0, colour); return colour.getHexString(); };

describe('rollers and body loads', () => {
  it('puts a body load through the model\'s middle, labelled with its g and way, at the load shown', () => {
    const result = cube({ fixtures: [], loads: [{ type: 'gravity', vector_g: [0, 0, -1] }] });
    const markers = createFeaMarkers(THREE, result);
    markers.update(positionsOf(result));
    const [pose] = markers.poses();
    expect(pose).toMatchObject({ kind: 'body_load', ref: null });
    near(pose.direction, [0, -1, 0]);
    near(pose.tip, [0, -ARROW_LENGTH * Math.sqrt(3) / 2, 0]);
    expect(markers.labels(2).map((label: any) => label.text)).toEqual(['2 g down']);
    // Its label leaves the model along the arrow, beside it (above or below the cube), never over its middle.
    const [label] = markers.labels(2);
    expect(Math.abs(label.at[1])).toBeGreaterThan(0.5);
    expect([label.at[0], label.at[2]]).toEqual([0, 0]);
    expect(label.corners).toHaveLength(8);
    markers.dispose();
  });

  it('stands a roller\'s own cone on a plate on its face, grey, pointing into it, wherever the markers are drawn', () => {
    const rolling = { fixtures: [{ type: 'fixed', faces: ['bracket/face 4'] }, { type: 'roller', faces: ['bracket/face 2'] }], loads: [DOWN_ON_TOP] };
    const result = cube(rolling);
    const sites = markerSites(result).sites;
    expect(sites.filter((site: any) => site.kind === 'fixture').every((site: any) => site.ref === 'bracket/face 4' && site.group === 0)).toBe(true);
    const rollers = markerPoses(result, markerSites(result), positionsOf(result)).filter((pose: any) => pose.kind === 'roller');
    expect(rollers.length).toBeGreaterThan(0);
    for (const pose of rollers) {
      // Numbered by its place among every fixture, as Study's "roller:1:<ref>" row is.
      expect([pose.ref, pose.group]).toEqual(['bracket/face 2', 1]);
      expect(pose.tip[0]).toBeCloseTo(-0.5, 6);
      near(pose.direction, [1, 0, 0]);
    }
    const markers = createFeaMarkers(THREE, result);
    expect(markers.kinds).toEqual(['load', 'fixture', 'roller']);
    markers.update(positionsOf(result));
    markers.style(STYLE);
    const names = markers.object3D.children.map((child) => child.name);
    expect(names.filter((name) => name.startsWith('fea-roller'))).toEqual(['fea-roller-cones', 'fea-roller-cones-ghost', 'fea-roller-plates',
      'fea-roller-plates-ghost', 'fea-roller-balls', 'fea-roller-balls-ghost', 'fea-roller-balls-2', 'fea-roller-balls-2-ghost']);
    const cones = markers.object3D.getObjectByName('fea-roller-cones') as THREE.InstancedMesh;
    expect(colourOf(cones)).toBe('71717a');
    markers.style({ ...STYLE, visible: false });
    expect(cones.visible).toBe(false);
    expect(MARKER_KINDS.roller).toMatchObject({ tone: 'fixture', on: 'faces' });
    expect(markerGateText(['fixture', 'roller'])).toBe('Cones where it holds it, cones on rollers where it may slide.');
    expect(markers.labels().map((label: any) => label.kind)).toEqual(['load']);
    // A study with no roller draws none.
    expect(createFeaMarkers(THREE, cube(STUDY)).kinds).not.toContain('roller');
  });

  it('says beside its checkbox what it draws', () => {
    expect(Object.keys(MARKER_KINDS)).toEqual(['load', 'fixture', 'roller', 'body_load']);
    expect(Object.values(MARKER_KINDS).every((kind: any) => ['load', 'fixture'].includes(kind.tone))).toBe(true);
    expect(markerGateText(['fixture', 'load'])).toBe('Arrows where the study loads the part, cones where it holds it.');
    expect(markerGateText(['load', 'body_load'])).toBe('Arrows where the study loads the part, an arrow through its middle for its weight.');
    expect(markerGateText([])).toBe('');
  });
});

describe('a label is never on or inside the part', () => {
  const BOX = { low: [-0.5, -0.5, -0.5], high: [0.5, 0.5, 0.5] };
  const inside = (p: number[]) => p.every((v) => Math.abs(v) <= 0.5 + 1e-9);

  it('leaves the model\'s box along its marker\'s line, by the nearer way: a pin hole\'s load, a body load', () => {
    // "36000 N" in a pin hole near the +X end: the arrow's ends both inside the hole; it leaves by the near +X side.
    const hole = labelOutside({ free: [0.3, 0, 0], anchor: [0.4, 0, 0] }, BOX, Math.sqrt(3));
    expect(inside(hole.at)).toBe(false);
    expect(hole.at[0]).toBeGreaterThan(0.5);
    expect([hole.at[1], hole.at[2]]).toEqual([0, 0]);
    // The other way round (free end towards the far side): still out by the nearer +X side, back past its anchor.
    const back = labelOutside({ free: [0.2, 0, 0], anchor: [0.4, 0, 0] }, BOX, Math.sqrt(3));
    expect(back.at[0]).toBeGreaterThan(0.5);
    // Already outside: where it was.
    expect(labelOutside({ free: [0, 0.7, 0], anchor: [0, 0.5, 0] }, BOX, 1).at).toEqual([0, 0.7, 0]);
  });

  it('on screen, moves a label past the model\'s outline along its line, by the nearer way, a back face\'s too', () => {
    const square = [[0, 0], [100, 0], [100, 100], [0, 100]];
    // A sideways load on a hidden back face: its free end projects inside the outline; it runs on out of it.
    const sideways = pastOutline([60, 50], [50, 50], square, 10);
    expect(sideways).toMatchObject({ x: 110, y: 50, dx: 1, dy: 0 });
    // A load standing under the part, its free end pointing up into it: labelled below, not across the part.
    const shake = pastOutline([50, 95], [50, 105], square, 10);
    expect(shake.y).toBeGreaterThan(100);
    expect(shake.dy).toBeGreaterThan(0);
    // Outside already: only the gap.
    expect(pastOutline([50, -20], [50, -5], square, 10)).toMatchObject({ x: 50, y: -30 });
    // An arrow seen end on: straight out from the outline's middle.
    const endOn = pastOutline([70, 50], [70.5, 50], square, 10);
    expect(endOn.x).toBeGreaterThan(100);
  });
});
