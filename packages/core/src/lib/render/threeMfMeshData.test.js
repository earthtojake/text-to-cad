import assert from "node:assert/strict";
import test from "node:test";

import { buildMeshDataFromThreeMfGroup } from "./threeMfMeshData.js";

class FakeVector3 {
  set(x, y, z) {
    this.x = x;
    this.y = y;
    this.z = z;
    return this;
  }

  applyMatrix4() {
    return this;
  }

  applyMatrix3() {
    return this;
  }

  normalize() {
    return this;
  }
}

class FakeMatrix3 {
  getNormalMatrix() {
    return this;
  }
}

function fakeAttribute(values) {
  return {
    itemSize: 3,
    count: values.length / 3,
    getX: (index) => values[index * 3],
    getY: (index) => values[index * 3 + 1],
    getZ: (index) => values[index * 3 + 2],
  };
}

function assertArrayAlmostEqual(actual, expected, epsilon = 1e-6) {
  assert.equal(actual.length, expected.length);
  for (let index = 0; index < actual.length; index += 1) {
    assert.ok(
      Math.abs(Number(actual[index]) - Number(expected[index])) <= epsilon,
      `index ${index}: expected ${expected[index]}, got ${actual[index]}`
    );
  }
}

test("buildMeshDataFromThreeMfGroup normalizes 3MF meshes to viewer mesh data", () => {
  const mesh = {
    isMesh: true,
    name: "fixture",
    material: null,
    matrixWorld: null,
    updateWorldMatrix() {},
    geometry: {
      getIndex: () => null,
      getAttribute: (name) => {
        if (name === "position") {
          return fakeAttribute([0, 0, 0, 1, 0, 0, 0, 1, 0]);
        }
        if (name === "normal") {
          return fakeAttribute([0, 0, 1, 0, 0, 1, 0, 0, 1]);
        }
        return null;
      },
      computeVertexNormals() {},
    },
  };
  const group = {
    updateWorldMatrix() {},
    traverse(callback) {
      callback(mesh);
    },
  };

  const meshData = buildMeshDataFromThreeMfGroup(
    { Matrix3: FakeMatrix3, Vector3: FakeVector3 },
    group
  );

  assert.deepEqual([...meshData.vertices], [0, 0, 0, 1, 0, 0, 0, 1, 0]);
  assert.deepEqual([...meshData.indices], [0, 1, 2]);
  assert.deepEqual([...meshData.normals], [0, 0, 1, 0, 0, 1, 0, 0, 1]);
  assert.deepEqual([...meshData.colors], []);
  assert.deepEqual(meshData.bounds, { min: [0, 0, 0], max: [1, 1, 0] });
  assert.equal(meshData.parts.length, 1);
  assert.equal(meshData.parts[0].name, "fixture");
  assert.equal(meshData.has_source_colors, false);
});

test("buildMeshDataFromThreeMfGroup preserves 3MF material colors", () => {
  const mesh = {
    isMesh: true,
    name: "colored fixture",
    material: {
      color: {
        r: 0.25,
        g: 0.5,
        b: 0.75,
        getHexString: () => "4080bf",
      },
    },
    matrixWorld: null,
    updateWorldMatrix() {},
    geometry: {
      getIndex: () => null,
      getAttribute: (name) => {
        if (name === "position") {
          return fakeAttribute([0, 0, 0, 1, 0, 0, 0, 1, 0]);
        }
        if (name === "normal") {
          return fakeAttribute([0, 0, 1, 0, 0, 1, 0, 0, 1]);
        }
        return null;
      },
      computeVertexNormals() {},
    },
  };
  const group = {
    updateWorldMatrix() {},
    traverse(callback) {
      callback(mesh);
    },
  };

  const meshData = buildMeshDataFromThreeMfGroup(
    { Matrix3: FakeMatrix3, Vector3: FakeVector3 },
    group
  );

  assert.deepEqual([...meshData.colors], [0.25, 0.5, 0.75, 0.25, 0.5, 0.75, 0.25, 0.5, 0.75]);
  assert.equal(meshData.has_source_colors, true);
  assert.equal(meshData.sourceColor, "#4080bf");
  assert.equal(meshData.parts[0].color, "#4080bf");
});

