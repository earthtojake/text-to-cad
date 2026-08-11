#!/usr/bin/env node
import { exportImplicitCadFile, IMPLICIT_CAD_EXPORT_FORMATS } from "../src/lib/implicitCad/export.js";
import path from "node:path";

// Sentinel for a format flag passed without a path: export to the default sibling path
// (`<name>.<ext>` beside the model), mirroring skills/cad/scripts/export.
const DEFAULT_OUTPUT = "__default_sibling_output__";

// One flag per format, several allowed per run. Derived from the frozen format list so
// the CLI cannot drift from the exporter.
const FORMAT_FLAGS = new Map(IMPLICIT_CAD_EXPORT_FORMATS.map((format) => [`--${format}`, format]));
const FORMAT_FLAG_LIST = [...FORMAT_FLAGS.keys()].join(", ");

class UsageError extends Error {}

function usage() {
  return `Usage:
  node scripts/export.mjs --input <model.implicit.js> --stl --3mf --glb
  node scripts/export.mjs --input <model.implicit.js> --stl <mesh.stl> --resolution <resolution>

At least one export format is required. The model is meshed once per run, so all
requested formats come from identical geometry.

Options:
  --input, -i       Input .implicit.js/.implicit.mjs file (also accepted positionally).
  --stl [OUTPUT]    Export an STL mesh. Without a path, writes the sibling <name>.stl.
  --3mf [OUTPUT]    Export a 3MF mesh. Without a path, writes the sibling <name>.3mf.
  --glb [OUTPUT]    Export a GLB mesh. Without a path, writes the sibling <name>.glb.
                    A supplied path resolves against the current directory.
  --resolution      Longest-axis sampling resolution. Default: 96.
  --max-cells       Safety cap for grid cells. Default: 2500000.
  --params          JSON object of implicit parameter values.
  --animation       JSON object of implicit animation state.
  --animated        Export a GLB morph-target animation from the selected animation.
                    GLB-only: cannot be combined with --stl or --3mf.
  --frames          Animation frame count for --animated. Default: 18.
  --duration        Animation duration in seconds for --animated. Default: animation duration.
  --json            Print machine-readable result JSON.
  --help, -h        Show this help.

Exit codes: 0 success, 1 export failure, 2 usage error.
`;
}

function parseJsonOption(value, label) {
  const text = String(value || "").trim();
  if (!text) {
    return null;
  }
  try {
    const parsed = JSON.parse(text);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      throw new Error(`${label} must be a JSON object`);
    }
    return parsed;
  } catch (error) {
    throw new UsageError(`Invalid ${label}: ${error instanceof Error ? error.message : String(error)}`);
  }
}

function parseArgs(argv) {
  const options = {
    input: "",
    formatOutputs: new Map(),
    resolution: 96,
    maxCells: undefined,
    params: null,
    animationState: null,
    animated: false,
    frames: undefined,
    duration: undefined,
    json: false,
    help: false,
  };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    const readValue = () => {
      index += 1;
      if (index >= argv.length) {
        throw new UsageError(`${arg} requires a value`);
      }
      return argv[index];
    };
    if (FORMAT_FLAGS.has(arg)) {
      const format = FORMAT_FLAGS.get(arg);
      const next = argv[index + 1];
      let value = DEFAULT_OUTPUT;
      if (next !== undefined && !next.startsWith("-")) {
        index += 1;
        value = next;
      }
      if (options.formatOutputs.has(format)) {
        throw new UsageError(`${arg} was given more than once`);
      }
      options.formatOutputs.set(format, value);
      continue;
    }
    switch (arg) {
      case "--input":
      case "-i":
        options.input = readValue();
        break;
      case "--resolution":
        options.resolution = Number(readValue());
        break;
      case "--max-cells":
        options.maxCells = Number(readValue());
        break;
      case "--params":
        options.params = parseJsonOption(readValue(), "--params");
        break;
      case "--animation":
        options.animationState = parseJsonOption(readValue(), "--animation");
        break;
      case "--animated":
        options.animated = true;
        break;
      case "--frames":
        options.frames = Number(readValue());
        break;
      case "--duration":
        options.duration = Number(readValue());
        break;
      case "--json":
        options.json = true;
        break;
      case "--help":
      case "-h":
        options.help = true;
        break;
      default:
        if (!options.input && !arg.startsWith("-")) {
          options.input = arg;
        } else {
          throw new UsageError(`Unknown argument: ${arg}`);
        }
    }
  }
  return options;
}

/** Requested outputs in the frozen format order, with the sentinel resolved to "use the
 * default sibling path". A supplied path must carry the format's own extension. */
function requestedOutputs(formatOutputs) {
  const outputs = [];
  for (const format of IMPLICIT_CAD_EXPORT_FORMATS) {
    if (!formatOutputs.has(format)) {
      continue;
    }
    const value = formatOutputs.get(format);
    if (value === DEFAULT_OUTPUT) {
      outputs.push({ format, output: "" });
      continue;
    }
    if (path.extname(value).toLowerCase() !== `.${format}`) {
      throw new UsageError(`--${format} output must end with .${format}: ${value}`);
    }
    outputs.push({ format, output: value });
  }
  return outputs;
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  if (options.help) {
    process.stdout.write(usage());
    return;
  }
  if (!options.input) {
    throw new UsageError("Missing --input");
  }
  const outputs = requestedOutputs(options.formatOutputs);
  if (!outputs.length) {
    throw new UsageError(`at least one export format is required: ${FORMAT_FLAG_LIST}`);
  }
  const result = await exportImplicitCadFile({ ...options, outputs });
  if (options.json) {
    process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
    return;
  }
  for (const file of result.files) {
    process.stdout.write(`wrote ${file.format.toUpperCase()}: ${file.output} (${file.bytes.toLocaleString()} bytes)\n`);
  }
  process.stdout.write(`Triangles: ${result.triangleCount.toLocaleString()}\n`);
}

main().catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  if (error instanceof UsageError) {
    process.stderr.write(usage());
    process.exitCode = 2;
    return;
  }
  process.exitCode = 1;
});
