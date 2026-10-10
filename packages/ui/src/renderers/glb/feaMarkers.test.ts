import * as THREE from 'three';
import { BoxGeometry, BufferAttribute, Group, Mesh } from 'three';
import { describe, expect, it } from 'vitest';
import { readFeaResult } from './feaResult.js';
import { ARROW_LENGTH, GHOST_OPACITY, MARKER_KINDS, createFeaMarkers, dropWords, loadLabel, markerGateText, markerPoses, markerSites, shakeWords } from './feaMarkers.js';

// A unit cube in the result's glTF space, its six faces in BoxGeometry's order (+X, -X, +Y, -Y, +Z,
// -Z) as `_FACE` 0..5, wound outward as the writer winds it.
const FACES = ['#o1.f1', '#o1.f2', '#o1.f3', '#o1.f4', '#o1.f5', '#o1.f6'];
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
    generator: 'cadgen fea', deformation_scale: 1, faces: FACES, study,
    fields: [{ attribute: '_VON_MISES', name: 'von Mises stress', units: 'MPa', min: 0, max: 1 }], ...extras,
  });
  const root = new Group();
  root.add(mesh);
  return readFeaResult(root)!;
}
const DOWN_ON_TOP = { type: 'force', faces: ['#o1.f3'], vector_N: [0, 0, -300] };  // CAD -Z is glTF -Y: onto the +Y face
const STUDY = { fixtures: [{ type: 'fixed', faces: ['#o1.f4'] }], loads: [DOWN_ON_TOP, { type: 'pressure', faces: ['#o1.f1'], pressure_MPa: 2 }] };
const near = (a: number[], b: number[]) => a.forEach((value, k) => expect(value).toBeCloseTo(b[k], 6));
const positionsOf = (result: any) => result.mesh.geometry.getAttribute('position').array;

describe('loads and fixtures on the model', () => {
  it('stands one to five markers on each loaded or fixed face, spread over it', () => {
    const placed = markerSites(cube(STUDY));
    expect(placed.diagonal).toBeCloseTo(Math.sqrt(3), 6);
    const byFace = (ref: string) => placed.sites.filter((site: any) => site.ref === ref);
    for (const ref of ['#o1.f3', '#o1.f1', '#o1.f4']) {
      expect(byFace(ref).length).toBeGreaterThanOrEqual(1);
      expect(byFace(ref).length).toBeLessThanOrEqual(5);
    }
    // A whole face of the cube is large for it: it gets the most, on distinct triangles.
    expect(byFace('#o1.f3').length).toBe(5);
    expect(new Set(byFace('#o1.f3').map((site: any) => site.triangle.join())).size).toBe(5);
    expect(placed.sites.filter((site: any) => site.ref === '#o1.f2')).toEqual([]);
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
    const result = cube({ fixtures: [], loads: [{ type: 'force', faces: ['#o1.f3'], vector_N: [0, 0, 300] }] });
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
      expect(cone.ref).toBe('#o1.f4');
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
    markers.style({ colours: { load: '#18181b', fixture: '#71717a' }, visible: { loads: true, fixtures: true }, chosen: () => false });
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
    const result = cube({ fixtures: [], loads: [{ type: 'force', faces: ['#o1.f3'], vector_N: [0, 0, 300] }] });
    const markers = createFeaMarkers(THREE, result);
    markers.update(positionsOf(result));
    const [label] = markers.labels();
    expect(label.at[1]).toBeCloseTo(0.5 + ARROW_LENGTH * Math.sqrt(3), 6);
    expect(label.face[1]).toBeCloseTo(0.5, 6);
    markers.dispose();
  });
});

// Track V1: every other kind of marker, from one table, each in the ink or the muted grey.
const HEATED = { fixtures: [], loads: [], temperatures: [{ faces: ['#o1.f4'], C: 25 }], heat: [{ faces: ['#o1.f3'], W: 15 }],
  convection: [{ faces: ['#o1.f1', '#o1.f2'], h_W_m2K: 10, ambient_C: 25 }] };
const STYLE = { colours: { load: '#18181b', fixture: '#71717a' }, visible: { loads: true, fixtures: true }, chosen: () => false };
const colourOf = (mesh: THREE.InstancedMesh) => { const colour = new THREE.Color(); mesh.getColorAt(0, colour); return colour.getHexString(); };