test("buildMeshDataFromThreeMfGroup treats generated default material as uncolored", () => {
  const mesh = {
    isMesh: true,
    name: "default fixture",
    material: {
      name: "Default",
      color: {
        r: 0.4677837961,
        g: 0.5520114015,
        b: 0.6172065624,
        getHexString: () => "b6c4ce",
      },
    },
    matrixWorld: null,
    updateWorldMatrix() {},
    geometry: {
      getIndex: () => null,
      getAttribute: (name) => {
        if (name === "position") {
          return fakeAttribute([0, 0, 0, 1, 0, 0, 0, 1, 0]);
        }
        if (name === "normal") {
          return fakeAttribute([0, 0, 1, 0, 0, 1, 0, 0, 1]);
        }
        return null;
      },
      computeVertexNormals() {},
    },
  };
  const group = {
    updateWorldMatrix() {},
    traverse(callback) {
      callback(mesh);
    },
  };

  const meshData = buildMeshDataFromThreeMfGroup(
    { Matrix3: FakeMatrix3, Vector3: FakeVector3 },
    group
  );

  assert.deepEqual([...meshData.colors], []);
  assert.equal(meshData.has_source_colors, false);
  assert.equal(meshData.sourceColor, "");
  assert.equal(meshData.parts[0].color, "");
});

test("buildMeshDataFromThreeMfGroup keeps authored colors when mixed with generated defaults", () => {
  const defaultRgb = [0.4677837961, 0.5520114015, 0.6172065624];
  const mesh = {
    isMesh: true,
    name: "mixed fixture",
    material: [
      {
        name: "Default",
        color: {
          r: defaultRgb[0],
          g: defaultRgb[1],
          b: defaultRgb[2],
          getHexString: () => "b6c4ce",
        },
      },
      {
        name: "red",
        color: {
          r: 1,
          g: 0,
          b: 0,
          getHexString: () => "ff0000",
        },
      },
    ],
    matrixWorld: null,
    updateWorldMatrix() {},
    geometry: {
      groups: [
        { start: 0, count: 3, materialIndex: 0 },
        { start: 3, count: 3, materialIndex: 1 },
      ],
      getIndex: () => null,
      getAttribute: (name) => {
        if (name === "position") {
          return fakeAttribute([
            0, 0, 0,
            1, 0, 0,
            0, 1, 0,
            1, 0, 0,
            1, 1, 0,
            0, 1, 0,
          ]);
        }
        if (name === "normal") {
          return fakeAttribute([
            0, 0, 1,
            0, 0, 1,
            0, 0, 1,
            0, 0, 1,
            0, 0, 1,
            0, 0, 1,
          ]);
        }
        return null;
      },
      computeVertexNormals() {},
    },
  };
  const group = {
    updateWorldMatrix() {},
    traverse(callback) {
      callback(mesh);
    },
  };

  const meshData = buildMeshDataFromThreeMfGroup(
    { Matrix3: FakeMatrix3, Vector3: FakeVector3 },
    group
  );

  assertArrayAlmostEqual([...meshData.colors], [
    ...defaultRgb,
    ...defaultRgb,
    ...defaultRgb,
    1, 0, 0,
    1, 0, 0,
    1, 0, 0,
  ]);
  assert.equal(meshData.has_source_colors, true);
  assert.equal(meshData.sourceColor, "#ff0000");
  assert.equal(meshData.parts[0].color, "");
  assert.equal(meshData.parts[1].color, "#ff0000");
});

test("a 3MF's objects are known by their place in its build, and its unit is the one its model declares", async () => {
  const THREE = await import("three");
  const { zipSync, strToU8 } = await import("three/examples/jsm/libs/fflate.module.js");
  const { declared3MfUnit } = await import("./threeMfMeshData.js");
  const { buildMeshScene } = await import("./meshScene.js");
  // As three's loader builds it: one child per build item; a component object one child per
  // component; an object's meshes under the object's own group.
  const object = (name) => { const group = new THREE.Group(); group.name = name; group.add(new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), new THREE.MeshStandardMaterial())); return group; };
  const root = new THREE.Group();
  const composite = new THREE.Group();
  composite.add(object("wheel"), object("wheel"));
  root.add(object("frame"), composite);
  const meshData = { ...buildMeshDataFromThreeMfGroup(THREE, root), unit: "inch" };
  // A box is six material groups: six ranges of one object, one place.
  assert.deepEqual([...new Set(meshData.parts.map(part => part.path.join(".")))], ["1", "2.1", "2.2"]);
  const scene = buildMeshScene(THREE, meshData);
  assert.deepEqual(scene.units, { unit: "in", perWorld: 1 });
  assert.deepEqual(["o1", "o2.1", "o2.2"].map(path => scene.describePart(path).name), ["frame", "wheel (o2.1)", "wheel (o2.2)"]);
  assert.deepEqual(scene.describePart("o2.2").facts.map(fact => fact.value), ["2, component 2", "12"]);
  scene.dispose();

  const model = unit => zipSync({ "3D/3dmodel.model": strToU8(`<?xml version="1.0"?>\n<model ${unit} xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"><resources/></model>`) });
  assert.deepEqual(await Promise.all([model('unit="inch"'), model("")].map(declared3MfUnit)), ["inch", "millimeter"]);
});


