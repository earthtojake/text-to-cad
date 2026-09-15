import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";

import {
  buildCadSurfaceInstanceSets,
  dissolveCadSurfaceInstanceSets,
  reconcileCadSurfaceInstanceSets,
  surfaceInstancingStateEligible,
  syncCadSurfaceInstanceRecord,
  syncCadSurfaceInstanceTransform,
} from "./cadSurfaceInstances.js";

function record(id, geometry, x, { mirrored = false } = {}) {
  const material = new THREE.MeshStandardMaterial({ color: id === "a" ? "#ff0000" : "#00ff00" });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.matrixAutoUpdate = false;
  mesh.matrix.makeScale(mirrored ? -1 : 1, 1, 1).setPosition(x, 0, 0);
  mesh.userData = { partId: id, faceIds: new Uint32Array([x]) };
  return { partId: id, mesh, geometry, material, baseColor: material.color.clone(), baseEmissiveIntensity: 0 };
}

// Exact pre-memo recipe: regression checks pin key bytes, including JSON's
// undefined, non-finite-number and negative-zero normalization.
function uncachedPassKey(material) {
  const color = material?.emissive;
  return JSON.stringify({
    type: material?.type || "", vertexColors: material?.vertexColors === true,
    roughness: Number(material?.roughness), metalness: Number(material?.metalness),
    clearcoat: Number(material?.clearcoat), clearcoatRoughness: Number(material?.clearcoatRoughness),
    emissiveIntensity: Number(material?.emissiveIntensity) || 0,
    emissionEnabled: Number(material?.emissiveIntensity) > 0 && !!color && (color.r !== 0 || color.g !== 0 || color.b !== 0),
    envMapIntensity: Number(material?.envMapIntensity) || 0, side: material?.side,
    depthTest: material?.depthTest !== false, depthWrite: material?.depthWrite !== false,
    polygonOffset: material?.polygonOffset === true,
    polygonOffsetFactor: Number(material?.polygonOffsetFactor) || 0,
    polygonOffsetUnits: Number(material?.polygonOffsetUnits) || 0,
  });
}

function uncachedSyncKey(material) {
  return JSON.stringify({
    pass: uncachedPassKey(material), opacity: Number(material?.opacity), alphaTest: Number(material?.alphaTest),
    blending: material?.blending, toneMapped: material?.toneMapped !== false,
    clipIntersection: material?.clipIntersection === true, clipShadows: material?.clipShadows === true,
    clippingPlanes: (material?.clippingPlanes || []).map((plane) => [
      Number(plane?.normal?.x) || 0, Number(plane?.normal?.y) || 0,
      Number(plane?.normal?.z) || 0, Number(plane?.constant) || 0,
    ]),
  });
}

function keyFixture() {
  const geometry = new THREE.BoxGeometry(1, 1, 1);
  const group = new THREE.Group();
  const records = [record("a", geometry, 0), record("b", geometry, 1)];
  const sets = buildCadSurfaceInstanceSets(THREE, records, group);
  return { geometry, group, records, sets, set: [...sets][0], dispose() {
    dissolveCadSurfaceInstanceSets(sets, group);
    geometry.dispose();
    records.forEach((item) => item.material.dispose());
  } };
}

function viewFrustum() {
  const camera = new THREE.OrthographicCamera(-2, 2, 2, -2, 0.1, 100);
  camera.position.set(0, 0, 10);
  camera.updateMatrixWorld(true);
  return new THREE.Frustum().setFromProjectionMatrix(
    new THREE.Matrix4().multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse)
  );
}

