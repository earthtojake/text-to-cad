import assert from "node:assert/strict";
import test from "node:test";

import {
  SOURCE_MATERIAL_DEFAULTS,
  SOURCE_SIDECAR_SCHEMA_VERSION,
  applySourceAppearance,
  applySourceAppearanceToMeshData,
  loadSourceSidecar,
  normalizeSourceAnimation,
  normalizeSourceAppearance,
  sourceAppearanceGeometry,
  sourceMaterialForOccurrence,
  validateSourceSidecar
} from "./sourceSidecar.js";

const DOCUMENT_HASH = "a".repeat(64);
const APPEARANCE = {
  materials: {
    aluminum: { name: "Brushed aluminum", baseColor: "#aabbcc", roughness: 0.25, metalness: 1 },
    unused: { name: "Unused", roughness: 0.8 }
  },
  assignments: { "o1.2": "aluminum" }
};

function descriptor() {
  return {
    kind: "assembly-package",
    occurrences: [
      { id: "o1.1", component: "cid-a", name: "base" },
      { id: "o1.2", component: "cid-b", name: "cap", color: [0.2, 0.3, 0.4, 0.5] }
    ]
  };
}

test("schema-v9 appearance is closed, named, sparse, and assignment-bound", () => {
  assert.deepEqual(normalizeSourceAppearance(APPEARANCE), {
    materials: {
      aluminum: { name: "Brushed aluminum", baseColor: "#AABBCC", roughness: 0.25, metalness: 1 },
      unused: { name: "Unused", roughness: 0.8 }
    },
    assignments: { "o1.2": "aluminum" }
  });
  assert.throws(() => normalizeSourceAppearance({ occurrences: {} }), /materials and assignments/);
  assert.throws(() => normalizeSourceAppearance({
    materials: { a: { name: "A", sheen: 0.5 } }, assignments: { "o1.1": "a" }
  }), /must contain only/);
  assert.throws(() => normalizeSourceAppearance({
    materials: { a: { name: "A", roughness: NaN } }, assignments: { "o1.1": "a" }
  }), /finite number/);
  assert.throws(() => normalizeSourceAppearance({
    materials: { a: { name: "A" } }, assignments: { "o1.1": "missing" }
  }), /unknown material/);
});

test("authored occurrence material lookup expands sparse defaults", () => {
  assert.deepEqual(sourceMaterialForOccurrence(APPEARANCE, "o1.2"), {
    materialId: "aluminum",
    ...SOURCE_MATERIAL_DEFAULTS,
    name: "Brushed aluminum",
    baseColor: "#AABBCC",
    roughness: 0.25,
    metalness: 1
  });
  assert.equal(sourceMaterialForOccurrence(APPEARANCE, "o1.1"), null);
});

test("read-only mesh appearance mapping follows live assignments and preserves geometry identity", () => {
  const geometry = { vertices: new Float32Array([0, 0, 0]) };
  const transform = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
  const source = {
    parts: [
      { id: "o1.1", occurrenceId: "o1.1", sourceMesh: geometry, transform,
        color: "#223344", sourceColor: "#223344", opacity: 0.6, sourceOpacity: 0.6 },
      { id: "o1.2", occurrenceId: "o1.2", sourceMesh: geometry, transform,
        color: "#556677", sourceColor: "#556677", sourceOpacity: 1 }
    ]
  };
  const first = applySourceAppearanceToMeshData(source, APPEARANCE);
  assert.notEqual(first, source);
  assert.equal(sourceAppearanceGeometry(first), source);
  assert.equal(first.parts[0].color, "#223344");
  assert.equal(first.parts[0].material, undefined);
  assert.deepEqual(first.parts[1].material, {
    roughness: 0.25, metalness: 1, clearcoat: 0, clearcoatRoughness: 0.26, opacity: 1
  });
  assert.equal(first.parts[1].color, "#AABBCC");

  const reassigned = applySourceAppearanceToMeshData(first, {
    materials: { rubber: { name: "Rubber", roughness: 0.9, opacity: 0.5 } },
    assignments: { "o1.1": "rubber" }
  });
  assert.equal(sourceAppearanceGeometry(reassigned), source);
  assert.equal(reassigned.parts[0].materialId, "rubber");
  assert.equal(reassigned.parts[0].opacity, 0.3);
  assert.equal(reassigned.parts[1].materialId, undefined);
  assert.equal(reassigned.parts[1].materialName, undefined);
  assert.equal(reassigned.parts[1].material, undefined);
  assert.equal(reassigned.parts[1].color, "#556677");
  assert.equal(reassigned.parts[1].opacity, undefined);
  assert.equal(source.parts[0].material, undefined, "the source publication stays immutable");
});

test("authored base color replaces vertex colors and removal restores their original mode", () => {
  const sourceMesh = { vertices: new Float32Array(9), colors: new Float32Array(9) };
  const source = { parts: [{ id: "o1.2", sourceMesh, hasSourceColors: true }] };
  const painted = applySourceAppearanceToMeshData(source, APPEARANCE);
  assert.equal(painted.parts[0].hasSourceColors, false);
  assert.equal(painted.parts[0].sourceHasVertexColors, true);
  const restored = applySourceAppearanceToMeshData(painted, null);
  assert.equal(restored.parts[0].hasSourceColors, true);
  assert.equal(restored.parts[0].sourceMesh, sourceMesh);
  assert.equal(source.parts[0].hasSourceColors, true);
});