// A real package, built entirely in memory: object-default and per-face material
// indices, duplicate material names/colours, repeated placements and alpha.
async function metallicPackage({ namespaced = true, properties = true, noMaterial = false, malformed = false, defaultScalars = false } = {}) {
  const { zipSync, strToU8 } = await import("three/examples/jsm/libs/fflate.module.js");
  const vertices = '<vertices><vertex x="0" y="0" z="0"/><vertex x="1" y="0" z="0"/><vertex x="0" y="1" z="0"/></vertices>';
  const triangle = attributes => `<triangle v1="0" v2="1" v3="2" ${attributes}/>`;
  const model = `<model unit="millimeter" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" xmlns:m="http://schemas.microsoft.com/3dmanufacturing/material/2015/02"><resources>
    ${!noMaterial ? `${properties ? `<m:pbmetallicdisplayproperties id="20"><m:pbmetallic name="same" metallicness="1" roughness="${malformed ? '2' : '0.3'}"/><m:pbmetallic name="same" metallicness="1" roughness="0.8"/><m:pbmetallic name="Default" ${defaultScalars ? '' : 'metallicness="0" roughness="0"'}/></m:pbmetallicdisplayproperties>` : ''}
    <basematerials id="10" ${properties ? `${namespaced ? 'm:' : ''}displaypropertiesid="20"` : ''}><base name="same" displaycolor="#c0804000"/><base name="same" displaycolor="#c0804080"/><base name="Default" displaycolor="#fafafbff"/></basematerials>
    <basematerials id="12"><base name="colour only" displaycolor="#20cc4040"/></basematerials><basematerials id="13"><base name="Default" displaycolor="#fafafbff"/></basematerials>
    <m:colorgroup id="40"><m:color color="#112233"/></m:colorgroup>` : ''}
    <object id="1" name="mixed" ${noMaterial ? '' : 'pid="10" pindex="0"'}><mesh>${vertices}<triangles>${triangle('')}${noMaterial ? '' : triangle('p1="1"') + triangle('p1="2"')}</triangles></mesh></object>
    ${noMaterial ? '' : `<object id="2" pid="12" pindex="0"><mesh>${vertices}<triangles>${triangle('')}</triangles></mesh></object><object id="3" pid="13" pindex="0"><mesh>${vertices}<triangles>${triangle('')}</triangles></mesh></object>`}
    </resources><build><item objectid="1"/>${noMaterial ? '' : '<item objectid="1" transform="1 0 0 0 1 0 0 0 1 10 0 0"/><item objectid="2"/><item objectid="3"/>'}</build></model>`;
  return zipSync({ '_rels/.rels': strToU8('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="r1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>'),
    '3D/3dmodel.model': strToU8(model), 'Metadata/unchanged.txt': strToU8('unrelated package entry') });
}

async function xmlEnvironment(t) {
  const { JSDOM } = await import('jsdom');
  const dom = new JSDOM();
  const before = { DOMParser: globalThis.DOMParser, XMLSerializer: globalThis.XMLSerializer };
  globalThis.DOMParser = dom.window.DOMParser; globalThis.XMLSerializer = dom.window.XMLSerializer;
  t.after(() => { for (const [key, value] of Object.entries(before)) { if (value === undefined) delete globalThis[key]; else globalThis[key] = value; } dom.window.close(); });
}