test("surface instance bounds cull offscreen groups and follow in-place occurrence moves", () => {
  const fixture = keyFixture();
  const { records, set, group } = fixture;
  const frustum = viewFrustum();
  const inView = () => { group.updateMatrixWorld(true); return frustum.intersectsObject(set.object); };
  try {
    assert.equal(set.object.frustumCulled, true);
    assert.equal(inView(), true);
    for (const item of records) {
      item.mesh.matrix.elements[12] += 100;
      syncCadSurfaceInstanceTransform(item);
    }
    assert.equal(inView(), false, "offscreen instance group can skip its draw");
    const settledBounds = set.object.boundingSphere;
    records.forEach(syncCadSurfaceInstanceTransform);
    assert.equal(set.object.boundingSphere, settledBounds, "unchanged transforms retain the computed bound");
    records[0].mesh.matrix.elements[12] = 0;
    syncCadSurfaceInstanceTransform(records[0]);
    assert.equal(inView(), true, "moving an occurrence into view invalidates the previous bound");
    records[0].mesh.matrix.elements[12] = 100;
    syncCadSurfaceInstanceTransform(records[0]);
    assert.equal(inView(), false);
    group.position.x = -100;
    assert.equal(inView(), true, "the parent placement remains part of Three's frustum test");
    assert.deepEqual(set.object.userData.partIds, ["a", "b"]);
    assert.deepEqual(records.map((item) => item.surfaceInstance.slot), [0, 1]);
  } finally { fixture.dispose(); }
});

test("surface bounds enclose affine-transformed geometry and boundary-crossing occurrences", () => {
  const fixture = keyFixture();
  const { records, set, group } = fixture;
  try {
    records[0].mesh.matrix.set(1, 3, 0, 3.2, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1);
    records[1].mesh.matrix.makeTranslation(10, 0, 0);
    records.forEach(syncCadSurfaceInstanceTransform);
    group.updateMatrixWorld(true);
    assert.equal(viewFrustum().intersectsObject(set.object), true, "a center outside the viewport can still have visible geometry");
    const point = new THREE.Vector3();
    const matrix = new THREE.Matrix4();
    const positions = fixture.geometry.attributes.position;
    for (let slot = 0; slot < records.length; slot += 1) {
      set.object.getMatrixAt(slot, matrix);
      for (let i = 0; i < positions.count; i += 1) {
        point.fromBufferAttribute(positions, i).applyMatrix4(matrix);
        assert.ok(point.distanceTo(set.object.boundingSphere.center) <= set.object.boundingSphere.radius + 1e-6);
      }
    }
  } finally { fixture.dispose(); }
});

test("reactivating a surface slot refreshes bounds without changing occurrence identity", () => {
  const fixture = keyFixture();
  const { records, group, sets, set } = fixture;
  const extra = record("c", fixture.geometry, 0);
  // Three records keep the set compatible while one takes an ordinary mesh.
  dissolveCadSurfaceInstanceSets(sets, group);
  records.push(extra);
  for (const next of buildCadSurfaceInstanceSets(THREE, records, group)) sets.add(next);
  const current = [...sets][0];
  try {
    current.object.computeBoundingSphere();
    records[0].material.transparent = true;
    reconcileCadSurfaceInstanceSets(THREE, records, group, sets);
    assert.equal(current.object.boundingSphere, null);
    current.object.computeBoundingSphere();
    records[0].mesh.matrix.makeTranslation(100, 0, 0);
    records[0].material.transparent = false;
    reconcileCadSurfaceInstanceSets(THREE, records, group, sets);
    assert.equal(current.object.boundingSphere, null);
    current.object.computeBoundingSphere();
    assert.ok(current.object.boundingSphere.containsPoint(new THREE.Vector3(100, 0, 0)));
    assert.equal(records[0].surfaceInstance.set, current);
    assert.equal(records[0].surfaceInstance.slot, 0);
    assert.equal(set.disposed, true);
  } finally { fixture.dispose(); }
});

