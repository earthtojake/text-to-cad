import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  PACKAGE_ROOT,
  RENDER_HTML_PATH,
  SNAPSHOT_ORIGIN,
  SnapshotError,
  chromiumLaunchOptions,
  loadJobFromOptions,
  parseSnapshotArgs,
  resolveRenderJobPacket,
  resolveSnapshotRouteFile,
  timestampOutputPath,
} from "./snapshot.mjs";

const ttyStdin = { isTTY: true };

function withTempImplicitModel(callback) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "implicitjs-snapshot-"));
  try {
    const models = path.join(root, "models", "implicit-cad");
    fs.mkdirSync(models, { recursive: true });
    fs.writeFileSync(
      path.join(models, "orb.implicit.js"),
      "export default {glsl: 'float sdf(vec3 p) { return length(p) - 1.0; }'};\n",
      "utf8"
    );
    return callback({ root, models });
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
}

test("shortcut job shape is built by the JavaScript snapshot CLI", async () => {
  const options = parseSnapshotArgs([
    "--input",
    "models/implicit-cad/orb.implicit.js",
    "--output",
    "tmp/orb.png",
    "--camera",
    "front",
    "--width",
    "640",
    "--height",
    "480",
    "--params",
    "{\"radius\":24}",
    "--appearance",
    "workbench",
    "--graphics",
    "{\"detail\":2,\"resolutionScale\":3}",
    "--size-profile",
    "simple",
  ]);

  const job = await loadJobFromOptions(options, { stdin: ttyStdin, cwd: process.cwd() });

  assert.equal(job.input, "models/implicit-cad/orb.implicit.js");
  assert.equal(job.mode, "view");
  assert.equal(job.outputs[0].path, "tmp/orb.png");
  assert.equal(job.outputs[0].camera, "front");
  assert.equal(job.outputs[0].width, 640);
  assert.equal(job.outputs[0].height, 480);
  assert.equal(job.appearance, "workbench");
  assert.deepEqual(job.graphics, { detail: 2, resolutionScale: 3 });
  assert.deepEqual(job.render, { sizeProfile: "simple" });
  assert.deepEqual(job.implicitParameters, { radius: 24 });
});

test("shortcut accepts JSON camera objects", async () => {
  const options = parseSnapshotArgs([
    "--input",
    "models/implicit-cad/orb.implicit.js",
    "--output",
    "tmp/orb.png",
    "--camera",
    "{\"position\":[4,-5,3],\"target\":[0,0,0],\"up\":[0,0,1],\"zoom\":1.4}",
  ]);

  const job = await loadJobFromOptions(options, { stdin: ttyStdin, cwd: process.cwd() });

  assert.deepEqual(job.outputs[0].camera, {
    position: [4, -5, 3],
    target: [0, 0, 0],
    up: [0, 0, 1],
    zoom: 1.4,
  });
});

test("GIF shortcut defaults to orbit mode", async () => {
  const options = parseSnapshotArgs([
    "--input",
    "models/implicit-cad/orb.implicit.js",
    "--output",
    "tmp/orb.gif",
  ]);

  const job = await loadJobFromOptions(options, { stdin: ttyStdin, cwd: process.cwd() });

  assert.equal(job.mode, "orbit");
  assert.equal(job.outputs[0].path, "tmp/orb.gif");
});

test("render job derives asset root from input parent", () => withTempImplicitModel(({ root, models }) => {
  const packet = resolveRenderJobPacket({
    input: "models/implicit-cad/orb.implicit.js",
    outputs: [{ path: "tmp/orb.png", camera: "iso" }],
  }, {
    cwd: root,
    timestamp: "20260527T163012Z",
  });

  const job = packet.jobs[0];
  assert.equal(packet.single, true);
  assert.equal(job.resolved.kind, "implicit");
  assert.equal(job.resolved.rootPath, models);
  assert.match(job.resolved.inputUrl, /^\/__render_asset\/orb\.implicit\.js\?v=/u);
  assert.equal(job.appearance, "workbench");
  assert.deepEqual(job.render, {});
  assert.deepEqual(job.graphics, {});
  assert.equal(job.outputs[0].width, 1600);
  assert.equal(job.outputs[0].height, 1200);
  assert.equal(path.basename(job.outputs[0].path), "orb_20260527T163012Z.png");
}));

