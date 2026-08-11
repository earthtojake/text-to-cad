import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";
import test from "node:test";

import { loadSource } from "./source.js";
import { renderAssetSourceScope } from "../lib/renderAssetSourceScope.js";

// Composition coverage for the scoping of render asset caches.
//
// loadSource is the only place a resolved render job meets the page-lifetime render asset caches
// (common/headlessRenderEntry.js is its sole production caller), and the caches it populates live
// in lib/stepRenderAssetClient.js. These tests drive the real composition — real loadSource, real
// client, real wiring — with only globalThis.fetch stubbed, so they fail if the scope is not
// declared, if the assertion is missing from the client the snapshot batch loads through, or if a
// collision is swallowed on the way out. Unit-level coverage of the assertion itself lives in
// lib/stepRenderAssetClient.test.js and lib/renderAssetClient.test.js.
//
// The stubbed asset body is deliberately not a decodable GLB: these jobs supply meshData, so the
// property under test is which source owns the cached bytes, not topology decoding (covered in
// lib/stepRenderAssetClient.test.js). Loading the mesh itself needs the three runtime and is out
// of scope for a unit test; it reads the same byte cache asserted here.

function renderAssetUrl() {
  return `/__render_asset/part.glb?v=${Date.now().toString(16)}${Math.random().toString(16).slice(2)}`;
}

function stepJob({ inputPath, rootPath, glbUrl }) {
  return {
    kind: "step",
    meshData: meshData(),
    resolved: {
      kind: "step",
      ...(inputPath === undefined ? {} : { inputPath }),
      ...(rootPath === undefined ? {} : { rootPath }),
      glbUrl
    }
  };
}

function stubAssetFetch(t, url) {
  const originalFetch = globalThis.fetch;
  const state = { fetchCount: 0 };
  globalThis.fetch = async (requestUrl) => {
    assert.equal(String(requestUrl), url);
    state.fetchCount += 1;
    return new Response(new Uint8Array([state.fetchCount]), { status: 200 });
  };
  t.after(() => {
    globalThis.fetch = originalFetch;
  });
  return state;
}

function meshData() {
  return {
    vertices: new Float32Array([
      0, 0, 0,
      1, 0, 0,
      0, 1, 0
    ]),
    indices: new Uint32Array([0, 1, 2]),
    bounds: {
      min: [0, 0, 0],
      max: [1, 1, 0]
    },
    parts: []
  };
}

async function withTempModule(callback) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "render-source-test-"));
  try {
    const modulePath = path.join(root, "part.step.mjs");
    fs.writeFileSync(modulePath, `
      export default {
        manifest: {
          schemaVersion: 1,
          parameters: {
            drive: { type: "number", min: 0, max: 360, default: 0 }
          }
        }
      };
    `);
    return await callback(pathToFileURL(modulePath).href);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
}

test("loadSource rejects the removed shared params field", async () => {
  await assert.rejects(
    () => loadSource({
      kind: "step",
      meshData: meshData(),
      params: { drive: 90 }
    }),
    /use stepParameters/
  );
});

test("loadSource rejects STEP parameter options for non-STEP sources", async () => {
  await assert.rejects(
    () => loadSource({
      kind: "glb",
      meshData: meshData(),
      stepParameters: { drive: 90 }
    }),
    /stepParameters is supported only for STEP\/STP sources/
  );
  await assert.rejects(
    () => loadSource({
      kind: "glb",
      meshData: meshData(),
      stepParameterUrl: "file:///tmp/part.step.mjs"
    }),
    /stepParameterUrl is supported only for STEP\/STP sources/
  );
});

test("loadSource refuses a render asset cached for a different job source", async (t) => {
  const glbUrl = renderAssetUrl();
  const fetches = stubAssetFetch(t, glbUrl);

  const first = await loadSource(stepJob({
    inputPath: "/models/first/part.step",
    rootPath: "/models/first",
    glbUrl
  }));
  assert.equal(first.kind, "step");
  assert.equal(fetches.fetchCount, 1);

  await assert.rejects(
    () => loadSource(stepJob({
      inputPath: "/models/second/part.step",
      rootPath: "/models/second",
      glbUrl
    })),
    /cached for source \/models\/first\/part\.step but was requested for \/models\/second\/part\.step/
  );
  assert.equal(fetches.fetchCount, 1);
});

test("loadSource refuses a collision between two sources under one render root", async (t) => {
  // Same directory, so the server would route this URL identically for both jobs: the scope has to
  // be the source file, not its parent, or a future URL-minting regression inside one directory
  // stays invisible.
  const glbUrl = renderAssetUrl();
  const fetches = stubAssetFetch(t, glbUrl);

  await loadSource(stepJob({ inputPath: "/models/a.step", rootPath: "/models", glbUrl }));
  await assert.rejects(
    () => loadSource(stepJob({ inputPath: "/models/b.step", rootPath: "/models", glbUrl })),
    /refusing to reuse it/
  );
  assert.equal(fetches.fetchCount, 1);
});

test("loadSource shares one render asset fetch across jobs against the same file", async (t) => {
  const glbUrl = renderAssetUrl();
  const fetches = stubAssetFetch(t, glbUrl);
  const job = () => stepJob({
    inputPath: "/models/only/part.step",
    rootPath: "/models/only",
    glbUrl
  });

  const results = [await loadSource(job()), await loadSource(job()), await loadSource(job())];

  assert.equal(results.length, 3);
  for (const result of results) {
    assert.equal(result.kind, "step");
  }
  assert.equal(fetches.fetchCount, 1);
});