test("surface culling stays conservative under a sheared external parent", () => {
  const fixture = keyFixture();
  const { records, set, group } = fixture;
  try {
    records[1].mesh.matrix.identity();
    syncCadSurfaceInstanceTransform(records[1]);
    group.matrixAutoUpdate = false;
    group.matrix.set(1, 1, 1, 3.3, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1);
    group.updateMatrixWorld(true);
    const visibleCorner = new THREE.Vector3(-0.5, -0.5, -0.5).applyMatrix4(group.matrixWorld);
    const frustum = viewFrustum();
    assert.equal(frustum.containsPoint(visibleCorner), true);
    assert.equal(frustum.intersectsObject(set.object), true);
    const worldBound = set.object.boundingSphere.clone().applyMatrix4(set.object.matrixWorld);
    const positions = fixture.geometry.attributes.position;
    const point = new THREE.Vector3();
    for (let i = 0; i < positions.count; i += 1) {
      point.fromBufferAttribute(positions, i).applyMatrix4(group.matrixWorld);
      assert.ok(point.distanceTo(worldBound.center) <= worldBound.radius + 1e-6);
    }
  } finally { fixture.dispose(); }
});

test("material keys retain exact bytes while observing every direct scalar mutation", () => {
  const fixture = keyFixture();
  const item = fixture.records[0];
  const material = item.material;
  const mutations = [
    ["type", "AlternateMaterial"], ["vertexColors", true], ["roughness", 0.37], ["metalness", 0.42],
    ["clearcoat", 0.21], ["clearcoatRoughness", 0.31], ["emissiveIntensity", 0.2],
    ["envMapIntensity", 1.3], ["side", THREE.DoubleSide], ["depthTest", false], ["depthWrite", false],
    ["polygonOffset", true], ["polygonOffsetFactor", -3], ["polygonOffsetUnits", 2],
    ["opacity", 0.8], ["alphaTest", 0.25], ["blending", THREE.AdditiveBlending], ["toneMapped", false],
    ["clipIntersection", true], ["clipShadows", true], ["roughness", NaN], ["metalness", Infinity],
    ["clearcoat", -Infinity], ["clearcoatRoughness", -0], ["alphaTest", NaN], ["side", undefined],
    ["opacity", "0.9"], ["emissiveIntensity", -0], ["envMapIntensity", NaN],
  ];
  try {
    assert.equal(fixture.set.materialKey, uncachedSyncKey(material));
    for (const [field, value] of mutations) {
      material[field] = value;
      syncCadSurfaceInstanceRecord(item);
      assert.equal(fixture.set.materialKey, uncachedSyncKey(material), field);
      syncCadSurfaceInstanceRecord(item);
      assert.equal(fixture.set.materialKey, uncachedSyncKey(material), `${field} repeated`);
    }
    material.emissiveIntensity = 1;
    material.emissive.setRGB(0, 0, 0);
    syncCadSurfaceInstanceRecord(item);
    const black = fixture.set.materialKey;
    material.emissive.g = 0.1;
    syncCadSurfaceInstanceRecord(item);
    assert.notEqual(fixture.set.materialKey, black, "in-place emission enables the pass");
    assert.equal(fixture.set.materialKey, uncachedSyncKey(material));
  } finally { fixture.dispose(); }
});

test("clipping recipes detect every in-place scalar, replacement and length change", () => {
  const fixture = keyFixture();
  const item = fixture.records[0];
  const a = new THREE.Plane(new THREE.Vector3(1, 2, 3), 4);
  const b = new THREE.Plane(new THREE.Vector3(5, 6, 7), 8);
  const changes = [
    () => { item.material.clippingPlanes = [a, b]; },
    () => { a.normal.x = 2; }, () => { a.normal.y = 3; }, () => { a.normal.z = 4; },
    () => { a.constant = 5; }, () => { b.constant = 9; },
    () => { item.material.clippingPlanes = [a.clone(), b.clone()]; },
    () => { item.material.clippingPlanes[1].normal.x = NaN; },
    () => { item.material.clippingPlanes[1].constant = -0; },
    () => { item.material.clippingPlanes.pop(); },
    () => { item.material.clippingPlanes = []; }, () => { item.material.clippingPlanes = null; },
  ];
  try {
    for (const change of changes) {
      change();
      syncCadSurfaceInstanceRecord(item);
      assert.equal(fixture.set.materialKey, uncachedSyncKey(item.material));
      syncCadSurfaceInstanceRecord(item);
      assert.equal(fixture.set.materialKey, uncachedSyncKey(item.material));
    }
  } finally { fixture.dispose(); }
});

