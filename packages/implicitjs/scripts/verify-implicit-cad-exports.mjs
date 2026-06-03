#!/usr/bin/env node
import fs from "node:fs/promises";
import path from "node:path";

import { loadImplicitCadModelFromPath } from "../src/lib/implicitCad/export.js";
import { meshToFormat } from "../src/lib/implicitCad/exporters.js";
import { analyzeImplicitMeshQuality } from "../src/lib/implicitCad/meshQuality.js";
import { meshImplicitCadModel } from "../src/lib/implicitCad/mesh.js";

const FORMATS = Object.freeze(["glb", "stl", "3mf"]);
const DEFAULT_ROOT = process.cwd();

function usage() {
  return `Usage:
  node scripts/verify-implicit-cad-exports.mjs
  node scripts/verify-implicit-cad-exports.mjs --root examples --resolution 96 --formats glb,stl,3mf

Options:
  --root           Directory containing .implicit.js files. Default: current directory.
  --file, --input  Specific .implicit.js file to verify. May be repeated.
  --resolution     Longest-axis sampling resolution. Default: 96.
  --max-cells      Safety cap for grid cells. Default: exporter default.
  --formats        Comma-separated export formats. Default: glb,stl,3mf.
  --orientation-samples
                   Maximum sampled SDF orientation checks per mesh. Default: 1000.
  --write-dir      Optional directory for generated export files.
  --json           Print machine-readable result JSON.
  --help, -h       Show this help.
`;
}

function finiteNumber(value, fallback = 0) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
}

function parseArgs(argv) {
  const options = {
    root: DEFAULT_ROOT,
    files: [],
    resolution: 96,
    maxCells: undefined,
    formats: [...FORMATS],
    orientationSamples: 1000,
    writeDir: "",
    json: false,
    help: false,
  };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    const readValue = () => {
      index += 1;
      if (index >= argv.length) {
        throw new Error(`${arg} requires a value`);
      }
      return argv[index];
    };
    switch (arg) {
      case "--root":
        options.root = path.resolve(readValue());
        break;
      case "--file":
      case "--input":
        options.files.push(path.resolve(readValue()));
        break;
      case "--resolution":
        options.resolution = Number(readValue());
        break;
      case "--max-cells":
        options.maxCells = Number(readValue());
        break;
      case "--formats":
        options.formats = readValue()
          .split(",")
          .map((format) => format.trim().toLowerCase())
          .filter(Boolean);
        break;
      case "--orientation-samples":
        options.orientationSamples = Number(readValue());
        break;
      case "--write-dir":
        options.writeDir = path.resolve(readValue());
        break;
      case "--json":
        options.json = true;
        break;
      case "--help":
      case "-h":
        options.help = true;
        break;
      default:
        throw new Error(`Unknown argument: ${arg}`);
    }
  }
  if (!options.formats.length || options.formats.some((format) => !FORMATS.includes(format))) {
    throw new Error(`--formats must contain one or more of: ${FORMATS.join(", ")}`);
  }
  return options;
}

async function listImplicitFiles(root) {
  const entries = await fs.readdir(root, { withFileTypes: true });
  return entries
    .filter((entry) => entry.isFile() && /\.implicit\.(?:js|mjs)$/i.test(entry.name))
    .map((entry) => path.join(root, entry.name))
    .sort((left, right) => left.localeCompare(right));
}

function parseGlbJson(buffer) {
  if (buffer.length < 28 || buffer.toString("utf-8", 0, 4) !== "glTF") {
    throw new Error("GLB magic header is missing");
  }
  const version = buffer.readUInt32LE(4);
  const totalLength = buffer.readUInt32LE(8);
  const jsonLength = buffer.readUInt32LE(12);
  const jsonType = buffer.readUInt32LE(16);
  if (version !== 2) {
    throw new Error(`Unsupported GLB version: ${version}`);
  }
  if (totalLength !== buffer.length) {
    throw new Error(`GLB length mismatch: header=${totalLength} actual=${buffer.length}`);
  }
  if (jsonType !== 0x4e4f534a) {
    throw new Error("GLB first chunk is not JSON");
  }
  return JSON.parse(buffer.toString("utf-8", 20, 20 + jsonLength).trim());
}

function validateFormatBuffer(format, buffer, mesh) {
  const triangleCount = mesh.triangleCount;
  if (!Buffer.isBuffer(buffer) || buffer.length <= 100) {
    return [`${format} buffer is unexpectedly small`];
  }
  if (format === "stl") {
    const expectedLength = 84 + triangleCount * 50;
    const declaredTriangles = buffer.readUInt32LE(80);
    return [
      declaredTriangles === triangleCount ? "" : `STL triangle count mismatch: ${declaredTriangles} != ${triangleCount}`,
      buffer.length === expectedLength ? "" : `STL byte length mismatch: ${buffer.length} != ${expectedLength}`,
    ].filter(Boolean);
  }
  if (format === "glb") {
    try {
      const json = parseGlbJson(buffer);
      const primitive = json.meshes?.[0]?.primitives?.[0];
      const nodeExtras = json.nodes?.[0]?.extras || {};
      return [
        primitive?.attributes?.POSITION === 0 ? "" : "GLB POSITION accessor missing",
        primitive?.attributes?.NORMAL === 1 ? "" : "GLB NORMAL accessor missing",
        nodeExtras.cadOccurrenceId ? "" : "GLB CAD-native occurrence metadata missing",
      ].filter(Boolean);
    } catch (error) {
      return [error instanceof Error ? error.message : String(error)];
    }
  }
  if (format === "3mf") {
    return buffer.readUInt32LE(0) === 0x04034b50 ? [] : ["3MF ZIP header missing"];
  }
  return [`Unsupported format: ${format}`];
}

