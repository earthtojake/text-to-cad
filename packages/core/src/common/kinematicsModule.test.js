import assert from "node:assert/strict";
import { test } from "node:test";
import * as THREE from "three";

import {
  SOURCE_SIDECAR_SCHEMA_VERSION,
  loadKinematicsModuleDefinition,
  previewKinematicsModuleDefinition
} from "./kinematicsModule.js";
import { resolveStepModuleFeatures } from "./stepModule.js";
import { buildStepModuleContext, createStepModuleEffectsApi } from "./stepModuleEffects.js";

const KINEMATICS = {
  mates: [
    {
      name: "swing",
      kind: "revolute",
      parent: "#base",
      child: "#flap",
      axis: { origin: [0, 0, 0], dir: [0, 0, 1] },
      limits: { value: [0, 120] }
    }
  ],
  poses: { open: { swing: 90 } }
};

const SIDECAR_URL = "/__cad/asset?file=hinge.step.json";
const DOCUMENT_HASH = "a".repeat(64);

function stubSidecar(t, payload) {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "content-type": "application/json" }
  });
  t.after(() => {
    globalThis.fetch = originalFetch;
  });
}

test("a current-schema sidecar compiles into a step-module definition", async (t) => {
  stubSidecar(t, {
    schemaVersion: SOURCE_SIDECAR_SCHEMA_VERSION,
    documentHash: DOCUMENT_HASH,
    kinematics: KINEMATICS
  });

  const definition = await loadKinematicsModuleDefinition(SIDECAR_URL, {
    cadPath: "hinge.step",
    documentHash: DOCUMENT_HASH
  });

  assert.ok(definition);
  assert.deepEqual(Object.keys(definition.manifest.parameters), ["swing"]);
});

test("a sidecar at any other schema is refused with the current requirement", async (t) => {
  // Reading sections out of a file written to a different shape is how a model
  // silently loses its kinematics. The error states what is required now and
  // how to get there — never what the file used to be.
  stubSidecar(t, { schemaVersion: SOURCE_SIDECAR_SCHEMA_VERSION - 1, kinematics: KINEMATICS });

  await assert.rejects(
    () => loadKinematicsModuleDefinition(SIDECAR_URL, {
      cadPath: "hinge.step",
      documentHash: DOCUMENT_HASH
    }),
    (error) => {
      assert.match(
        error.message,
        new RegExp(`unsupported sidecar schema ${SOURCE_SIDECAR_SCHEMA_VERSION - 1} \\(expected ${SOURCE_SIDECAR_SCHEMA_VERSION}\\)`)
      );
      assert.match(error.message, /python hinge\.py/);
      assert.match(error.message, /cadgen step build/);
      return true;
    }
  );
});

test("a sidecar declaring no schema at all is refused the same way", async (t) => {
  stubSidecar(t, { kinematics: KINEMATICS });

  await assert.rejects(
    () => loadKinematicsModuleDefinition(SIDECAR_URL, { documentHash: DOCUMENT_HASH }),
    new RegExp(`unsupported sidecar schema none \\(expected ${SOURCE_SIDECAR_SCHEMA_VERSION}\\)`)
  );
});

test("a sidecar bound to different STEP bytes is refused", async (t) => {
  stubSidecar(t, {
    schemaVersion: SOURCE_SIDECAR_SCHEMA_VERSION,
    documentHash: "b".repeat(64),
    kinematics: KINEMATICS
  });

  await assert.rejects(
    () => loadKinematicsModuleDefinition(SIDECAR_URL, { documentHash: DOCUMENT_HASH }),
    /documentHash b+ does not match STEP sha256 a+/
  );
});

test("a saved sidecar load requires the resolved STEP digest", async (t) => {
  stubSidecar(t, {
    schemaVersion: SOURCE_SIDECAR_SCHEMA_VERSION,
    documentHash: DOCUMENT_HASH,
    kinematics: KINEMATICS
  });

  await assert.rejects(
    () => loadKinematicsModuleDefinition(SIDECAR_URL),
    /saved sidecar load requires the STEP documentHash/
  );
});

test("preview kinematics compile without fetching a saved sidecar", () => {
  const definition = previewKinematicsModuleDefinition(KINEMATICS, { cadPath: "hinge.step" });
  assert.ok(definition);
  assert.equal(definition.cadPath, "hinge.step");
  assert.deepEqual(Object.keys(definition.manifest.parameters), ["swing"]);
});

test("no sidecar url means nothing to load", async () => {
  assert.equal(await loadKinematicsModuleDefinition(""), null);
});