describe('every other kind of marker', () => {
  it('draws what the analysis lists, each kind in its tone, following the switch for its bucket', () => {
    expect(Object.values(MARKER_KINDS).every((kind: any) => ['load', 'fixture'].includes(kind.tone) && ['loads', 'fixtures'].includes(kind.bucket))).toBe(true);
    const result = cube(HEATED, [0, 0, 0], { analysis: { type: 'thermal' } });
    const markers = createFeaMarkers(THREE, result);
    expect(markers.kinds).toEqual(['temperature', 'heat', 'convection']);
    markers.update(positionsOf(result));
    markers.style(STYLE);
    const byName = (name: string) => markers.object3D.getObjectByName(name) as THREE.InstancedMesh;
    // Loads and fixtures keep their six meshes, empty here; the other kinds follow them, each with its ghost.
    expect(markers.object3D.children.slice(0, 6).map((child: any) => child.count)).toEqual([0, 0, 0, 0, 0, 0]);
    expect(markers.object3D.children.slice(6).map((child) => child.name)).toEqual([
      'fea-temperature-dots', 'fea-temperature-dots-ghost', 'fea-heat-shafts', 'fea-heat-shafts-ghost', 'fea-heat-heads', 'fea-heat-heads-ghost',
      'fea-convection-strokes', 'fea-convection-strokes-ghost', 'fea-convection-strokes-2', 'fea-convection-strokes-2-ghost']);
    // A temperature and the air are what the part gives heat to, grey; heat going in is the ink.
    expect([colourOf(byName('fea-temperature-dots')), colourOf(byName('fea-heat-heads')), colourOf(byName('fea-convection-strokes'))])
      .toEqual(['71717a', '18181b', '71717a']);
    expect((byName('fea-heat-heads-ghost').material as THREE.MeshBasicMaterial).opacity).toBe(GHOST_OPACITY);
    markers.style({ ...STYLE, visible: { loads: true, fixtures: false } });
    expect([byName('fea-temperature-dots').visible, byName('fea-heat-heads').visible, byName('fea-convection-strokes-ghost').visible]).toEqual([false, true, false]);
    markers.style({ ...STYLE, chosen: (site: any) => site.kind === 'heat' });
    expect(colourOf(byName('fea-heat-shafts'))).toBe('ff40f2');
    // Static draws none of them, whatever the study echoes.
    expect(createFeaMarkers(THREE, cube(HEATED)).kinds).toEqual([]);
    const disposed: string[] = [];
    markers.object3D.traverse((object: any) => object.material?.addEventListener('dispose', () => disposed.push(object.name)));
    markers.dispose();
    expect(disposed.length).toBeGreaterThanOrEqual(10);
  });

  it('stands a dot on a fixed temperature, heat\'s arrow into its face and the air\'s strokes off theirs, each labelled', () => {
    const result = cube(HEATED, [0, 0, 0], { analysis: { type: 'thermal' } });
    const markers = createFeaMarkers(THREE, result);
    markers.update(positionsOf(result));
    const poses = markers.poses();
    for (const dot of poses.filter((pose: any) => pose.kind === 'temperature')) expect(dot.tip[1]).toBeCloseTo(-0.5, 6);
    for (const heat of poses.filter((pose: any) => pose.kind === 'heat')) { expect(heat.tip[1]).toBeCloseTo(0.5, 6); near(heat.direction, [0, -1, 0]); }
    for (const air of poses.filter((pose: any) => pose.kind === 'convection')) expect(Math.abs(air.direction[0])).toBeCloseTo(1, 6);
    expect(markers.labels().map((label: any) => [label.kind, label.text])).toEqual([['temperature', '25 °C'], ['heat', '15 W'], ['convection', 'air 25 °C']]);
    // Only the bucket shown is labelled.
    expect(markers.labels(1, { loads: true, fixtures: false }).map((label: any) => label.text)).toEqual(['15 W']);
    markers.dispose();
  });

  it('puts a body load through the model\'s middle, labelled with its g and way, at the load shown', () => {
    const result = cube({ fixtures: [], loads: [{ type: 'gravity', vector_g: [0, 0, -1] }] });
    const markers = createFeaMarkers(THREE, result);
    markers.update(positionsOf(result));
    const [pose] = markers.poses();
    expect(pose).toMatchObject({ kind: 'body_load', ref: null });
    near(pose.direction, [0, -1, 0]);
    near(pose.tip, [0, -ARROW_LENGTH * Math.sqrt(3) / 2, 0]);
    expect(markers.labels(2).map((label: any) => label.text)).toEqual(['2 g down']);
    markers.dispose();
  });

  it('shakes the fixtures with double arrows, drops along the fall, and opens a flow at its box\'s sides', () => {
    const shaken = cube({ fixtures: [{ type: 'fixed', faces: ['#o1.f4'] }], loads: [], excitation: { type: 'base', direction: [0, 0, 1], amplitude_g: 1 } },
      [0, 0, 0], { analysis: { type: 'harmonic' } });
    const shaker = createFeaMarkers(THREE, shaken);
    shaker.update(positionsOf(shaken));
    const doubles = shaker.poses().filter((pose: any) => pose.kind === 'base_excitation');
    expect(doubles).toHaveLength(1);
    // CAD Z is the mesh's Y: the double arrow runs along it, off the fixed face.
    near(doubles[0].direction, [0, 1, 0]);
    expect(shaker.object3D.getObjectByName('fea-base-excitation-tails')).toBeTruthy();
    expect(shaker.labels().map((label: any) => label.text)).toEqual(['shaken 1 g along Z']);
    shaker.dispose();

    const dropped = cube({ fixtures: [], loads: [], drop: { height_mm: 1000, onto: ['#o1.f4'], stop_mm: 2 } }, [0, 0, 0], { analysis: { type: 'drop' } });
    const [fall] = markerPoses(dropped, markerSites(dropped), positionsOf(dropped));
    // Along the landing face's outward normal, standing on it by its tail.
    near(fall.direction, [0, -1, 0]);
    expect(fall.tail[1]).toBeCloseTo(-0.5, 6);

    const flow = cube({ fixtures: [], loads: [], flow: { kind: 'internal', inlets: [{ opening: 'x_min', velocity_m_s: 0.5 }], outlets: [{ opening: 'y_max', pressure_Pa: 0 }] } },
      [0, 0, 0], { analysis: { type: 'cfd' } });
    const openings = createFeaMarkers(THREE, flow);
    openings.update(positionsOf(flow));
    const [inlet, outlet] = openings.poses();
    // In through the low X side, its tip on it; out through CAD's high Y, which is the mesh's low Z.
    near(inlet.direction, [1, 0, 0]);
    near(inlet.tip, [-0.5, 0, 0]);
    near(outlet.direction, [0, 0, -1]);
    near(outlet.tail, [0, 0, -0.5]);
    expect(openings.labels().map((label: any) => label.text)).toEqual(['0.5 m/s', '0 Pa']);
    openings.dispose();
  });

  it('lays a see-through rigid floor under a drop, through the lowest point along the fall', () => {
    const result = cube({ fixtures: [], loads: [], drop: { height_mm: 1000, onto: [], direction: [0, 0, -1], floor: 'rigid' } }, [0, 0, 0], { analysis: { type: 'impact' } });
    const markers = createFeaMarkers(THREE, result);
    markers.update(positionsOf(result));
    const plane = markers.object3D.getObjectByName('fea-rigid-plane-0') as THREE.Mesh;
    expect(plane.position.y).toBeCloseTo(-0.5, 6);
    const material = plane.material as THREE.MeshBasicMaterial;
    expect([material.transparent, material.opacity < 0.5, material.depthWrite]).toEqual([true, true, false]);
    markers.style(STYLE);
    expect(material.color.getHexString()).toBe('71717a');
    markers.dispose();
  });

  it('says in Display what it draws, and words a drop and a shake plainly', () => {
    expect(markerGateText(['fixture', 'load'])).toBe('Arrows where the study loads the part, cones where it holds it.');
    expect(markerGateText(['temperature', 'heat', 'convection'])).toBe('Dots where its temperature is fixed, wavy arrows where heat goes in, strokes where air cools it.');
    expect(markerGateText([])).toBe('');
    expect([dropWords(1000), dropWords(500), dropWords(1500)]).toEqual(['1 m drop', '500 mm drop', '1.5 m drop']);
    expect([shakeWords({ kind: 'psd', direction: [0, 0, 1] }), shakeWords({ kind: 'srs', direction: [1, 0, 0] }),
      shakeWords({ kind: 'base', direction: [0, 0, 1], amplitudeG: 2 }, 1.5)]).toEqual(['shaken at random along Z', 'a shock along X', 'shaken 3 g along Z']);
  });
});