function qualityFailures(quality) {
  const failures = [];
  if (quality.triangleCount < 100) {
    failures.push(`too few triangles: ${quality.triangleCount}`);
  }
  if (quality.triangles.nonFinitePositions > 0 || quality.triangles.nonFiniteNormals > 0) {
    failures.push("mesh contains non-finite position or normal data");
  }
  if (quality.triangles.degenerateRatio > 0.002) {
    failures.push(`degenerate triangle ratio ${(quality.triangles.degenerateRatio * 100).toFixed(3)}%`);
  }
  if (quality.edges.boundaryRatio > 0.002) {
    failures.push(`boundary edge ratio ${(quality.edges.boundaryRatio * 100).toFixed(3)}%`);
  }
  if (quality.orientation.samples > 0 && quality.orientation.invertedRatio > 0.02) {
    failures.push(`inverted orientation sample ratio ${(quality.orientation.invertedRatio * 100).toFixed(3)}%`);
  }
  if (quality.triangles.poorNormalAlignment > Math.max(8, quality.triangleCount * 0.005)) {
    failures.push(`poor normal alignment count ${quality.triangles.poorNormalAlignment}`);
  }
  return failures;
}

async function verifyFile(inputPath, options) {
  const started = Date.now();
  const model = await loadImplicitCadModelFromPath(inputPath);
  const mesh = meshImplicitCadModel(model, {
    resolution: options.resolution,
    maxCells: options.maxCells,
    smoothNormals: true,
  });
  const quality = analyzeImplicitMeshQuality(mesh, {
    model,
    maxOrientationSamples: options.orientationSamples,
  });
  const formatResults = [];
  for (const format of options.formats) {
    const exported = meshToFormat(mesh, format, {
      name: model.name,
      color: model.material?.color,
    });
    const failures = validateFormatBuffer(format, exported.body, mesh);
    if (options.writeDir) {
      await fs.mkdir(options.writeDir, { recursive: true });
      const stem = path.basename(inputPath).replace(/\.implicit\.(?:js|mjs)$/i, "");
      await fs.writeFile(path.join(options.writeDir, `${stem}.${format}`), exported.body);
    }
    formatResults.push({
      format,
      bytes: exported.body.length,
      failures,
    });
  }
  const failures = [
    ...qualityFailures(quality),
    ...formatResults.flatMap((result) => result.failures.map((failure) => `${result.format}: ${failure}`)),
  ];
  return {
    input: path.relative(process.cwd(), inputPath),
    name: model.name,
    ok: failures.length === 0,
    failures,
    elapsedMs: Date.now() - started,
    mesh: {
      triangles: mesh.triangleCount,
      vertices: mesh.vertexCount,
      grid: mesh.grid,
    },
    quality,
    formats: formatResults,
  };
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  if (options.help) {
    process.stdout.write(usage());
    return;
  }
  const files = options.files.length ? options.files : await listImplicitFiles(options.root);
  if (!files.length) {
    throw new Error(`No implicit CAD files found under ${options.root}`);
  }
  const results = [];
  for (const file of files) {
    if (!options.json) {
      process.stdout.write(`VERIFY ${path.relative(process.cwd(), file)}\n`);
    }
    const result = await verifyFile(file, options);
    results.push(result);
    if (!options.json) {
      const status = result.ok ? "PASS" : "FAIL";
      const formats = result.formats
        .map((formatResult) => `${formatResult.format}:${Math.round(formatResult.bytes / 1024)}KB`)
        .join(" ");
      process.stdout.write(
        `${status} ${result.input}  triangles=${result.mesh.triangles.toLocaleString()} ` +
        `boundary=${result.quality.edges.boundary} nonManifold=${result.quality.edges.nonManifold} ` +
        `inverted=${result.quality.orientation.inverted}/${result.quality.orientation.samples} ${formats}\n`
      );
      for (const failure of result.failures) {
        process.stdout.write(`  - ${failure}\n`);
      }
    }
  }
  const summary = {
    ok: results.every((result) => result.ok),
    resolution: Math.floor(finiteNumber(options.resolution, 96)),
    formats: options.formats,
    fileCount: results.length,
    elapsedMs: results.reduce((total, result) => total + result.elapsedMs, 0),
    results,
  };
  if (options.json) {
    process.stdout.write(`${JSON.stringify(summary, null, 2)}\n`);
  }
  if (!summary.ok) {
    process.exitCode = 1;
  }
}

main().catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.exit(1);
});