test("real 3MF metallic display properties and alpha survive decode, modes and Preview siblings", async t => {
  await xmlEnvironment(t);
  const THREE = await import('three');
  const { buildMeshDataFrom3MfBuffer } = await import('./threeMfMeshData.js');
  const { buildMeshObjects } = await import('./meshObjects.js');
  const { buildMeshScene } = await import('./meshScene.js');
  const materialSettings = { defaultColor: '#b6c4ce', fillColors: ['#ff8800'], roughness: 0.58, metalness: 0.02, clearcoat: 0.12, emissiveIntensity: 0.02 };
  const original = { authored: false, materialSettings, surface: { style: 'shaded', opacity: 1 } };
  for (const namespaced of [true, false]) {
    const bytes = await metallicPackage({ namespaced }), unchanged = bytes.slice();
    const data = await buildMeshDataFrom3MfBuffer(bytes.buffer);
    const metadata = JSON.stringify(data.parts);
    assert.equal(data.parts.length, 8, 'three material subsets per repeated object, plus colour-only and generated default');
    assert.deepEqual(data.parts.slice(0, 3).map(part => [part.finish.metalness, part.finish.roughness, part.opacity]), [[1, 0.3, 0], [1, 0.8, 128 / 255], [0, 0, 1]]);
    assert.deepEqual(data.parts.slice(3, 6).map(part => part.finish), data.parts.slice(0, 3).map(part => part.finish));
    assert.deepEqual(data.parts.slice(0, 6).map(part => part.path), [[1], [1], [1], [2], [2], [2]]);
    assert.equal(data.parts[6].opacity, 64 / 255, 'colour-only base alpha is retained');
    assert.equal(data.parts[6].finish, undefined);
    assert.equal(data.parts[7].finish, undefined, 'generated default is not an authored finish');
    const objects = buildMeshObjects(THREE, data);
    assert.equal(objects[2].color.getHexString(), 'fafafb', 'explicit dielectric named Default keeps its default-looking source colour');
    objects.forEach(object => object.geometry.dispose());
    const scene = buildMeshScene(THREE, data), meshes = scene.object3D.children;
    assert.equal(scene.keepsAuthoredFinish, true, 'authored metals request the existing neutral reflection fill');
    const state = () => meshes.map(mesh => [mesh.material.metalness, mesh.material.roughness, mesh.material.opacity, mesh.material.color.getHexString()]);
    scene.setSurfaceLook(original);
    const regular = state();
    assert.deepEqual(regular.slice(0, 3).map(row => row.slice(0, 3)), [[1, 0.3, 0], [1, 0.8, 128 / 255], [0, 0, 1]]);
    assert.deepEqual([meshes[0].material.transparent, meshes[0].material.depthWrite], [true, false]);
    assert.equal(meshes[6].material.opacity, 64 / 255);
    scene.setSurfaceLook({ ...original, materialSettings: { ...materialSettings, overrideSourceColors: true } });
    assert.equal(meshes[1].material.metalness, 0.02);
    scene.setSurfaceLook({ ...original, finishes: false, surface: { style: 'shaded', opacity: 0.22 } });
    assert.equal(meshes[1].material.opacity, 128 / 255 * 0.22);
    scene.setSurfaceLook({ ...original, surface: { style: 'flat', opacity: 0.5 } });
    assert.equal(meshes[1].material.isMeshBasicMaterial, true);
    scene.setSurfaceLook(original); assert.deepEqual(state(), regular);
    const sibling = scene.createSibling();
    sibling.setSurfaceLook({ ...original, authored: true, materialSettings: { ...materialSettings, roughness: 0.34, metalness: 0, clearcoat: 0.3, emissiveIntensity: 0 } });
    assert.deepEqual(sibling.object3D.children.slice(0, 3).map(mesh => [mesh.material.metalness, mesh.material.roughness, mesh.material.opacity]), [[1, 0.3, 0], [1, 0.8, 128 / 255], [0, 0, 1]]);
    assert.notEqual(sibling.object3D.children[1].material, meshes[1].material);
    assert.equal(sibling.object3D.children[1].geometry.attributes.position, meshes[1].geometry.attributes.position);
    sibling.dispose(); scene.setSurfaceLook(original); assert.deepEqual(state(), regular);
    assert.equal(JSON.stringify(data.parts), metadata, 'mode changes and siblings never mutate decoded material metadata');
    assert.deepEqual(bytes, unchanged, 'the archive bytes are untouched');
    scene.dispose();
  }
});