test("unchanged reconciliation creates no material JSON and observes current render order", () => {
  const fixture = keyFixture();
  const original = JSON.stringify;
  let calls = 0;
  try {
    reconcileCadSurfaceInstanceSets(THREE, fixture.records, fixture.group, fixture.sets);
    JSON.stringify = function (...args) { calls += 1; return original.apply(this, args); };
    for (let i = 0; i < 20; i += 1) {
      reconcileCadSurfaceInstanceSets(THREE, fixture.records, fixture.group, fixture.sets);
      fixture.records.forEach(syncCadSurfaceInstanceRecord);
    }
    assert.equal(calls, 0);
    for (const item of fixture.records) item.mesh.renderOrder = 19;
    reconcileCadSurfaceInstanceSets(THREE, fixture.records, fixture.group, fixture.sets);
    assert.equal(fixture.set.object.renderOrder, 19);
    assert.equal(fixture.set.groupPassKey, `${uncachedPassKey(fixture.records[0].material)}#order=19`);
  } finally { JSON.stringify = original; fixture.dispose(); }
});

test("equal clipping values reuse keys and numeric conversions still execute on hits", () => {
  const fixture = keyFixture();
  const item = fixture.records[0];
  const original = JSON.stringify;
  let calls = 0;
  let conversions = 0;
  let roughness = 0.4;
  try {
    item.material.clippingPlanes = [new THREE.Plane(new THREE.Vector3(1, 2, 3), 4)];
    item.material.roughness = { valueOf() { conversions += 1; return roughness; } };
    syncCadSurfaceInstanceRecord(item);
    JSON.stringify = function (...args) { calls += 1; return original.apply(this, args); };
    const initialConversions = conversions;
    for (let i = 0; i < 20; i += 1) syncCadSurfaceInstanceRecord(item);
    assert.equal(conversions, initialConversions + 20);
    assert.equal(calls, 0, "unchanged nonempty plane arrays need no JSON");
    item.material.clippingPlanes = item.material.clippingPlanes.map((plane) => plane.clone());
    syncCadSurfaceInstanceRecord(item);
    assert.equal(calls, 0, "equal values in replacement planes still hit");
    roughness = 0.7;
    syncCadSurfaceInstanceRecord(item);
    assert.ok(calls > 0, "a changed conversion result cannot hide behind object identity");
    assert.equal(fixture.set.materialKey, uncachedSyncKey(item.material));
  } finally { JSON.stringify = original; fixture.dispose(); }
});

test("custom key values and clipping mappers retain uncached behaviour", () => {
  const fixture = keyFixture();
  const item = fixture.records[0];
  let side = 1;
  let mapperValue = 0;
  let mapped = 0;
  const planes = [new THREE.Plane(new THREE.Vector3(1, 0, 0), 0)];
  planes.map = function () { mapped += 1; return [[mapperValue]]; };
  try {
    item.material.side = { toJSON() { return side; } };
    item.material.clippingPlanes = planes;
    syncCadSurfaceInstanceRecord(item);
    assert.equal(fixture.set.materialKey, uncachedSyncKey(item.material));
    side = 2;
    mapperValue = 4;
    syncCadSurfaceInstanceRecord(item);
    assert.equal(fixture.set.materialKey, uncachedSyncKey(item.material));
    const calls = mapped;
    syncCadSurfaceInstanceRecord(item);
    assert.ok(mapped > calls, "an unchanged custom mapper still runs");
  } finally { fixture.dispose(); }
});

