import assert from "node:assert/strict";
import { test } from "node:test";
import * as THREE from "three";
import { CAD_DISPLAY_MODE } from "../../common/displaySettings.js";
import { applyMaterialSettingsToRecord as applySceneMaterialSettings } from "../../common/cadScene.js";
import {
  applyMaterialSettingsToRecord,
  createMaterialFillColor,
  createSurfaceMaterial,
  partUsesDisplayVertexColors,
  readSourceColor,
  resolveSourceBaseColor,
  shapeSourceColor,
  shapeSourceColorBuffer,
  shouldUseDisplayVertexColors
} from "./surfaceMaterials.js";

const EPSILON = 1e-6;

function assertNear(actual, expected, message = "") {
  assert.ok(Math.abs(actual - expected) < EPSILON, `${message} expected ${expected}, received ${actual}`);
}

function assertColorNear(color, expected, message = "") {
  assertNear(color.r, expected[0], `${message} r`);
  assertNear(color.g, expected[1], `${message} g`);
  assertNear(color.b, expected[2], `${message} b`);
}

test("surface material helpers preserve viewer material defaults", () => {
  const material = createSurfaceMaterial(THREE, {
    surface: "#102030",
    surfaceOpacity: 0.5,
    surfaceRoughness: 0.25,
    surfaceMetalness: 0.35,
    surfaceClearcoat: 0.45,
    surfaceClearcoatRoughness: 0.55
  }, {
    useVertexColors: true
  });

  assert.equal(material.type, "MeshPhysicalMaterial");
  assert.equal(material.color.getHexString(), "102030");
  assert.equal(material.vertexColors, true);
  assert.equal(material.transparent, true);
  assert.equal(material.opacity, 0.5);
  assert.equal(material.roughness, 0.25);
  assert.equal(material.metalness, 0.35);
  assert.equal(material.clearcoat, 0.45);
  assert.equal(material.clearcoatRoughness, 0.55);
  assert.equal(material.polygonOffset, false);
  assert.equal(material.polygonOffsetFactor, 0);
  assert.equal(material.polygonOffsetUnits, 0);
});

test("source color helpers read, shape, and buffer source colors consistently", () => {
  assert.equal(readSourceColor(THREE, "#abc").getHexString(), "aabbcc");
  assert.equal(readSourceColor(THREE, "not-a-color"), null);

  const source = new THREE.Color(0.2, 0.4, 0.6);
  const shaped = shapeSourceColor(THREE, source, {
    tintStrength: 0,
    saturation: 1,
    contrast: 1,
    brightness: 0.5
  });
  assertColorNear(shaped, [0.1, 0.2, 0.3], "shaped");

  const colors = new Float32Array([0.2, 0.4, 0.6, 1, 0.5, 0]);
  const originalColors = Array.from(colors);
  const shapedBuffer = shapeSourceColorBuffer(THREE, colors, {
    tintStrength: 0,
    saturation: 1,
    contrast: 1,
    brightness: 0.5
  });
  assert.notEqual(shapedBuffer, colors);
  assert.deepEqual(Array.from(colors), originalColors);
  assertColorNear({ r: shapedBuffer[0], g: shapedBuffer[1], b: shapedBuffer[2] }, [0.1, 0.2, 0.3], "first buffer color");
  assertColorNear({ r: shapedBuffer[3], g: shapedBuffer[4], b: shapedBuffer[5] }, [0.5, 0.25, 0], "second buffer color");

  const invalid = [0.2, 0.4];
  assert.equal(shapeSourceColorBuffer(THREE, invalid, {}), invalid);
});

test("source color shaping preserves explicit zero-valued controls", () => {
  const source = new THREE.Color(0.2, 0.4, 0.6);
  const black = shapeSourceColor(THREE, source, { brightness: 0 });
  assertColorNear(black, [0, 0, 0], "zero brightness");

  const neutralContrast = shapeSourceColor(THREE, source, { contrast: 0 });
  assertColorNear(neutralContrast, [0.5, 0.5, 0.5], "zero contrast");

  const desaturated = shapeSourceColor(THREE, source, { saturation: 0 });
  assertNear(desaturated.r, desaturated.g, "zero saturation red/green");
  assertNear(desaturated.g, desaturated.b, "zero saturation green/blue");
});