test("ordinary 3MF fallback finishes remain unchanged and malformed metallic tables fail loudly", async t => {
  await xmlEnvironment(t);
  const THREE = await import('three');
  const { buildMeshDataFrom3MfBuffer } = await import('./threeMfMeshData.js');
  const { buildMeshScene } = await import('./meshScene.js');
  for (const options of [{ properties: false }, { noMaterial: true }]) {
    const data = await buildMeshDataFrom3MfBuffer((await metallicPackage(options)).buffer);
    assert.ok(data.parts.every(part => !part.finish));
    const scene = buildMeshScene(THREE, data);
    assert.equal(scene.keepsAuthoredFinish, undefined);
    scene.setSurfaceLook({ authored: true, materialSettings: { roughness: 0.34, metalness: 0, clearcoat: 0.3 }, surface: { style: 'shaded', opacity: 1 } });
    assert.ok(scene.object3D.children.every(mesh => mesh.material.roughness === 0.34 && mesh.material.clearcoat === 0.3));
    scene.dispose();
  }
  const defaults = await buildMeshDataFrom3MfBuffer((await metallicPackage({ defaultScalars: true })).buffer);
  assert.deepEqual(defaults.parts[2].finish, { metalness: 0, roughness: 1 }, 'omitted scalars take the extension defaults');
  await assert.rejects(() => metallicPackage({ malformed: true }).then(bytes => buildMeshDataFrom3MfBuffer(bytes.buffer)), /Invalid 3MF metallic display properties/);
});


test("the 3MF bridge parses only material tables and preserves geometry markup through XML escapes", async t => {
  await xmlEnvironment(t);
  const { bridgeThreeMfMaterialModel } = await import('./threeMfMeshData.js');
  const NativeParser = globalThis.DOMParser, parsed = [];
  globalThis.DOMParser = class {
    parseFromString(text, type) { parsed.push(text); return new NativeParser().parseFromString(text, type); }
  };
  const geometry = '<c:object id="1"><c:mesh><!-- </c:object><c:basematerials id="fake"/> --><![CDATA[</c:object><m:pbmetallicdisplayproperties id="fake"/>]]><?ignored </c:object> ?><c:vertices><c:vertex x="0" y="0" z="0"/></c:vertices><c:triangles/></c:mesh></c:object>';
  const xml = '<?xml version="1.0"?><!-- <resources><basematerials id="fake"/></resources> -->'
    + '<!DOCTYPE c:model [<!ENTITY label "metal">]><c:model unit="inch" xmlns:c="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" xmlns:m="http://schemas.microsoft.com/3dmanufacturing/material/2015/02">'
    + '<c:metadata name="Description"><![CDATA[<resources><m:pbmetallicdisplayproperties id="fake"/></resources>]]></c:metadata>'
    + '<c:resources>' + geometry + '<m:pbmetallicdisplayproperties id="20"><m:pbmetallic name="&label;" metallicness="1" roughness="0.3"/></m:pbmetallicdisplayproperties>'
    + '<c:basematerials id="10" m:displaypropertiesid="20"><c:base name="&label;" displaycolor="#80808080"/></c:basematerials></c:resources><c:build/></c:model>';
  const bytes = new TextEncoder().encode(xml), result = bridgeThreeMfMaterialModel(bytes);
  assert.equal(result.adapted, true);
  assert.equal(result.materialBearing, true);
  assert.equal(result.unit, 'inch');
  assert.equal(parsed.length, 1);
  assert.ok(!parsed[0].includes('<c:mesh>') && !parsed[0].includes('<c:triangles'), 'the adapter DOM contains no geometry, even with materials after objects');
  const output = new TextDecoder().decode(result.bytes);
  assert.ok(output.includes(geometry), 'the entire geometry subtree is copied byte-for-byte');
  const document = new NativeParser().parseFromString(output, 'application/xml');
  assert.equal(document.querySelector('parsererror'), null);
  assert.equal(document.getElementsByTagNameNS('*', 'base')[0].getAttribute('displaypropertiesid'), '20');
  assert.deepEqual(new TextDecoder().decode(bytes), xml, 'source bytes remain unchanged');
  parsed.length = 0;
  const ordinary = new TextEncoder().encode('<model><resources><object id="1"><mesh><triangles/></mesh></object></resources></model>');
  const unchanged = bridgeThreeMfMaterialModel(ordinary);
  assert.equal(unchanged.bytes, ordinary, 'a model without a PB candidate reuses its exact input');
  assert.equal(unchanged.adapted, false);
  assert.equal(parsed.length, 0, 'ordinary geometry never creates an adapter DOM');
  const fakeOnly = new TextEncoder().encode('<model><resources><!-- <pbmetallicdisplayproperties/> --><![CDATA[<basematerials displaypropertiesid="20"/>]]><object><mesh/></object></resources></model>');
  assert.equal(bridgeThreeMfMaterialModel(fakeOnly).bytes, fakeOnly, 'comments and CDATA cannot introduce material resources');
});
