import * as THREE from 'three';
import { BoxGeometry, BufferAttribute, Group, Mesh } from 'three';
import { describe, expect, it } from 'vitest';
import { readFeaResult } from './feaResult.js';
import { ARROW_LENGTH, GHOST_OPACITY, createFeaMarkers, loadLabel, markerPoses, markerSites } from './feaMarkers.js';

// A unit cube in the result's glTF space, its six faces in BoxGeometry's order (+X, -X, +Y, -Y, +Z,
// -Z) as `_FACE` 0..5, wound outward as the writer winds it.
const FACES = ['#o1.f1', '#o1.f2', '#o1.f3', '#o1.f4', '#o1.f5', '#o1.f6'];
function cube(study: Record<string, unknown>, displacement = [0, 0, 0]) {
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
    fields: [{ attribute: '_VON_MISES', name: 'von Mises stress', units: 'MPa', min: 0, max: 1 }],
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
    markers.dispose();
  });
});