test("loadSource still serves single-source callers that pass no resolved job", async (t) => {
  // The shape documented in packages/cadjs/docs/render-pipeline.md for interactive viewer/docs use,
  // and the one docs/src/components/hero-step-render.tsx actually calls: no resolved packet, one
  // source per page. It must keep working unscoped — requiring a source path here would break a
  // documented public contract and the docs hero renderer.
  const glbUrl = renderAssetUrl();
  const fetches = stubAssetFetch(t, glbUrl);

  const source = await loadSource({
    kind: "step",
    meshData: meshData(),
    glbUrl,
    cadPath: "models/part.step"
  });

  assert.equal(source.kind, "step");
  assert.equal(source.glbUrl, glbUrl);
  assert.equal(renderAssetSourceScope(), "");
  assert.equal(fetches.fetchCount, 1);

  // Repeating it reuses the cached asset, exactly as before.
  await loadSource({ kind: "step", meshData: meshData(), glbUrl, cadPath: "models/part.step" });
  assert.equal(fetches.fetchCount, 1);
});

test("loadSource refuses to fetch a render asset for a resolved job that does not name its source", async (t) => {
  const glbUrl = renderAssetUrl();
  const fetches = stubAssetFetch(t, glbUrl);

  await assert.rejects(
    () => loadSource(stepJob({ rootPath: "/models/first", glbUrl })),
    /require resolved\.inputPath to scope the render asset cache/
  );
  // A blank or non-string source is not a source: it must fail closed rather than coerce into the
  // same bucket as the interactive viewer's unscoped default.
  for (const inputPath of ["", "   ", 0, false, {}, ["/models/first/part.step"]]) {
    await assert.rejects(
      () => loadSource(stepJob({ inputPath, rootPath: "/models/first", glbUrl })),
      /require resolved\.inputPath to scope the render asset cache/
    );
  }
  assert.equal(fetches.fetchCount, 0);
});

test("loadSource leaves no source scope behind", async (t) => {
  const glbUrl = renderAssetUrl();
  stubAssetFetch(t, glbUrl);
  assert.equal(renderAssetSourceScope(), "");

  await loadSource(stepJob({
    inputPath: "/models/kept/part.step",
    rootPath: "/models/kept",
    glbUrl
  }));
  assert.equal(renderAssetSourceScope(), "");

  await assert.rejects(() => loadSource(stepJob({ glbUrl })));
  assert.equal(renderAssetSourceScope(), "");
});

test("loadSource accepts STEP parameter sidecars for STEP sources", async () => {
  await withTempModule(async (stepParameterUrl) => {
    const source = await loadSource({
      kind: "step",
      meshData: meshData(),
      cadPath: "part.step",
      stepParameterUrl,
      stepParameters: { drive: 90 }
    });

    assert.equal(source.kind, "step");
    assert.equal(source.stepParameterSource.renderParameters.values.drive, 90);
    assert.equal(source.stepParameterSource.cadPath, "part.step");
  });
});

function binaryStlTriangle() {
  // 80-byte header + uint32 triangle count + one 50-byte triangle record.
  const buffer = new ArrayBuffer(84 + 50);
  const view = new DataView(buffer);
  view.setUint32(80, 1, true); // triangle count
  const floats = [
    0, 0, 1, // normal
    0, 0, 0, // v1
    1, 0, 0, // v2
    0, 1, 0 // v3
  ];
  let offset = 84;
  for (const value of floats) {
    view.setFloat32(offset, value, true);
    offset += 4;
  }
  // trailing uint16 attribute byte count left as 0
  return buffer;
}

test("loadSource builds mesh data from an STL url", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response(binaryStlTriangle(), { status: 200 });
  try {
    const source = await loadSource("/models/part.stl");
    assert.equal(source.kind, "stl");
    assert.equal(source.stepParameterSource, null);
    assert.equal(source.selectorRuntime, null);
    assert.equal(source.displayEdgeRuntime, null);
    assert.ok(source.meshData.vertices.length >= 9);
    assert.ok(source.meshData.indices.length >= 3);
    assert.equal(source.meshData.sourceFormat, "stl");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("loadSource fetches a direct mesh exactly once (no STEP sidecar loads)", async () => {
  const originalFetch = globalThis.fetch;
  const fetchedUrls = [];
  globalThis.fetch = async (url) => {
    fetchedUrls.push(String(url));
    return new Response(binaryStlTriangle(), { status: 200 });
  };
  try {
    const source = await loadSource("/models/part.stl");
    // Selector/display-edge runtimes are STEP topology sidecars; loading them for a
    // mesh kind re-downloads the binary just to fail the GLB parse. One fetch total.
    assert.deepEqual(fetchedUrls, ["/models/part.stl"]);
    assert.equal(source.selectorRuntime, null);
    assert.equal(source.displayEdgeRuntime, null);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("loadSource surfaces STL fetch failures", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response("nope", { status: 404 });
  try {
    await assert.rejects(() => loadSource("/models/missing.stl"), /Failed to load STL source: HTTP 404/);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("loadSource routes 3MF sources through the non-step return path", async () => {
  const source = await loadSource({ kind: "3mf", meshData: meshData() });
  assert.equal(source.kind, "3mf");
  assert.equal(source.stepParameterSource, null);
  assert.equal(source.selectorRuntime, null);
  assert.equal(source.displayEdgeRuntime, null);
});
