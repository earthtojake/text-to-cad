import assert from "node:assert/strict";
import test from "node:test";

import {
  cadWebGlRendererAttributes,
  createCadWebGlRenderer,
  fallbackCadWebGlRendererAttributes
} from "./webglRenderer.js";

test("shared CAD WebGL renderer attributes match viewer depth defaults", () => {
  assert.deepEqual(cadWebGlRendererAttributes(), {
    stencil: true,
    alpha: true,
    antialias: true,
    powerPreference: "high-performance",
    preserveDrawingBuffer: false,
    logarithmicDepthBuffer: true
  });
  assert.equal(cadWebGlRendererAttributes({ preserveDrawingBuffer: true }).preserveDrawingBuffer, true);
});

test("shared CAD WebGL renderer fallback preserves snapshot/viewer compatibility knobs", () => {
  assert.deepEqual(fallbackCadWebGlRendererAttributes(), {
    stencil: true,
    alpha: true,
    antialias: false,
    powerPreference: "default",
    preserveDrawingBuffer: false,
    logarithmicDepthBuffer: false
  });
});

function fakeCanvas(name, lost) {
  return {
    name,
    getContext: (kind) => (kind === "webgl2" ? { getExtension: (extension) => (extension === "WEBGL_lose_context" ? { loseContext: () => lost.push(name) } : null) } : null)
  };
}

test("a failed first renderer attempt is released through its canvas, and the fallback gets a canvas of its own", () => {
  const lost = [];
  const canvases = [fakeCanvas("first", lost), fakeCanvas("second", lost)];
  const attempts = [];
  class FakeRenderer {
    constructor(parameters) {
      attempts.push(parameters);
      this.canvas = parameters.canvas;
      if (attempts.length === 1) {
        throw new Error("Error creating WebGL context.");
      }
    }
  }
  const renderer = createCadWebGlRenderer({ WebGLRenderer: FakeRenderer }, {
    allowFallback: true,
    createCanvas: () => canvases.shift()
  });
  assert.deepEqual(lost, ["first"], "the first attempt's context is lost, the live renderer's is not");
  assert.equal(attempts.length, 2);
  assert.equal(renderer.canvas.name, "second");
  assert.equal(attempts[0].canvas.name, "first");
  assert.equal(attempts[0].antialias, true);
  assert.equal(attempts[1].antialias, false);
});

test("an unrecoverable first failure is rethrown after its context is released", () => {
  const lost = [];
  const failure = new Error("not a context error");
  assert.throws(
    () => createCadWebGlRenderer({
      WebGLRenderer: class { constructor() { throw failure; } }
    }, { allowFallback: true, isRecoverableError: () => false, createCanvas: () => fakeCanvas("only", lost) }),
    failure
  );
  assert.deepEqual(lost, ["only"]);
});

test("a failed attempt whose canvas never made a context releases nothing, throws nothing and asks for no WebGL 1 context", () => {
  const asked = [];
  const lost = [];
  const canvas = {
    getContext: (kind) => {
      asked.push(kind);
      return null;
    },
    loseContext: () => lost.push("lost")
  };
  const failure = new Error("Error creating WebGL context.");
  assert.throws(
    () => createCadWebGlRenderer({ WebGLRenderer: class { constructor() { throw failure; } } }, { createCanvas: () => canvas }),
    failure
  );
  assert.deepEqual(lost, []);
  assert.deepEqual(asked, ["webgl2"], "only the type three tried is asked for: asking for another could create a context just to lose it");
  // A canvas whose getContext itself throws is as harmless.
  assert.throws(
    () => createCadWebGlRenderer({ WebGLRenderer: class { constructor() { throw failure; } } }, {
      createCanvas: () => ({ getContext: () => { throw new Error("context creation blew up"); } })
    }),
    failure
  );
});