test("surface material source-color gates match mesh and part metadata", () => {
  const meshData = {
    has_source_colors: true,
    colors: new Float32Array([1, 0, 0, 0, 1, 0])
  };
  assert.equal(shouldUseDisplayVertexColors(meshData), true);
  assert.equal(partUsesDisplayVertexColors(meshData, null), true);
  assert.equal(partUsesDisplayVertexColors(meshData, { hasSourceColors: false }), false);
  assert.equal(partUsesDisplayVertexColors(meshData, { hasSourceColors: true }), true);
  assert.equal(shouldUseDisplayVertexColors({ has_source_colors: true, colors: [1, 0] }), false);
  assert.equal(partUsesDisplayVertexColors({ has_source_colors: false, colors: meshData.colors }, {}), false);
});

test("fill colors and record material settings preserve override semantics", () => {
  assert.equal(createMaterialFillColor(THREE, {
    defaultColor: "#445566",
    fillColors: ["#112233", "#aabbcc"],
    cycleColors: true
  }, 1).getHexString(), "aabbcc");

  const vertexColorBase = resolveSourceBaseColor(THREE, {
    hasVertexColors: true,
    sourceColor: new THREE.Color(0.2, 0.3, 0.4),
    materialSettings: { defaultColor: "#445566" }
  });
  assert.equal(vertexColorBase.getHexString(), "ffffff");

  const material = new THREE.MeshPhysicalMaterial({ color: "#000000" });
  const initialMaterialVersion = material.version;
  const record = {
    material,
    hasVertexColors: true,
    sourceColor: new THREE.Color(0.2, 0.3, 0.4),
    fillIndex: 1
  };
  applyMaterialSettingsToRecord(THREE, record, {
    defaultColor: "#445566",
    fillColors: ["#112233", "#aabbcc"],
    cycleColors: true,
    overrideSourceColors: true,
    roughness: 0.2,
    metalness: 0.3,
    clearcoat: 0.4,
    clearcoatRoughness: 0.5,
    opacity: 0.6,
    envMapIntensity: 0.7,
    emissiveIntensity: 0.8
  });

  assert.equal(record.useVertexColors, false);
  assert.equal(record.baseColor.getHexString(), "aabbcc");
  assert.equal(record.material.vertexColors, false);
  assert.equal(record.material.color.getHexString(), "aabbcc");
  assert.equal(record.material.roughness, 0.2);
  assert.equal(record.material.metalness, 0.3);
  assert.equal(record.material.clearcoat, 0.4);
  assert.equal(record.material.clearcoatRoughness, 0.5);
  assert.equal(record.baseOpacity, 0.6);
  assert.equal(record.material.opacity, 0.6);
  assert.equal(record.material.transparent, true);
  assert.equal(record.material.envMapIntensity, 0.7);
  assert.equal(record.baseEmissiveIntensity, 0.8);
  assert.equal(record.material.emissiveIntensity, 0.8);
  assert.ok(record.material.version > initialMaterialVersion);
});

test("record material settings preserve display-mode surface opacity", () => {
  const transparentMaterial = new THREE.MeshPhysicalMaterial({ color: "#000000" });
  const transparentRecord = {
    material: transparentMaterial,
    hasVertexColors: false,
    fillIndex: 0
  };

  applyMaterialSettingsToRecord(THREE, transparentRecord, {
    defaultColor: "#445566",
    opacity: 1
  }, {
    displayMode: CAD_DISPLAY_MODE.TRANSPARENT
  });

  assert.equal(transparentRecord.baseOpacity, 0.22);
  assert.equal(transparentRecord.material.opacity, 0.22);
  assert.equal(transparentRecord.material.transparent, true);
  assert.equal(transparentRecord.material.depthWrite, false);

  const wireframeMaterial = new THREE.MeshPhysicalMaterial({ color: "#000000" });
  const wireframeRecord = {
    material: wireframeMaterial,
    hasVertexColors: true,
    fillIndex: 0
  };

  applyMaterialSettingsToRecord(THREE, wireframeRecord, {
    defaultColor: "#445566",
    opacity: 1
  }, {
    displayMode: CAD_DISPLAY_MODE.WIREFRAME
  });

  assert.equal(wireframeRecord.useVertexColors, false);
  assert.equal(wireframeRecord.baseOpacity, 0.035);
  assert.equal(wireframeRecord.material.opacity, 0.035);
  assert.equal(wireframeRecord.material.transparent, true);
  assert.equal(wireframeRecord.material.depthWrite, false);
});