test("a clipping getter removing a later entry preserves native map holes", () => {
  const fixture = keyFixture();
  const item = fixture.records[0];
  const mutatingPlanes = () => {
    const planes = [new THREE.Plane(new THREE.Vector3(1, 2, 3), 4), new THREE.Plane()];
    const normal = planes[0].normal;
    Object.defineProperty(planes[0], "normal", { get() { delete planes[1]; return normal; } });
    return planes;
  };
  try {
    // Only exercise recipe construction: three's Material.copy deliberately
    // requires real planes at every slot, independently of JSON's hole rules.
    fixture.set.object.material.copy = function () { return this; };
    item.material.clippingPlanes = mutatingPlanes();
    const expected = uncachedSyncKey(item.material);
    item.material.clippingPlanes = mutatingPlanes();
    syncCadSurfaceInstanceRecord(item);
    assert.equal(fixture.set.materialKey, expected);
    assert.equal(JSON.parse(expected).clippingPlanes[1], null);
    syncCadSurfaceInstanceRecord(item);
    assert.equal(fixture.set.materialKey, uncachedSyncKey(item.material), "already-sparse arrays keep the same bytes");
  } finally { fixture.dispose(); }
});

test("compatible surfaces share one draw and keep per-instance identity and transforms", () => {
  const geometry = new THREE.BoxGeometry(1, 1, 1);
  const group = new THREE.Group();
  const records = [record("a", geometry, 2), record("b", geometry, 7)];
  records.forEach((item) => group.add(item.mesh));
  const sets = buildCadSurfaceInstanceSets(THREE, records, group);
  const [set] = sets;
  let objectDisposes = 0;
  set.object.addEventListener("dispose", () => { objectDisposes += 1; });
  assert.equal(group.children.length, 3, "two hidden pick proxies plus one rendered instance draw");
  assert.equal(set.object.isInstancedMesh, true);
  assert.equal(set.matrixValues, set.object.instanceMatrix.array, "dirty checks reuse the upload array");
  assert.equal(set.colorValues, set.object.instanceColor.array, "color dirty checks need no CPU mirror");
  assert.deepEqual(set.object.userData.partIds, ["a", "b"]);
  assert.equal(set.object.userData.faceIdsByInstance[1][0], 7);
  const matrix = new THREE.Matrix4();
  set.object.getMatrixAt(1, matrix);
  assert.equal(matrix.elements[12], 7);
  records[1].mesh.matrix.makeTranslation(11, 0, 0);
  syncCadSurfaceInstanceRecord(records[1]);
  set.object.getMatrixAt(1, matrix);
  assert.equal(matrix.elements[12], 11);
  const matrixVersion = set.object.instanceMatrix.version;
  const colorVersion = set.object.instanceColor.version;
  const materialVersion = set.object.material.version;
  const originalCopy = set.object.material.copy;
  let materialCopies = 0;
  set.object.material.copy = function (...args) {
    materialCopies += 1;
    return originalCopy.apply(this, args);
  };
  syncCadSurfaceInstanceRecord(records[1]);
  syncCadSurfaceInstanceRecord(records[0]);
  assert.equal(set.object.instanceMatrix.version, matrixVersion, "stable transforms schedule no upload");
  assert.equal(set.object.instanceColor.version, colorVersion, "stable colours schedule no upload");
  assert.equal(set.object.material.version, materialVersion, "stable pass state avoids material copy/configure");
  assert.equal(materialCopies, 0);
  dissolveCadSurfaceInstanceSets(sets, group);
  assert.equal(group.children.length, 2);
  assert.equal(objectDisposes, 1, "InstancedMesh releases its private instance GPU attributes");
  dissolveCadSurfaceInstanceSets(sets, group);
  assert.equal(objectDisposes, 1, "dissolve is idempotent");
  geometry.dispose();
  records.forEach((item) => item.material.dispose());
});

