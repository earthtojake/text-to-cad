import { BufferAttribute, BufferGeometry, Group, Mesh } from 'three';
import { describe, expect, it } from 'vitest';
import {
  applyDeformation, deformationRange, feaRamp, fieldValues, formatValue, readFeaResult, recolorByField
} from './feaResult.js';

/** A two-triangle "result" the way GLTFLoader hands one over: lower-cased custom attributes, extras in userData. */
function resultMesh({ generator = 'cadgen fea', scale = 10 } = {}) {
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
    fields: [
      { attribute: '_VON_MISES', name: 'von Mises stress', units: 'MPa', min: 0, max: 100, attribute_scale: 1 },
      { attribute: '_DISPLACEMENT', name: 'displacement', units: 'mm', min: 0, max: 2, attribute_scale: 1000 },
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
    expect(result?.fields[1]).toMatchObject({ units: 'mm', max: 2, attributeScale: 1000 });
    expect(result?.ramp.length).toBe(5);  // no ramp in the file: the default
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
