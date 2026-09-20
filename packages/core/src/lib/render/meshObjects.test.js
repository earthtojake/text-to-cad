import assert from "node:assert/strict";
import test from "node:test";

import * as THREE from "three";
import { toCreasedNormals } from "three/examples/jsm/utils/BufferGeometryUtils.js";

import { buildPartFillIndexMap } from "../../common/cadScene.js";
import { CREASED_NORMAL_MAX_TRIANGLES } from "./meshNormals.js";
import { buildMeshObjects } from "./meshObjects.js";
import { buildMeshDataFromStlGeometry } from "./stlMeshData.js";
import { buildMeshDataFromThreeMfGroup } from "./threeMfMeshData.js";

const soup = geometry => geometry.toNonIndexed();
const normalsAt = (geometry, x, y, z) => {
  const position = geometry.getAttribute("position");
  const normal = geometry.getAttribute("normal");
  const found = new Set();
  for (let index = 0; index < position.count; index += 1) {
    if (position.getX(index) === x && position.getY(index) === y && position.getZ(index) === z) {
      found.add([normal.getX(index), normal.getY(index), normal.getZ(index)].map(value => Math.round(value * 1000) / 1000).join(","));
    }
  }
  return found;
};

test("an STL is one object over the decode's own arrays: creased normals, no colour, no index", () => {
  const meshData = buildMeshDataFromStlGeometry(soup(new THREE.BoxGeometry(2, 2, 2)), { toCreasedNormals });
  const objects = buildMeshObjects(THREE, meshData);
  assert.equal(objects.length, 1);
  const [{ geometry, color, paletteIndex }] = objects;
  assert.deepEqual([color, paletteIndex], [null, 0]);
  assert.equal(geometry.getAttribute("position").array.buffer, meshData.vertices.buffer, "a view, never a copy");
  assert.equal(geometry.getAttribute("normal").array.buffer, meshData.normals.buffer);
  assert.equal(geometry.getIndex(), null, "triangle soup in draw order needs no index");
  assert.equal(normalsAt(geometry, 1, 1, 1).size, 3, "a box corner keeps its three hard faces");
  assert.deepEqual([geometry.boundingBox.min.toArray(), geometry.boundingBox.max.toArray()], [[-1, -1, -1], [1, 1, 1]]);
});

test("a coarse round mesh is smoothed across its facets; a dense one takes plain vertex normals instead", () => {
  const coarse = buildMeshObjects(THREE, buildMeshDataFromStlGeometry(soup(new THREE.CylinderGeometry(1, 1, 2, 24, 1, true)), { toCreasedNormals }))[0].geometry;
  const seam = coarse.getAttribute("position");
  assert.equal(normalsAt(coarse, seam.getX(0), seam.getY(0), seam.getZ(0)).size, 1, "15 degree facets read as one round wall");

  let creased = 0;
  const counting = (geometry, angle) => { creased += 1; return toCreasedNormals(geometry, angle); };
  const segments = Math.ceil(Math.sqrt(CREASED_NORMAL_MAX_TRIANGLES / 2)) + 1;
  const dense = soup(new THREE.PlaneGeometry(1, 1, segments, segments));
  assert.ok(dense.getAttribute("position").count / 3 > CREASED_NORMAL_MAX_TRIANGLES);
  const [object] = buildMeshObjects(THREE, buildMeshDataFromStlGeometry(dense, { toCreasedNormals: counting }));
  assert.equal(creased, 0, "creasing is superlinear: above the cap it is never run");
  assert.deepEqual([...object.geometry.getAttribute("normal").array.slice(0, 3)], [0, 0, 1]);
});

function threeMfGroup(colors) {
  const group = new THREE.Group();
  colors.forEach((color, index) => {
    const material = new THREE.MeshPhongMaterial({ color: color || "#fafafb", name: color ? `material-${index}` : "default" });
    const box = new THREE.BoxGeometry(1, 1, 1);
    box.clearGroups();
    const mesh = new THREE.Mesh(box, material);
    mesh.name = `object ${index}`;
    mesh.position.set(index * 2, 0, 0);
    group.add(mesh);
  });
  return group;
}

test("a 3MF is one object per file object, placed, with the colour its material carried", () => {
  const meshData = buildMeshDataFromThreeMfGroup(THREE, threeMfGroup(["#d02020", "#2040d0"]), { toCreasedNormals });
  const objects = buildMeshObjects(THREE, meshData);
  assert.deepEqual(objects.map(object => [object.name, object.color.getHexString()]), [["object 0", "d02020"], ["object 1", "2040d0"]]);
  assert.deepEqual(objects[1].geometry.boundingBox.min.toArray(), [1.5, -0.5, -0.5], "the build transform is baked in");
  assert.equal(objects[1].geometry.getAttribute("position").array.byteOffset > 0, true, "each object is a window onto the shared arrays");
  assert.equal(objects[1].geometry.getAttribute("position").count, 36);
});

test("a file with no authored colour leaves every object to the viewer's surface colour; one colour makes the file coloured", () => {
  const plain = buildMeshObjects(THREE, buildMeshDataFromThreeMfGroup(THREE, threeMfGroup([null, null]), { toCreasedNormals }));
  assert.deepEqual(plain.map(object => object.color), [null, null]);
  const mixed = buildMeshObjects(THREE, buildMeshDataFromThreeMfGroup(THREE, threeMfGroup(["#d02020", null]), { toCreasedNormals }));
  assert.deepEqual(mixed.map(object => object.color.getHexString()), ["d02020", "b6c4ce"], "the writer's default grey stays a colour of that file");
});

test("a palette is dealt in the order the viewer has always used, which is not file order past ten objects", () => {
  const meshData = buildMeshDataFromThreeMfGroup(THREE, threeMfGroup(Array.from({ length: 12 }, () => "#808080")), { toCreasedNormals });
  const expected = buildPartFillIndexMap(meshData.parts);
  const objects = buildMeshObjects(THREE, meshData);
  assert.deepEqual(objects.map(object => object.paletteIndex), meshData.parts.map(part => expected.get(part)));
  assert.notDeepEqual(objects.map(object => object.paletteIndex), objects.map((_, index) => index));
});

test("a decode without triangles is no objects", () => {
  assert.deepEqual(buildMeshObjects(THREE, buildMeshDataFromStlGeometry(new THREE.BufferGeometry().setAttribute("position", new THREE.Float32BufferAttribute([], 3)))), []);
  assert.deepEqual(buildMeshObjects(THREE, null), []);
});
