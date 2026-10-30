import * as THREE from 'three';
import { BufferAttribute, BufferGeometry, Group, Mesh } from 'three';
import { describe, expect, it } from 'vitest';
import { applyDeformation, readFeaResult } from './feaResult.js';
import { feaDrawnBounds } from './feaBounds.js';

// A cantilever 40 mm long (glTF metres) whose tip moves 0.2 mm down under its load, the file drawing it ×10.
function cantilever() {
  const geometry = new BufferGeometry();
  const tip = [0, 0, 0, 0, -0.0002, 0, 0, -0.0002, 0, 0, 0, 0];
  const rest = [0, 0, 0, 0.04, 0, 0, 0.04, 0.004, 0, 0, 0.004, 0];
  geometry.setAttribute('position', new BufferAttribute(new Float32Array(rest.map((value, i) => value + 10 * tip[i])), 3));
  geometry.setIndex([0, 1, 2, 0, 2, 3]);
  geometry.setAttribute('color', new BufferAttribute(new Uint8Array(16), 4, true));
  geometry.setAttribute('_von_mises', new BufferAttribute(new Float32Array([1, 0, 0, 1]), 1));
  geometry.setAttribute('_displacement', new BufferAttribute(new Float32Array(tip), 3));
  geometry.setAttribute('_face', new BufferAttribute(new Float32Array(4), 1));
  const mesh = new Mesh(geometry);
  Object.assign(mesh.userData, {
    generator: 'cadgen fea', name: 'cantilever', document: 'cantilever.step', occurrence: 'cantilever', deformation_scale: 10, safety_factor: 276, faces: [],
    ramp: [[0, [0, 0, 1]], [1, [1, 0, 0]]],
    checks: [{ kind: 'stress', label: 'Strength', value: 1, limit: 276, unit: 'MPa', ratio: 0.003623, close_at: 0.5, margin: 2, status: 'passes', where: { ref: null, at: [0, 0, 0] } }],
    study: { material: { name: '6061-T6', yield_MPa: 276 }, fixtures: [], loads: [], mesh: { size_mm: 1, refined_from_mm: null }, margin: 2 },
    fields: [{ attribute: '_VON_MISES', name: 'von Mises stress', units: 'MPa', min: 0, max: 1, attribute_scale: 1 },
      { attribute: '_DISPLACEMENT', name: 'displacement', units: 'mm', min: 0, max: 0.2, attribute_scale: 1000 }],
  });
  const root = new Group();
  root.add(mesh);
  const fea = readFeaResult(root)!;
  const box = new THREE.Box3().setFromObject(root, true);
  return { fea, mesh, scene: { object3D: root, bounds: { min: box.min.toArray(), max: box.max.toArray() } } };
}

describe('feaDrawnBounds', () => {
  it('holds the part at rest, as the file holds it and as drawn at the deformation and load it opens on', () => {
    const { fea, mesh, scene } = cantilever();
    // Opened at ×20 and twice the load: the tip 8 mm down, past the file's 2 mm.
    const grown = feaDrawnBounds(THREE, scene, fea, { scale: 20, load: 2 })!;
    expect(scene.bounds.min[1]).toBeCloseTo(-0.002, 6);
    expect(grown.min[1]).toBeCloseTo(-0.008, 6);
    // The part at rest stands as high as the file's box, and the ramp's every moment is between rest and the load shown.
    expect(grown.max[1]).toBeCloseTo(0.004, 6);
    applyDeformation(mesh, 40, 10);
    mesh.geometry.computeBoundingBox();
    expect(mesh.geometry.boundingBox!.min.y).toBeGreaterThanOrEqual(grown.min[1] - 1e-9);
  });

  it('is null with no bounds to grow', () => {
    const { fea } = cantilever();
    expect(feaDrawnBounds(THREE, { object3D: new Group() }, fea)).toBeNull();
  });
});