for (const [name, apply] of [["scene", applySceneMaterialSettings], ["viewer", applyMaterialSettingsToRecord]]) {
  test(`${name} material updates never reuse an externally aliased emissive color`, () => {
    const source = new THREE.Color(0.2, 0.4, 0.6);
    const record = {
      material: new THREE.MeshPhysicalMaterial(),
      sourceColor: source,
      hasSourceColor: true,
      baseEmissiveColor: source
    };
    const settings = { opacity: 1, brightness: 0.5, emissiveIntensity: 0.2 };
    for (let index = 0; index < 3; index += 1) {
      if (index === 2) record.baseEmissiveColor = source; // replacement after adoption
      apply(THREE, record, settings);
      assertColorNear(source, [0.2, 0.4, 0.6]);
      assertColorNear(record.baseEmissiveColor, [0.1, 0.2, 0.3]);
      assert.notEqual(record.baseEmissiveColor, source);
    }
    const owned = record.baseEmissiveColor;
    // Both consumers share the same ownership boundary, without cloning again.
    const other = apply === applySceneMaterialSettings ? applyMaterialSettingsToRecord : applySceneMaterialSettings;
    other(THREE, record, settings);
    assert.equal(record.baseEmissiveColor, owned);
    record.sourceColor = owned; // source can adopt an already-owned color too
    apply(THREE, record, settings);
    assertColorNear(owned, [0.1, 0.2, 0.3]);
    assertColorNear(record.baseEmissiveColor, [0.05, 0.1, 0.15]);
    assert.notEqual(record.baseEmissiveColor, owned);
    record.material.dispose();
  });

  test(`${name} material updates retain programs for unchanged records and observe live appearance changes`, () => {
    const record = {
      material: new THREE.MeshPhysicalMaterial(),
      sourceColor: new THREE.Color("#123456"),
      hasSourceColor: true,
      hasVertexColors: false,
      sourceOpacity: 1,
      sourcePart: { material: { roughness: 0.6 } }
    };
    const settings = { opacity: 1, emissiveIntensity: 0.2, clearcoat: 0, roughness: 0.8 };
    apply(THREE, record, settings);
    const version = record.material.version;
    const emissiveColor = record.baseEmissiveColor;
    for (let index = 0; index < 10; index += 1) apply(THREE, record, { ...settings });
    assert.equal(record.material.version, version, "unchanged publications do not refresh the program");
    assert.equal(record.baseEmissiveColor, emissiveColor, "the record retains its owned emissive color");
    assert.notEqual(record.baseEmissiveColor, record.baseColor);
    assert.notEqual(record.baseEmissiveColor, record.sourceColor);

    record.sourceColor.set("#abcdef");
    record.sourcePart.material.roughness = 0.3;
    settings.emissiveIntensity = 0.7;
    settings.envMapIntensity = 0.9;
    apply(THREE, record, settings);
    assert.equal(record.material.color.getHexString(), "abcdef");
    assert.equal(record.material.emissive.getHexString(), "abcdef");
    assert.equal(record.material.emissiveIntensity, 0.7);
    assert.equal(record.material.envMapIntensity, 0.9);
    assert.equal(record.material.roughness, 0.3);
    assert.equal(record.material.version, version, "uniform changes do not refresh the program");

    settings.clearcoat = 0.4;
    apply(THREE, record, settings);
    assert.ok(record.material.version > version, "physical feature changes still refresh the program");
    const coatedVersion = record.material.version;
    apply(THREE, record, settings);
    assert.equal(record.material.version, coatedVersion);
    record.hasVertexColors = true;
    apply(THREE, record, settings);
    assert.equal(record.material.vertexColors, true);
    assert.ok(record.material.version > coatedVersion);
    const coloredVersion = record.material.version;
    settings.opacity = 0.5;
    apply(THREE, record, settings);
    assert.equal(record.material.transparent, true);
    assert.ok(record.material.version > coloredVersion);
    const transparentVersion = record.material.version;
    apply(THREE, record, settings);
    assert.equal(record.material.version, transparentVersion);
    settings.opacity = 1;
    apply(THREE, record, settings, { displayMode: CAD_DISPLAY_MODE.WIREFRAME });
    assert.equal(record.material.vertexColors, false);
    assert.ok(record.material.version > transparentVersion);
    const wireframeVersion = record.material.version;
    apply(THREE, record, settings, { displayMode: CAD_DISPLAY_MODE.WIREFRAME });
    assert.equal(record.material.version, wireframeVersion);
    apply(THREE, record, settings);
    assert.equal(record.material.vertexColors, true);
    assert.equal(record.material.transparent, false);
    assert.ok(record.material.version > wireframeVersion);
    record.material.dispose();
  });
}
