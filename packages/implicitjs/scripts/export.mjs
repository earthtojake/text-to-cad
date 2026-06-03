#!/usr/bin/env node
import { exportImplicitCadFile, IMPLICIT_CAD_EXPORT_FORMATS } from "../src/lib/implicitCad/export.js";

function usage() {
  return `Usage:
  node scripts/export.mjs --input <model.implicit.js> --format glb
  node scripts/export.mjs --input <model.implicit.js> --output <mesh.stl> --resolution <resolution>

Options:
  --input, -i       Input .implicit.js/.implicit.mjs file.
  --output, -o      Output file. Defaults to same folder/stem with selected format.
  --format, -f      Export format: ${IMPLICIT_CAD_EXPORT_FORMATS.join(", ")}.
  --resolution      Longest-axis sampling resolution. Default: 96.
  --max-cells       Safety cap for grid cells. Default: 2500000.
  --params          JSON object of implicit parameter values.
  --animation       JSON object of implicit animation state.
  --animated        Export a GLB morph-target animation from the selected animation.
  --frames          Animation frame count for --animated. Default: 18.
  --duration        Animation duration in seconds for --animated. Default: animation duration.
  --json            Print machine-readable result JSON.
  --help, -h        Show this help.
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
    throw new Error(`Invalid ${label}: ${error instanceof Error ? error.message : String(error)}`);
  }
}

function parseArgs(argv) {
  const options = {
    input: "",
    output: "",
    format: "",
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
        throw new Error(`${arg} requires a value`);
      }
      return argv[index];
    };
    switch (arg) {
      case "--input":
      case "-i":
        options.input = readValue();
        break;
      case "--output":
      case "-o":
        options.output = readValue();
        break;
      case "--format":
      case "-f":
        options.format = readValue();
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
          throw new Error(`Unknown argument: ${arg}`);
        }
    }
  }
  return options;
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  if (options.help) {
    process.stdout.write(usage());
    return;
  }
  if (!options.input) {
    throw new Error("Missing --input");
  }
  const result = await exportImplicitCadFile(options);
  if (options.json) {
    process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
  } else {
    process.stdout.write(`Exported ${result.format.toUpperCase()} ${result.output}\n`);
    process.stdout.write(`Triangles: ${result.triangleCount.toLocaleString()}  Bytes: ${result.bytes.toLocaleString()}\n`);
  }
}

main().catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.exitCode = 1;
});
