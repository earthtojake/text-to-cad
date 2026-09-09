import assert from "node:assert/strict";
import { test } from "node:test";
import * as THREE from "three";

import {
  normalizeStepModuleDefinition,
  normalizeStepModuleParameterValues,
  resolveStepModuleFeatures,
  stepModuleRuntimeAtZeroState
} from "./stepModule.js";
import {
  normalizeStepParameterRenderValues,
  stepParameterRenderValues
} from "../../common/stepParameters.js";
import {
  createStepModuleEffectsApi,
  displayTransformForPart
} from "../../common/stepModuleEffects.js";

test("STEP modules normalize controls and defaults", () => {
  const definition = normalizeStepModuleDefinition({
    manifest: {
      schemaVersion: 1,
      parameters: {
        open: { type: "number", min: 0, max: 90, default: 120 },
        visible: { type: "boolean", default: true },
        color: { type: "color", default: "#f97316" },
        mode: { type: "select", options: ["mesh", "ghost"], default: "ghost" }
      }
    }
  });

  assert.deepEqual(definition.defaultParameterValues, {
    open: 90,
    visible: true,
    color: "#f97316",
    mode: "ghost"
  });
  assert.equal(definition.parameters[3].type, "enum");
  // A step-module definition carries POSE controls only: clips live in the
  // sidecar's animation section and never reach this normalizer.
  assert.equal(definition.animations, undefined);
  assert.deepEqual(normalizeStepModuleParameterValues(definition, {
    open: -5,
    visible: false,
    color: "orange",
    mode: "unknown"
  }), {
    open: 0,
    visible: false,
    color: "#ffffff",
    mode: "mesh"
  });
});

test("STEP module zero state uses normalized defaults", () => {
  const definition = normalizeStepModuleDefinition({
    manifest: {
      schemaVersion: 1,
      parameters: {
        drive: { type: "number", min: 0, max: 360, default: 0 },
        compression: { type: "number", min: 0, max: 1, default: 0.5 },
        tint: { type: "color", default: "#F97316" },
        visible: { type: "boolean", default: true }
      }
    }
  });

  assert.equal(stepModuleRuntimeAtZeroState(definition, {
    parameterValues: {
      drive: 0.0000004,
      compression: 0.5,
      tint: "#f97316",
      visible: true
    }
  }), true);
  assert.equal(stepModuleRuntimeAtZeroState(definition, {
    parameterValues: {
      drive: 360,
      compression: 0.5,
      tint: "#f97316",
      visible: true
    }
  }), false);
  assert.equal(stepModuleRuntimeAtZeroState(definition, {
    parameterValues: definition.defaultParameterValues
  }), true);
});

test("STEP module features resolve CAD occurrence refs to render part ids and bounds", () => {
  const definition = normalizeStepModuleDefinition({
    manifest: {
      schemaVersion: 1,
      features: {
        planet: {
          ref: "#o1.4"
        }
      }
    }
  });
  const features = resolveStepModuleFeatures(definition, {
    meshData: {
      parts: [
        {
          id: "o1.4.1",
          occurrenceId: "o1.4.1",
          bounds: { min: [20, -10, 0], max: [60, 10, 8] }
        }
      ]
    }
  });

  assert.deepEqual(features.planet.partIds, ["o1.4.1"]);
  assert.deepEqual(features.planet.center, [40, 0, 4]);
  assert.equal(features.planet.missing, false);
});

test("STEP module local feature refs resolve against the sidecar parent CAD path", () => {
  const definition = normalizeStepModuleDefinition({
    manifest: {
      schemaVersion: 1,
      features: {
        lid: {
          ref: "#o1.2"
        },
        hinges: {
          ref: "#o1.3,o1.4"
        },
        latch: {
          selectors: ["o1.5"]
        }
      }
    }
  }, {
    url: "/models/thang010146/.box.step.js?v=abc",
    cadPath: "models/thang010146/box"
  });

  assert.equal(definition.cadPath, "models/thang010146/box");
  assert.equal(definition.features[0].ref, "#o1.2");
  assert.equal(definition.features[1].ref, "#o1.3,o1.4");
  assert.equal(definition.features[2].ref, "#o1.5");
});

