// Structural render-cost benchmark for a component-GLB package.
//
// Measures the metrics that matter for large-package rendering, at the JS/meshData
// layer so it runs deterministically in Node with no GPU/browser:
//
//   - occurrences vs unique components (the dedup the render layer keeps)
//   - composed top-level vertices vs unique-component vertices. The shared-geometry
//     composer holds ONE component-local copy per unique component, so these must
//     stay equal (1.0x). This is a regression guard: if a future change re-bakes
//     per-occurrence vertices, the ratio jumps back toward occurrence count.
//   - composed "parts" == THREE.Mesh count == draw calls (one per occurrence; the
//     shared-geometry path reuses one cached BufferGeometry across a cid's meshes)
//   - buildComposedPackageMeshData wall time (the main-thread compose stall)
//   - retained buffer bytes across the composed top-level arrays
//
// Not covered (needs a real WebGL/browser session): GPU upload time, frame
// rate, main-thread stall as felt in the app. Those are validated per-phase
// with the viewer itself; this harness is the fast, CI-able structural gate.
//
// Usage:
//   node packages/cadjs/bench/composePackageBench.mjs <package-dir> [--json]
// where <package-dir> is a __cadgen__/models/<entry> directory (has
// assembly.json + components/). Defaults to the warmed falcon_heavy package.

import { readFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

import { buildMeshDataFromGlbBuffer } from "../src/lib/render/glbMeshData.js";
import { buildComposedPackageMeshData } from "../src/lib/assembly/meshData.js";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(HERE, "../../..");
const DEFAULT_PACKAGE = path.join(
  REPO_ROOT,
  "models/renders/falcon_heavy/__cadgen__/models/falcon_heavy.step.py",
);

function sumPartBytes(meshData) {
  const parts = Array.isArray(meshData?.parts) ? meshData.parts : [];
  let bytes = 0;
  for (const key of ["vertices", "normals", "colors", "barycentric", "edgeClasses", "indices"]) {
    const buffer = meshData?.[key];
    if (buffer && typeof buffer.byteLength === "number") {
      bytes += buffer.byteLength;
    }
  }
  // Composed output keeps one set of parallel arrays plus per-part index ranges;
  // count the top-level arrays (the retained composed copy).
  return { bytes, partCount: parts.length };
}

async function main() {
  const args = process.argv.slice(2);
  const asJson = args.includes("--json");
  const packageDir = path.resolve(args.find((a) => !a.startsWith("--")) || DEFAULT_PACKAGE);

  const descriptor = JSON.parse(
    await readFile(path.join(packageDir, "assembly.json"), "utf8"),
  );
  const componentEntries = Object.entries(descriptor.components || {});

  // Parse each unique component GLB once (mirrors the viewer's per-cid load).
  const componentMeshDataByCid = {};
  let uniqueVertices = 0;
  let uniqueTriangles = 0;
  for (const [cid, component] of componentEntries) {
    const buffer = await readFile(path.join(packageDir, component.glb));
    const meshData = await buildMeshDataFromGlbBuffer(
      buffer.buffer.slice(buffer.byteOffset, buffer.byteOffset + buffer.byteLength),
    );
    componentMeshDataByCid[cid] = meshData;
    for (const part of meshData.parts || []) {
      uniqueVertices += Number(part.vertexCount || 0);
      uniqueTriangles += Number(part.triangleCount || 0);
    }
  }

  const started = process.hrtime.bigint();
  const composed = buildComposedPackageMeshData(descriptor, componentMeshDataByCid);
  const composeMs = Number(process.hrtime.bigint() - started) / 1e6;

  const composedVertices = (composed.vertices?.length || 0) / 3;
  const composedTriangles = (composed.indices?.length || 0) / 3;
  const { bytes, partCount } = sumPartBytes(composed);

  const report = {
    package: path.relative(REPO_ROOT, packageDir),
    occurrences: (descriptor.occurrences || []).length,
    uniqueComponents: componentEntries.length,
    drawCalls: partCount, // one THREE.Mesh per occurrence (over shared, cached geometry)
    uniqueVertices, // each unique component's geometry, uploaded once
    composedVertices, // shared geometry: top-level holds one copy per unique component
    // Must stay 1.0 on the shared-geometry path; > 1.0 means per-occurrence baking crept back.
    vertexInflation: uniqueVertices ? Number((composedVertices / uniqueVertices).toFixed(2)) : null,
    uniqueTriangles,
    composedTriangles,
    composedBufferMiB: Number((bytes / (1024 * 1024)).toFixed(1)),
    composeMs: Number(composeMs.toFixed(1)),
  };

  if (asJson) {
    process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
    return;
  }
  process.stdout.write(`package            ${report.package}\n`);
  process.stdout.write(`occurrences        ${report.occurrences}\n`);
  process.stdout.write(`unique components  ${report.uniqueComponents}\n`);
  process.stdout.write(`draw calls         ${report.drawCalls}\n`);
  process.stdout.write(`unique vertices    ${report.uniqueVertices.toLocaleString()}  (uploaded once per component)\n`);
  process.stdout.write(`composed vertices  ${report.composedVertices.toLocaleString()} (${report.vertexInflation}x — shared geometry keeps this at 1.0x; >1 = baking regressed)\n`);
  process.stdout.write(`composed triangles ${report.composedTriangles.toLocaleString()}\n`);
  process.stdout.write(`composed buffers   ${report.composedBufferMiB} MiB\n`);
  process.stdout.write(`compose time       ${report.composeMs} ms\n`);
}

main().catch((error) => {
  process.stderr.write(`${error?.stack || error}\n`);
  process.exitCode = 1;
});
