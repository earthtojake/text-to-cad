import assert from "node:assert/strict";
import test from "node:test";

import {
  SOURCE_MATERIAL_DEFAULTS,
  SOURCE_SIDECAR_SCHEMA_VERSION,
  applySourceAppearance,
  loadSourceSidecar,
  normalizeSourceAnimation,
  normalizeSourceAppearance,
  resolveSourceAppearance,
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

test("session overlays patch shared materials and can duplicate one assignment", () => {
  const overlay = {
    materials: {
      aluminum: { roughness: 0.6 },
      "aluminum-copy": { name: "Brushed aluminum copy", baseColor: "#112233", metalness: 0.9 }
    },
    assignments: { "o1.2": "aluminum-copy" }
  };
  const resolved = resolveSourceAppearance(APPEARANCE, overlay);
  assert.deepEqual(resolved.assignments, { "o1.2": "aluminum-copy" });
  assert.deepEqual(resolved.materials, {
    aluminum: { name: "Brushed aluminum", baseColor: "#AABBCC", roughness: 0.6, metalness: 1 },
    "aluminum-copy": { name: "Brushed aluminum copy", baseColor: "#112233", metalness: 0.9 },
    unused: { name: "Unused", roughness: 0.8 }
  });
  assert.deepEqual(sourceMaterialForOccurrence(APPEARANCE, "o1.2", overlay), {
    materialId: "aluminum-copy",
    ...SOURCE_MATERIAL_DEFAULTS,
    name: "Brushed aluminum copy",
    baseColor: "#112233",
    metalness: 0.9
  });
  assert.throws(() => resolveSourceAppearance(APPEARANCE, {
    materials: { copy: { roughness: 0.2 } }, assignments: { "o1.2": "copy" }
  }), /requires a nonempty name/);
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
  assert.throws(() => validateSourceSidecar({ ...valid, schemaVersion: 8 }, {
    url: "/part.step.json", documentHash: DOCUMENT_HASH
  }), /unsupported sidecar schema 8 \(expected 9\)/);
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