test("render job packet supports multi-output review snapshots", () => withTempImplicitModel(({ root }) => {
  const packet = resolveRenderJobPacket({
    input: "models/implicit-cad/orb.implicit.js",
    render: { frameMargin: 1.55 },
    outputs: [
      { path: "tmp/orb-iso.png", camera: "iso" },
      { path: "tmp/orb-front.png", camera: "front", width: 900, height: 700 },
      { path: "tmp/orb-top.png", camera: "top" },
    ],
  }, {
    cwd: root,
    timestamp: "20260527T163012Z",
  });

  const job = packet.jobs[0];
  assert.equal(packet.single, true);
  assert.equal(job.outputs.length, 3);
  assert.equal(job.render.frameMargin, 1.55);
  assert.equal(job.outputs[0].camera, "iso");
  assert.equal(job.outputs[1].camera, "front");
  assert.equal(job.outputs[1].width, 900);
  assert.equal(job.outputs[1].height, 700);
  assert.equal(job.outputs[2].camera, "top");
  assert.deepEqual(
    job.outputs.map((output) => path.basename(output.path)),
    [
      "orb-iso_20260527T163012Z.png",
      "orb-front_20260527T163012Z.png",
      "orb-top_20260527T163012Z.png",
    ]
  );
}));

test("render job packet accepts arrays with one shared timestamp", () => withTempImplicitModel(({ root }) => {
  const packet = resolveRenderJobPacket([
    { input: "models/implicit-cad/orb.implicit.js", outputs: [{ path: "tmp/a.png" }] },
    { input: "models/implicit-cad/orb.implicit.js", outputs: [{ path: "tmp/b.png" }] },
  ], {
    cwd: root,
    timestamp: "20260527T163012Z",
  });

  assert.equal(packet.single, false);
  assert.equal(packet.jobs.length, 2);
  assert.equal(path.basename(packet.jobs[0].outputs[0].path), "a_20260527T163012Z.png");
  assert.equal(path.basename(packet.jobs[1].outputs[0].path), "b_20260527T163012Z.png");
  assert.equal(packet.jobs[0].resolved.inputUrl, packet.jobs[1].resolved.inputUrl);
}));

test("render job accepts animation mode", () => withTempImplicitModel(({ root }) => {
  const packet = resolveRenderJobPacket({
    input: "models/implicit-cad/orb.implicit.js",
    mode: "animate",
    outputs: [{ path: "tmp/orb.gif" }],
  }, { cwd: root });

  assert.equal(packet.jobs[0].mode, "animate");
}));

test("non implicit input files are rejected", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "implicitjs-snapshot-"));
  try {
    const models = path.join(root, "models");
    fs.mkdirSync(models, { recursive: true });
    fs.writeFileSync(path.join(models, "part.js"), "export default {};\n", "utf8");

    assert.throws(
      () => resolveRenderJobPacket({ input: "models/part.js", outputs: [{ path: "tmp/part.png" }] }, { cwd: root }),
      /only \.implicit\.js and \.implicit\.mjs/u
    );
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test("legacy top-level theme and params fields are rejected", () => withTempImplicitModel(({ root }) => {
  assert.throws(
    () => resolveRenderJobPacket({
      input: "models/implicit-cad/orb.implicit.js",
      theme: "dark",
      outputs: [{ path: "tmp/orb.png" }],
    }, { cwd: root }),
    /use appearance/u
  );
  assert.throws(
    () => resolveRenderJobPacket({
      input: "models/implicit-cad/orb.implicit.js",
      params: {},
      outputs: [{ path: "tmp/orb.png" }],
    }, { cwd: root }),
    /use implicitParameters/u
  );
}));

test("timestamp output path preserves extension", () => {
  assert.equal(
    timestampOutputPath("snapshots/review.png", "20260527T163012Z"),
    "snapshots/review_20260527T163012Z.png"
  );
});

test("snapshot routes are package-owned and self-contained", () => {
  assert.equal(resolveSnapshotRouteFile(`${SNAPSHOT_ORIGIN}/render.html`), RENDER_HTML_PATH);
  assert.equal(
    resolveSnapshotRouteFile(`${SNAPSHOT_ORIGIN}/src/common/implicitHeadlessRenderEntry.js`),
    path.join(PACKAGE_ROOT, "src", "common", "implicitHeadlessRenderEntry.js")
  );
  assert.equal(
    resolveSnapshotRouteFile(`${SNAPSHOT_ORIGIN}/src/common/implicitHeadlessRenderEntry.js?v=test`),
    path.join(PACKAGE_ROOT, "src", "common", "implicitHeadlessRenderEntry.js")
  );
  assert.throws(
    () => resolveSnapshotRouteFile(`${SNAPSHOT_ORIGIN}/__render_asset/orb.implicit.js`),
    SnapshotError
  );
});

test("snapshot renderer does not force Chromium single-process mode", () => {
  assert.notEqual(chromiumLaunchOptions().args?.includes("--single-process"), true);
});