test("shared emission follows diffuse colour while distinct emission keeps exact ordinary shading", () => {
  const geometry = new THREE.BoxGeometry(1, 1, 1);
  const group = new THREE.Group();
  const records = [record("a", geometry, 0), record("b", geometry, 2), record("c", geometry, 4), record("d", geometry, 6)];
  records.forEach((item) => group.add(item.mesh));
  let sets = buildCadSurfaceInstanceSets(THREE, records, group);
  assert.equal([...sets][0].object.material.emissive.getHex(), 0, "black emission remains black even with a nonzero intensity");
  for (const item of records) {
    item.material.emissive.copy(item.material.color);
    item.material.emissiveIntensity = 0.2;
  }
  sets = reconcileCadSurfaceInstanceSets(THREE, records, group, sets);
  const [set] = sets;
  assert.equal(set.object.material.emissive.getHex(), 0xffffff, "instance colour supplies the matched emission channel");
  records[0].material.emissive.set("#0000ff");
  records[1].material.vertexColors = true;
  sets = reconcileCadSurfaceInstanceSets(THREE, records, group, sets);
  assert.equal(sets.has(set), true, "the unaffected two still share the original slots");
  assert.equal(records[0].material.visible, true);
  assert.equal(records[0].material.emissive.getHexString(), "0000ff");
  assert.equal(records[1].material.visible, true, "uniform emission must not acquire a vertex-colour multiplier");
  assert.deepEqual(Array.from(set.activeSlots), [0, 0, 1, 1]);
  records[0].material.emissive.copy(records[0].material.color);
  records[1].material.vertexColors = false;
  reconcileCadSurfaceInstanceSets(THREE, records, group, sets);
  assert.deepEqual(Array.from(set.activeSlots), [1, 1, 1, 1]);
  dissolveCadSurfaceInstanceSets(sets, group);
  geometry.dispose();
  records.forEach((item) => item.material.dispose());
});

test("mirrored placements and incompatible mutable states stay on ordinary meshes", () => {
  const geometry = new THREE.BoxGeometry(1, 1, 1);
  const group = new THREE.Group();
  const records = [
    record("a", geometry, 0),
    record("b", geometry, 1),
    record("mirror", geometry, 2, { mirrored: true }),
  ];
  records.forEach((item) => group.add(item.mesh));
  const sets = buildCadSurfaceInstanceSets(THREE, records, group);
  assert.equal(sets.size, 1);
  assert.ok(records[0].surfaceInstance && records[1].surfaceInstance);
  assert.equal(records[2].surfaceInstance, undefined, "negative determinant keeps Three.js mirrored-normal handling");
  dissolveCadSurfaceInstanceSets(sets, group);
  assert.equal(surfaceInstancingStateEligible({}), true);
  assert.equal(surfaceInstancingStateEligible({ selection: { selectedPartIds: ["a"] } }), true);
  assert.equal(surfaceInstancingStateEligible({ stepParameters: {} }), true, "mutable effects are handled per record");
  geometry.dispose();
  records.forEach((item) => item.material.dispose());
});

test("opaque generated-surface vertex colours remain shared and instanced", () => {
  const geometry = new THREE.BoxGeometry(1, 1, 1);
  geometry.setAttribute("color", new THREE.Float32BufferAttribute(
    Array.from({ length: geometry.getAttribute("position").count * 3 }, (_, index) => (
      index % 3 === 0 ? 0.25 : index % 3 === 1 ? 0.5 : 0.75
    )),
    3
  ));
  const group = new THREE.Group();
  const records = [record("a", geometry, 0), record("b", geometry, 2)];
  for (const item of records) {
    item.hasVertexColors = true;
    item.material.vertexColors = true;
    item.material.color.set(0xffffff);
    group.add(item.mesh);
  }
  const sets = buildCadSurfaceInstanceSets(THREE, records, group);
  const [set] = sets;
  assert.equal(sets.size, 1, "shared vertex colours do not block the ordinary opaque path");
  assert.equal(set.object.material.vertexColors, true);
  assert.equal(set.object.renderOrder, records[0].mesh.renderOrder);
  assert.deepEqual(set.object.instanceColor.array.slice(0, 3), new Float32Array([1, 1, 1]));

  records[1].material.transparent = true;
  records[1].material.opacity = 0.5;
  const reconciled = buildCadSurfaceInstanceSets(THREE, records, new THREE.Group());
  assert.equal(reconciled.size, 0, "a true alpha-blended occurrence stays an ordinary mesh");
  dissolveCadSurfaceInstanceSets(sets, group);
  geometry.dispose();
  records.forEach((item) => item.material.dispose());
});
