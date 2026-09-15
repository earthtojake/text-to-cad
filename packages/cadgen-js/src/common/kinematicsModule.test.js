import assert from "node:assert/strict";
import { test } from "node:test";

import {
  SOURCE_SIDECAR_SCHEMA_VERSION,
  loadKinematicsModuleDefinition,
  previewKinematicsModuleDefinition
} from "./kinematicsModule.js";

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