// A servo GROUP fastened to the moving frame, whose output horn — a part
// INSIDE that group — is fastened to the jaw beside it. Both mates name the
// horn, so the horn's parts sit in two target subtrees at once. The mate
// deltas are accumulated world motions, so the horn must take the jaw's
// (deepest mate wins) exactly once, not the servo group's on top of it.
const NESTED = {
  mates: [
    {
      name: "wrist", kind: "revolute", parent: "#base", child: "#frame",
      parentId: "#o1.0", childId: "#o1.1",
      axis: { origin: [0, 0, 0], dir: [0, 0, 1] },
      limits: { value: [-90, 90] }
    },
    {
      name: "frame__servo", kind: "fastened", parent: "#frame", child: "#servo",
      parentId: "#o1.1", childId: "#o1.2"
    },
    {
      name: "jaw", kind: "revolute", parent: "#frame", child: "#jaw",
      parentId: "#o1.1", childId: "#o1.3",
      axis: { origin: [10, 0, 0], dir: [0, 1, 0] },
      limits: { value: [0, 90] }
    },
    {
      name: "jaw__horn", kind: "fastened", parent: "#jaw", child: "#horn",
      parentId: "#o1.3", childId: "#o1.2.2"
    }
  ]
};

const NESTED_PARTS = ["o1.1", "o1.2.1", "o1.2.2", "o1.3"];

async function nestedEffects(t, values) {
  stubSidecar(t, { schemaVersion: SOURCE_SIDECAR_SCHEMA_VERSION, documentHash: DOCUMENT_HASH, kinematics: NESTED });
  const definition = await loadKinematicsModuleDefinition(SIDECAR_URL, {
    cadPath: "gripper.step",
    documentHash: DOCUMENT_HASH
  });
  const meshData = { parts: NESTED_PARTS.map((id) => ({ id })) };
  const features = resolveStepModuleFeatures(definition, { meshData });
  const effectsByPartId = new Map();
  const effects = createStepModuleEffectsApi(THREE, {
    meshData, features, runtime: null, effectsByPartId
  });
  definition.module.update(buildStepModuleContext({
    runtime: { THREE },
    stepModuleRuntime: { definition, parameterValues: values },
    features,
    effects
  }));
  return effectsByPartId;
}

function rotationAbout(axis, origin, degrees) {
  const direction = new THREE.Vector3(...axis).normalize();
  const point = new THREE.Vector3(...origin);
  return new THREE.Matrix4()
    .makeTranslation(point.x, point.y, point.z)
    .multiply(new THREE.Matrix4().makeRotationAxis(direction, (degrees * Math.PI) / 180))
    .multiply(new THREE.Matrix4().makeTranslation(-point.x, -point.y, -point.z));
}

function maxElementDelta(a, b) {
  return Math.max(...a.elements.map((value, index) => Math.abs(value - b.elements[index])));
}

test("a mate nested inside another mate's subtree applies upstream motion once", async (t) => {
  const effects = await nestedEffects(t, { wrist: 45, jaw: 30 });

  // Built here from the two axes, not from the evaluator under test: the horn
  // is bolted to the jaw, so it rides the wrist AND the jaw, once each.
  const wrist = rotationAbout([0, 0, 1], [0, 0, 0], 45);
  const jaw = new THREE.Matrix4().multiplyMatrices(wrist, rotationAbout([0, 1, 0], [10, 0, 0], 30));

  assert.ok(maxElementDelta(effects.get("o1.2.2").matrix, jaw) < 1e-9);
  assert.ok(maxElementDelta(effects.get("o1.3").matrix, jaw) < 1e-9);
  // The servo body is only in the group's subtree, so it stays on the frame.
  assert.ok(maxElementDelta(effects.get("o1.2.1").matrix, wrist) < 1e-9);
  assert.ok(maxElementDelta(effects.get("o1.1").matrix, wrist) < 1e-9);

  // The regression itself: the group delta premultiplied onto the jaw delta
  // counted the wrist twice and tore the horn off the jaw it is bolted to.
  const doubled = new THREE.Matrix4().multiplyMatrices(wrist, jaw);
  const pivot = new THREE.Vector3(10, 0, 0);
  assert.ok(
    pivot.clone().applyMatrix4(doubled).distanceTo(pivot.clone().applyMatrix4(jaw)) > 1,
    "the doubled pose must be a different place, or this test proves nothing"
  );
});

test("jaw-only motion moves the nested horn with the jaw", async (t) => {
  const effects = await nestedEffects(t, { jaw: 30 });
  const jaw = rotationAbout([0, 1, 0], [10, 0, 0], 30);

  assert.ok(maxElementDelta(effects.get("o1.2.2").matrix, jaw) < 1e-9);
  // Removing the horn mates would have stopped this: the horn is inside the
  // servo group, which does not turn with the jaw.
  assert.ok(maxElementDelta(effects.get("o1.2.1").matrix, new THREE.Matrix4()) < 1e-9);
});
