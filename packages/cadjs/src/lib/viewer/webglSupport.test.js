import assert from "node:assert/strict";
import test from "node:test";

import {
  buildRuntimeInitializationAlert,
  isSoftwareWebGlRenderer,
  isWebGlContextCreationError,
  runtimeErrorMessage
} from "./webglSupport.js";

function rendererWithName(name, exposeDebugInfo = true) {
  const debugInfo = exposeDebugInfo ? { UNMASKED_RENDERER_WEBGL: 1 } : null;
  return {
    getContext() {
      return {
        RENDERER: 2,
        getExtension() {
          return debugInfo;
        },
        getParameter() {
          return name;
        }
      };
    }
  };
}

test("isWebGlContextCreationError recognizes Three.js context creation failures", () => {
  assert.equal(isWebGlContextCreationError(new Error("Error creating WebGL context.")), true);
  assert.equal(
    isWebGlContextCreationError("THREE.WebGLRenderer: A WebGL context could not be created."),
    true
  );
  assert.equal(isWebGlContextCreationError(new Error("Failed to load render mesh")), false);
});

test("isSoftwareWebGlRenderer recognizes common software rasterizers", () => {
  assert.equal(isSoftwareWebGlRenderer(rendererWithName("ANGLE (Google, SwiftShader Device)")), true);
  assert.equal(isSoftwareWebGlRenderer(rendererWithName("llvmpipe (LLVM 18.1.3)", false)), true);
  assert.equal(isSoftwareWebGlRenderer(rendererWithName("AMD Radeon Graphics (radeonsi)")), false);
  assert.equal(isSoftwareWebGlRenderer(null), false);
});

test("buildRuntimeInitializationAlert reports WebGL as a blocking browser capability issue", () => {
  const alert = buildRuntimeInitializationAlert(new Error("Error creating WebGL context."));

  assert.equal(alert.blocking, true);
  assert.equal(alert.summary, "WebGL unavailable");
  assert.match(alert.message, /browser WebGL/);
  assert.match(alert.resolution, /chrome:\/\/gpu/);
});

test("buildRuntimeInitializationAlert falls back to a generic startup alert", () => {
  const alert = buildRuntimeInitializationAlert(new Error("Unexpected renderer failure"));

  assert.equal(alert.blocking, true);
  assert.equal(alert.summary, "CAD Viewer startup failed");
  assert.equal(alert.message, "Unexpected renderer failure");
});

test("runtimeErrorMessage normalizes unknown thrown values", () => {
  assert.equal(runtimeErrorMessage(null), "");
  assert.equal(runtimeErrorMessage("plain failure"), "plain failure");
  assert.equal(runtimeErrorMessage(new Error("boom")), "boom");
});