test("removing STEP appearance restores sources while null stays a no-op for native meshes", () => {
  const native = { parts: [{ id: "mesh", color: "#123456", opacity: 0.4 }] };
  assert.equal(applySourceAppearanceToMeshData(native, null), native);

  const decorated = {
    appearance: APPEARANCE,
    parts: [{
      id: "o1.2", occurrenceId: "o1.2", color: "#AABBCC", sourceColor: "#102030",
      materialId: "aluminum", materialName: "Brushed aluminum", material: { metalness: 1, opacity: 0.4 },
      opacity: 0.2, sourceOpacity: 0.5
    }]
  };
  const restored = applySourceAppearanceToMeshData(decorated, null);
  assert.equal(restored.appearance, null);
  assert.deepEqual(restored.parts[0], {
    id: "o1.2", occurrenceId: "o1.2", color: "#102030", sourceColor: "#102030",
    opacity: 0.5, sourceOpacity: 0.5
  });
  assert.equal(decorated.parts[0].materialId, "aluminum");
});

test("appearance composition owns changes and carries material identity plus effective defaults", () => {
  const stored = descriptor();
  const composed = applySourceAppearance(stored, APPEARANCE);
  assert.notEqual(composed, stored);
  assert.equal(composed.occurrences[0], stored.occurrences[0]);
  assert.deepEqual(composed.occurrences[1], {
    ...stored.occurrences[1],
    baseColor: "#AABBCC",
    materialId: "aluminum",
    materialName: "Brushed aluminum",
    material: { ...SOURCE_MATERIAL_DEFAULTS, roughness: 0.25, metalness: 1 }
  });
  assert.equal(stored.occurrences[1].material, undefined);
  assert.throws(() => applySourceAppearance(stored, {
    materials: { a: { name: "A" } }, assignments: { missing: "a" }
  }), /missing document occurrence missing/);
});

test("sidecars are closed, schema-bound, document-bound, and normalize embedded animation", () => {
  const valid = {
    schemaVersion: SOURCE_SIDECAR_SCHEMA_VERSION,
    documentHash: DOCUMENT_HASH,
    appearance: APPEARANCE,
    animation: { language: "javascript", source: "export const clips = {};\n" }
  };
  const normalized = validateSourceSidecar(valid, { url: "/part.step.json", documentHash: DOCUMENT_HASH });
  assert.equal(normalized.animation.source, valid.animation.source);
  assert.equal(normalized.appearance.materials.aluminum.baseColor, "#AABBCC");
  assert.throws(() => validateSourceSidecar({ ...valid, extra: true }, {
    url: "/part.step.json", documentHash: DOCUMENT_HASH
  }), /unknown sidecar field extra/);
  assert.throws(() => validateSourceSidecar({ ...valid, documentHash: "b".repeat(64) }, {
    url: "/part.step.json", documentHash: DOCUMENT_HASH
  }), /does not match STEP sha256/);
  // Word for word what the Python reader says: what is lost, and the migration to do.
  for (const [payload, found] of [[{ ...valid, schemaVersion: 8 }, "8"], ["not an object", "none"], [{ ...valid, schemaVersion: undefined }, "none"]]) {
    assert.throws(() => validateSourceSidecar(payload, { url: "/part.step.json", documentHash: DOCUMENT_HASH }), (error) => {
      assert.match(error.message, new RegExp(`part\\.step\\.json: unsupported sidecar schema ${found} \\(expected 9\\),`));
      assert.match(error.message, /the kinematics, materials and animation it declares cannot be read and this model poses and plays nothing\./);
      assert.match(error.message, /Migrate it now: rebuild the model \(python part\.py\) or re-annotate the document \(cadgen step build\)/);
      return true;
    });
  }
  assert.throws(() => normalizeSourceAnimation("export const clips = {};"), /only language and source/);
  assert.throws(() => normalizeSourceAnimation({ language: "typescript", source: "x" }), /javascript/);
});

test("a mutable sidecar URL is never retained as immutable content", async (t) => {
  const originalFetch = globalThis.fetch;
  let fetches = 0;
  globalThis.fetch = async () => {
    fetches += 1;
    return new Response(JSON.stringify({
      schemaVersion: SOURCE_SIDECAR_SCHEMA_VERSION,
      documentHash: DOCUMENT_HASH,
      appearance: {
        materials: { finish: { name: "Finish", clearcoat: fetches === 1 ? 0.4 : 0.9 } },
        assignments: { "o1.1": "finish" }
      }
    }));
  };
  t.after(() => { globalThis.fetch = originalFetch; });
  const first = await loadSourceSidecar("/part.step.json", { documentHash: DOCUMENT_HASH });
  const second = await loadSourceSidecar("/part.step.json", { documentHash: DOCUMENT_HASH });
  assert.equal(first.appearance.materials.finish.clearcoat, 0.4);
  assert.equal(second.appearance.materials.finish.clearcoat, 0.9);
  assert.equal(fetches, 2);
});

test("changing the owning render session rejects a late sidecar response", async () => {
  const controller = new AbortController();
  let finish;
  const pending = loadSourceSidecar("http://workspace.test/part.step.json", {
    documentHash: DOCUMENT_HASH,
    signal: controller.signal,
    fetch: () => new Promise((resolve) => { finish = resolve; }),
  });
  controller.abort();
  finish(Response.json({ schemaVersion: SOURCE_SIDECAR_SCHEMA_VERSION, documentHash: DOCUMENT_HASH }));
  await assert.rejects(pending, { name: "AbortError" });
});
