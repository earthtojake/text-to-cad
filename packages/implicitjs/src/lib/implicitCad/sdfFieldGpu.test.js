// THE NON-GATING GPU TIER: does every model's shader still COMPILE?
//
// `sdfField.test.js` is the gate, and it is browser-free by necessity -- CI never runs
// `playwright install`, and a gate that skips is not a gate. That leaves it with one stated
// blind spot it cannot close from Node: GLSL is typed and JavaScript is not, so a rewrite that
// turns `i == 0` into `i == 0.0` -- one of the two known normalizer bugs -- changes
// NOTHING a JS evaluator can
// observe (`0` and `0.0` are the same Number) while making the shader fail to compile:
//
//   ERROR: '==' : wrong operand types - no operation '==' exists that takes a left-hand
//   operand of type 'mediump int' and a right operand of type 'const float'
//
// The model then renders as nothing at all. Only a real GL context can see that, so this file
// asks a real one, and SKIPS -- loudly, with the reason -- when there is no browser. It is
// deliberately compile-only: linking, drawing, and comparing pixels or float readback belong
// to the nightly visual pass (§10.3), and none of them add anything to the type question.
//
// Only the FRAGMENT shader is checked. The vertex shader is three.js's -- it leans on the
// `position`/`uv` attribute declarations three.js prepends at material-compile time, so
// compiling it bare says something about three.js rather than about a model.
//
// OPT-IN, by `IMPLICIT_GPU_SHADER_CHECK=1`, for two reasons rather than one. CI has no browser,
// so it would skip there anyway -- but a developer machine DOES have one, and a test whose
// result depends on whether a browser happens to be installed is not a test, it is a coin
// flip. Off by default, `npm test` behaves identically everywhere.
//
//   IMPLICIT_GPU_SHADER_CHECK=1 npm --prefix packages/implicitjs test
//   (first time: npx playwright install chromium)

import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { loadImplicitCadModelFromPath } from "./export.js";
import { implicitCadFragmentShader } from "./render.js";

const MODELS_DIR = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../../../..",
  "models/implicits"
);

/** The models whose shader is known NOT to compile, and why. Kept in step with
 *  `MODELS_THAT_DO_NOT_COMPILE` in sdfField.test.js, whose header carries the full write-up and
 *  the fix. This list must only ever SHRINK. */
const KNOWN_UNCOMPILABLE = new Map([
  [
    "catenoid-ring-bridge.implicit.js",
    "calls cosh, which is GLSL ES 3.00 and does not exist in the ES 1.00 shader -- see the "
    + "comment block in sdfField.test.js",
  ],
]);

async function openBrowser() {
  let chromium;
  try {
    ({ chromium } = await import("playwright"));
  } catch (error) {
    return { skip: `playwright is not installed (${error instanceof Error ? error.message : error})` };
  }
  try {
    const browser = await chromium.launch({ headless: true, timeout: 60000 });
    return { browser };
  } catch (error) {
    return {
      skip: "no chromium executable -- run `npx playwright install chromium` to include the GPU "
        + `tier (${error instanceof Error ? error.message.split("\n")[0] : error})`,
    };
  }
}

test("every model's fragment shader compiles in a real GL context", async (t) => {
  if (process.env.IMPLICIT_GPU_SHADER_CHECK !== "1") {
    t.skip("GPU shader-compile tier is opt-in -- rerun with IMPLICIT_GPU_SHADER_CHECK=1");
    return;
  }
  const { browser, skip } = await openBrowser();
  if (skip) {
    // Non-gating by design: CI has no browser, and this tier exists to be run locally and
    // nightly. The reason is printed rather than swallowed so a silent skip is never mistaken
    // for a pass.
    t.skip(`GPU shader-compile tier skipped -- ${skip}`);
    return;
  }

  try {
    const page = await browser.newPage();
    const shaders = fs.readdirSync(MODELS_DIR)
      .filter((name) => name.endsWith(".implicit.js"))
      .sort();
    assert.ok(shaders.length >= 43, `expected the implicit corpus at ${MODELS_DIR}`);

    const sources = [];
    for (const file of shaders) {
      const model = await loadImplicitCadModelFromPath(path.join(MODELS_DIR, file));
      sources.push({ file, fragment: implicitCadFragmentShader(model) });
    }

    const results = await page.evaluate((programs) => {
      const canvas = document.createElement("canvas");
      const gl = canvas.getContext("webgl") || canvas.getContext("experimental-webgl");
      if (!gl) {
        return { unavailable: "the page has no WebGL context" };
      }
      const compile = (type, source) => {
        const shader = gl.createShader(type);
        gl.shaderSource(shader, source);
        gl.compileShader(shader);
        const ok = gl.getShaderParameter(shader, gl.COMPILE_STATUS);
        const log = ok ? "" : String(gl.getShaderInfoLog(shader) || "").replace(/\0/g, "").trim();
        gl.deleteShader(shader);
        return { ok, log };
      };
      return {
        renderer: String(gl.getParameter(gl.RENDERER)),
        compiled: programs.map(({ file, fragment }) => ({
          file,
          fragment: compile(gl.FRAGMENT_SHADER, fragment),
        })),
      };
    }, sources);

    if (results.unavailable) {
      t.skip(`GPU shader-compile tier skipped -- ${results.unavailable}`);
      return;
    }

    for (const result of results.compiled) {
      await t.test(result.file, () => {
        const known = KNOWN_UNCOMPILABLE.get(result.file);
        if (known) {
          // Pinned, not excused: assert the break is STILL THERE, so repairing the shader turns
          // this red and tells whoever did it to take the model off both lists.
          assert.ok(
            !result.fragment.ok,
            `${result.file} now compiles on ${results.renderer}. If the ES 1.00 polyfills landed, `
            + `remove it from KNOWN_UNCOMPILABLE here and from MODELS_THAT_DO_NOT_COMPILE in `
            + `sdfField.test.js. Recorded reason: ${known}`
          );
          return;
        }
        assert.ok(
          result.fragment.ok,
          `${result.file}: the fragment shader the GPU raymarches did not compile on `
          + `${results.renderer}, so this model renders as nothing. The CPU evaluator cannot see `
          + `this class of break -- see the header of sdfField.test.js.\n${result.fragment.log}`
        );
      });
    }
  } finally {
    await browser.close();
  }
});