test("STEP module local feature refs prefer explicit relative STEP path", () => {
  const definition = normalizeStepModuleDefinition({
    manifest: {
      schemaVersion: 1,
      step: {
        path: "models/thang010146/actual-box.step"
      },
      features: {
        lid: {
          ref: "#o1.2"
        }
      }
    }
  }, {
    url: "/models/thang010146/.legacy-name.step.js?v=abc",
    cadPath: "models/thang010146/legacy-name"
  });

  assert.deepEqual(definition.step, {
    path: "models/thang010146/actual-box.step",
    cadPath: "models/thang010146/actual-box",
    explicit: true,
    inferred: false
  });
  assert.equal(definition.manifest.step.path, "models/thang010146/actual-box.step");
  assert.equal(definition.cadPath, "models/thang010146/actual-box");
  assert.equal(definition.features[0].ref, "#o1.2");
});

test("STEP module display transforms respect baked assembly part transforms", () => {
  const transform = [
    1, 0, 0, 12,
    0, 1, 0, 34,
    0, 0, 1, 56,
    0, 0, 0, 1
  ];
  const part = { id: "o1.2", transform };

  assert.equal(displayTransformForPart({ partTransformsBaked: true }, part), null);
  assert.equal(displayTransformForPart({}, part), null);
  assert.deepEqual(displayTransformForPart({ partTransformsBaked: false }, part), transform);
});

test("STEP module effects report only non-identity transforms", () => {
  const effectsByPartId = new Map();
  const transforms = [];
  const effects = createStepModuleEffectsApi(THREE, {
    meshData: {
      parts: [{ id: "arm", occurrenceId: "arm" }]
    },
    features: {
      arm: { partIds: ["arm"] }
    },
    runtime: { displayRecords: [] },
    effectsByPartId,
    onTransformEffect: (event) => transforms.push(event)
  });

  effects.transform("arm", { translate: [0, 0, 0] });
  assert.equal(transforms.length, 0);

  effects.transform("arm", { translate: [2, 0, 0] });
  assert.equal(transforms.length, 1);
  assert.deepEqual(transforms[0].partIds, ["arm"]);
  assert.ok(effectsByPartId.get("arm").matrix instanceof THREE.Matrix4);
});

test("STEP module transform detection ignores floating point pose noise", () => {
  const transforms = [];
  const effects = createStepModuleEffectsApi(THREE, {
    meshData: {
      parts: [{ id: "actuator", occurrenceId: "actuator" }]
    },
    features: {
      actuator: { partIds: ["actuator"] }
    },
    runtime: { displayRecords: [] },
    effectsByPartId: new Map(),
    onTransformEffect: (event) => transforms.push(event)
  });

  effects.transform("actuator", { translate: [0, 0, -5.278885595316751e-8] });
  assert.equal(transforms.length, 0);

  effects.transform("actuator", { translate: [0, 0, 0.001] });
  assert.equal(transforms.length, 1);
});

test("STEP render parameters normalize static values from bare and envelope forms", () => {
  const definition = normalizeStepModuleDefinition({
    manifest: {
      schemaVersion: 1,
      parameters: {
        drive: { type: "number", min: 0, max: 360, default: 0 },
        visible: { type: "boolean", default: true },
        mode: { type: "select", options: ["mesh", "ghost"], default: "mesh" }
      }
    }
  });
  const enveloped = normalizeStepParameterRenderValues(definition, {
    values: { drive: 180, visible: false, mode: "ghost" }
  });
  const bare = normalizeStepParameterRenderValues(definition, {
    drive: 180,
    visible: false,
    mode: "ghost"
  });
  assert.deepEqual(enveloped, bare);
  assert.deepEqual(stepParameterRenderValues(enveloped), {
    drive: 180,
    visible: false,
    mode: "ghost"
  });
});

test("STEP render parameters reject every id the model does not declare", () => {
  const definition = normalizeStepModuleDefinition({
    manifest: {
      schemaVersion: 1,
      parameters: {
        drive: { type: "number", min: 0, max: 360, default: 0 }
      }
    }
  });

  assert.throws(
    () => normalizeStepParameterRenderValues(definition, { missing: 1 }),
    /Unknown STEP parameter/
  );
  // No key is special-cased: anything that is not a declared DOF is simply an
  // unknown parameter, so nothing can silently render as if it were honoured.
  for (const unknown of [
    { animate: { drive: { from: 0, to: 360 } } },
    { fps: 4 },
    { durationSeconds: 2 },
    { duration: 2 },
    { loop: false }
  ]) {
    assert.throws(
      () => normalizeStepParameterRenderValues(definition, unknown),
      /Unknown STEP parameter/
    );
  }
});
