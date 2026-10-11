import * as THREE from 'three';
import { BufferAttribute, BufferGeometry, Group, Mesh } from 'three';
import { describe, expect, it } from 'vitest';
import { applyDeformation, readFeaResult } from './feaResult.js';
import { feaDrawnBounds } from './feaBounds.js';

// A rubber strap 74 mm long (glTF metres) whose file carries its first load step (stretched 2.7 mm) and whose last
// step, where Study opens, stretches it 37 mm: the case that drew as a sliced wedge in an oblique view.
function strap(series = true) {
  const geometry = new BufferGeometry();
  const rest = [-0.037, 0, -0.009, 0.037, 0, -0.009, 0.037, 0.003, 0.009, -0.037, 0.003, 0.009];
  const first = [0, 0, 0, 0.0027, 0, 0, 0.0027, 0, 0, 0, 0, 0];
  const last = [0, 0, 0, 0.037, 0, 0, 0.037, 0, 0, 0, 0, 0];
  geometry.setAttribute('position', new BufferAttribute(new Float32Array(rest.map((value, i) => value + first[i])), 3));
  geometry.setIndex([0, 1, 2, 0, 2, 3]);
  geometry.setAttribute('color', new BufferAttribute(new Uint8Array(16), 4, true));
  geometry.setAttribute('_von_mises', new BufferAttribute(new Float32Array([0, 1, 1, 0]), 1));
  geometry.setAttribute('_displacement', new BufferAttribute(new Float32Array(first), 3));
  geometry.setAttribute('_displacement_f1', new BufferAttribute(new Float32Array(last), 3));
  const mesh = new Mesh(geometry);
  Object.assign(mesh.userData, {
    generator: 'cadgen fea', name: 'strap nonlinear', deformation_scale: 1,
    analysis: { type: 'nonlinear', tier: 3, word: 'Stretch', estimate: false, limits: [], noun: 'this load', reference_C: null, warnings: [] },
    fields: [{ attribute: '_VON_MISES', name: 'von Mises stress', units: 'MPa', min: 0, max: 1, attribute_scale: 1, field: 'von_mises', per_frame: true },
      { attribute: '_DISPLACEMENT', name: 'displacement', units: 'mm', min: 0, max: 37, attribute_scale: 1000, field: 'displacement', per_frame: true }],
    ...(series ? { series: { kind: 'time', unit: '%', default: 1, frames: [
      { value: 10, label: '10 % load', attributes: { von_mises: '_VON_MISES', displacement: '_DISPLACEMENT' } },
      { value: 100, label: '100 % load', attributes: { von_mises: '_VON_MISES', displacement: '_DISPLACEMENT_F1' } }] } } : {}),
  });
  const root = new Group();
  root.add(mesh);
  const fea = readFeaResult(root)!;
  const box = new THREE.Box3().setFromObject(root, true);
  return { fea, mesh, scene: { object3D: root, bounds: { min: box.min.toArray(), max: box.max.toArray() } } };
}

describe('feaDrawnBounds', () => {
  it('holds every frame of the series, so the frame Study opens on is inside the box the camera planes are fitted to', () => {
    const { fea, mesh, scene } = strap();
    const grown = feaDrawnBounds(THREE, scene, fea)!;
    // The file's box ends at the first step's 39.7 mm; the last step reaches 74 mm.
    expect(scene.bounds.max[0]).toBeCloseTo(0.0397, 6);
    expect(grown.max[0]).toBeCloseTo(0.074, 6);
    expect(grown.min).toEqual(scene.bounds.min);
    // Drawn at the last frame (what the paint pass does), every position is inside the grown box.
    applyDeformation(mesh, 1, 1, '_displacement_f1');
    mesh.geometry.computeBoundingBox();
    const drawn = mesh.geometry.boundingBox!;
    expect(drawn.max.x).toBeGreaterThan(scene.bounds.max[0]);
    expect(drawn.max.x).toBeLessThanOrEqual(grown.max[0] + 1e-9);
  });

  it('leaves a result with no series as the file holds it', () => {
    const { fea, scene } = strap(false);
    expect(feaDrawnBounds(THREE, scene, fea)).toBeNull();
    expect(feaDrawnBounds(THREE, { object3D: new Group() }, fea)).toBeNull();
  });
});
