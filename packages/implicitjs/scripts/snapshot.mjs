#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { performance } from "node:perf_hooks";
import { fileURLToPath, pathToFileURL } from "node:url";

export const SNAPSHOT_ORIGIN = "http://implicit-cad-snapshot.local";
const SNAPSHOT_RENDER_URL = `${SNAPSHOT_ORIGIN}/render.html`;
const SNAPSHOT_ROUTE_GLOB = `${SNAPSHOT_ORIGIN}/**`;
export const PACKAGE_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
export const RUNTIME_DIR = path.join(PACKAGE_ROOT, "scripts", "snapshot-runtime");
export const RENDER_HTML_PATH = path.join(RUNTIME_DIR, "render.html");
const DEFAULT_TIMEOUT_SECONDS = 180;
const RENDER_BROWSER_STARTUP_TIMEOUT_MS = 15_000;
const DEFAULT_RENDER_THEME_ID = "workbench";
const WORKBENCH_RENDER_THEME_IDS = new Set([DEFAULT_RENDER_THEME_ID]);
const SIMPLE_RENDER_WIDTH = 1200;
const SIMPLE_RENDER_HEIGHT = 900;
const SIMPLE_SQUARE_RENDER_WIDTH = 1024;
const SIMPLE_SQUARE_RENDER_HEIGHT = 1024;
const DIAGNOSTIC_RENDER_WIDTH = 1600;
const DIAGNOSTIC_RENDER_HEIGHT = 1200;
const DEFAULT_RENDER_WIDTH = DIAGNOSTIC_RENDER_WIDTH;
const DEFAULT_RENDER_HEIGHT = DIAGNOSTIC_RENDER_HEIGHT;
const COMPLEX_ASSEMBLY_RENDER_WIDTH = 1800;
const COMPLEX_ASSEMBLY_RENDER_HEIGHT = 1200;
const COMPLEX_ASSEMBLY_LARGE_RENDER_WIDTH = 1920;
const COMPLEX_ASSEMBLY_LARGE_RENDER_HEIGHT = 1440;
const PRESENTATION_RENDER_WIDTH = 2400;
const PRESENTATION_RENDER_HEIGHT = 1600;
const PRESENTATION_LARGE_RENDER_WIDTH = 2800;
const PRESENTATION_LARGE_RENDER_HEIGHT = 1800;
const ORBIT_RENDER_WIDTH = 960;
const ORBIT_RENDER_HEIGHT = 640;
const CONTACT_SHEET_RENDER_WIDTH = 2400;
const CONTACT_SHEET_RENDER_HEIGHT = 1600;

const APPEARANCE_OPTION_KEYS = new Set([
  "materials",
  "edges",
  "background",
  "floor",
  "environment",
  "lighting",
]);
const GRAPHICS_OPTION_KEYS = new Set([
  "resolutionScale",
  "interactionResolutionScale",
  "detail",
  "normalSmoothing",
  "modelColors",
  "shadows",
  "ambientOcclusion",
  "rimLight",
]);

export class SnapshotError extends Error {
  constructor(message) {
    super(message);
    this.name = "SnapshotError";
  }
}

class RouteFileError extends SnapshotError {
  constructor(message, { status = 404 } = {}) {
    super(message);
    this.status = status;
  }
}

export function helpText() {
  return `Usage:
  node scripts/snapshot.mjs --input <model.implicit.js> --output <snapshot.png>
  node scripts/snapshot.mjs --input <model.implicit.js> --output <orbit.gif> --mode orbit
  node scripts/snapshot.mjs --job <render-job.json>
  node scripts/snapshot.mjs --job - --json

Snapshot renders browser-native implicit CAD .implicit.js/.implicit.mjs modules. Supported shortcut flags are --input, --output/-o, --mode, --appearance, --camera, --size-profile, --width, --height, --params, --graphics, --job, and --json. The default appearance is the built-in light/dark-aware theme. --appearance accepts a saved theme name, an inline JSON appearance settings object, or a JSON appearance settings file path. --camera accepts a preset, azimuth:elevation pair, or JSON object with preset, position, target, up, direction, and zoom fields. JSON jobs use input, mode=view/orbit/animate, outputs, camera, width/height, appearance, graphics, implicitParameters, implicitAnimation, orbit, and optional render.transparent/render.zoom/render.frameMargin. A job can include multiple outputs, and --job can load a raw job, an array of jobs, or { "jobs": [...] }; prefer one multi-output job for review packets so the browser, source module, and runtime model are reused. Output file names are saved with a shared UTC seconds timestamp before the extension.
`;
}

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function positiveInteger(value, label) {
  const parsed = Number.parseInt(String(value || ""), 10);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    throw new SnapshotError(`${label} must be a positive integer`);
  }
  return parsed;
}

function readRequiredValue(argv, index, flag) {
  const value = argv[index + 1];
  if (!value || value.startsWith("--")) {
    throw new SnapshotError(`${flag} requires a value`);
  }
  return value;
}

function optionDefaults() {
  return {
    job: "",
    input: "",
    output: "",
    mode: "",
    modeSpecified: false,
    appearance: DEFAULT_RENDER_THEME_ID,
    appearanceSpecified: false,
    camera: "iso",
    cameraSpecified: false,
    sizeProfile: "",
    graphics: null,
    graphicsSpecified: false,
    width: null,
    height: null,
    params: null,
    paramsSpecified: false,
    json: false,
    help: false,
  };
}

export function parseSnapshotArgs(argv) {
  const options = optionDefaults();
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--help" || arg === "-h") {
      options.help = true;
    } else if (arg === "--json") {
      options.json = true;
    } else if (arg === "--job") {
      options.job = readRequiredValue(argv, index, arg);
      index += 1;
    } else if (arg.startsWith("--job=")) {
      options.job = arg.slice("--job=".length);
    } else if (arg === "--input") {
      options.input = readRequiredValue(argv, index, arg);
      index += 1;
    } else if (arg.startsWith("--input=")) {
      options.input = arg.slice("--input=".length);
    } else if (arg === "--output" || arg === "-o") {
      options.output = readRequiredValue(argv, index, arg);
      index += 1;
    } else if (arg.startsWith("--output=")) {
      options.output = arg.slice("--output=".length);
    } else if (arg === "--mode") {
      options.mode = readRequiredValue(argv, index, arg);
      options.modeSpecified = true;
      index += 1;
    } else if (arg.startsWith("--mode=")) {
      options.mode = arg.slice("--mode=".length);
      options.modeSpecified = true;
    } else if (arg === "--appearance") {
      options.appearance = readRequiredValue(argv, index, arg);
      options.appearanceSpecified = true;
      index += 1;
    } else if (arg.startsWith("--appearance=")) {
      options.appearance = arg.slice("--appearance=".length);
      options.appearanceSpecified = true;
    } else if (arg === "--camera") {
      options.camera = readRequiredValue(argv, index, arg);
      options.cameraSpecified = true;
      index += 1;
    } else if (arg.startsWith("--camera=")) {
      options.camera = arg.slice("--camera=".length);
      options.cameraSpecified = true;
    } else if (arg === "--size-profile") {
      options.sizeProfile = readRequiredValue(argv, index, arg);
      index += 1;
    } else if (arg.startsWith("--size-profile=")) {
      options.sizeProfile = arg.slice("--size-profile=".length);
    } else if (arg === "--width") {
      options.width = positiveInteger(readRequiredValue(argv, index, arg), arg);
      index += 1;
    } else if (arg.startsWith("--width=")) {
      options.width = positiveInteger(arg.slice("--width=".length), "--width");
    } else if (arg === "--height") {
      options.height = positiveInteger(readRequiredValue(argv, index, arg), arg);
      index += 1;
    } else if (arg.startsWith("--height=")) {
      options.height = positiveInteger(arg.slice("--height=".length), "--height");
    } else if (arg === "--params") {
      options.params = readRequiredValue(argv, index, arg);
      options.paramsSpecified = true;
      index += 1;
    } else if (arg.startsWith("--params=")) {
      options.params = arg.slice("--params=".length);
      options.paramsSpecified = true;
    } else if (arg === "--graphics") {
      options.graphics = readRequiredValue(argv, index, arg);
      options.graphicsSpecified = true;
      index += 1;
    } else if (arg.startsWith("--graphics=")) {
      options.graphics = arg.slice("--graphics=".length);
      options.graphicsSpecified = true;
    } else {
      throw new SnapshotError(`Unknown argument: ${arg}`);
    }
  }
  return options;
}

function loadJsonText(text, sourceLabel) {
  try {
    return JSON.parse(text);
  } catch (error) {
    throw new SnapshotError(`Failed to parse JSON from ${sourceLabel}: ${error.message}`);
  }
}

function parseCameraOption(rawCamera) {
  const camera = String(rawCamera || "").trim();
  if (!camera) {
    throw new SnapshotError("--camera requires a preset, azimuth:elevation pair, or JSON camera object");
  }
  if (!camera.startsWith("{")) {
    return camera;
  }
  const parsed = loadJsonText(camera, "--camera");
  if (!isPlainObject(parsed)) {
    throw new SnapshotError("--camera must be a preset, azimuth:elevation pair, or JSON object");
  }
  return { ...parsed };
}

function parseParamsOption(rawParams) {
  const parsed = loadJsonText(String(rawParams || ""), "--params");
  if (!isPlainObject(parsed)) {
    throw new SnapshotError("--params must be an implicit parameter JSON object");
  }
  return { ...parsed };
}

function validateDirectSettingsPayload(parsed, {
  optionName,
  sourceLabel,
  allowedKeys,
  settingLabel,
}) {
  if (!isPlainObject(parsed)) {
    throw new SnapshotError(`${optionName} JSON must be a ${settingLabel} object: ${sourceLabel}`);
  }
  const unknownKeys = Object.keys(parsed).filter((key) => !allowedKeys.has(key));
  if (unknownKeys.length) {
    throw new SnapshotError(
      `${optionName} JSON must be the ${settingLabel} object directly; unsupported keys: ${unknownKeys.join(", ")}`
    );
  }
  if (!Object.keys(parsed).length) {
    throw new SnapshotError(`${optionName} JSON must include at least one ${settingLabel} field: ${sourceLabel}`);
  }
  return { ...parsed };
}

function resolveMaybeRelative(rawPath, cwd) {
  return path.isAbsolute(rawPath) ? path.resolve(rawPath) : path.resolve(cwd, rawPath);
}

function loadAppearanceOption(rawAppearance, { cwd }) {
  const appearance = String(rawAppearance || DEFAULT_RENDER_THEME_ID).trim() || DEFAULT_RENDER_THEME_ID;
  if (appearance.startsWith("{")) {
    return validateDirectSettingsPayload(loadJsonText(appearance, "--appearance"), {
      optionName: "--appearance",
      sourceLabel: "--appearance",
      allowedKeys: APPEARANCE_OPTION_KEYS,
      settingLabel: "appearance settings",
    });
  }

  const appearancePath = resolveMaybeRelative(appearance, cwd);
  const looksLikeFile = appearance.toLowerCase().endsWith(".json") || appearance.includes("/") || appearance.includes("\\");
  if (!looksLikeFile && !fs.existsSync(appearancePath)) {
    return appearance;
  }
  if (!fs.existsSync(appearancePath)) {
    throw new SnapshotError(`Appearance JSON file does not exist: ${appearance}`);
  }
  return validateDirectSettingsPayload(loadJsonText(fs.readFileSync(appearancePath, "utf8"), appearancePath), {
    optionName: "--appearance",
    sourceLabel: appearancePath,
    allowedKeys: APPEARANCE_OPTION_KEYS,
    settingLabel: "appearance settings",
  });
}

function loadGraphicsOption(rawGraphics, { cwd }) {
  const graphics = String(rawGraphics || "").trim();
  if (!graphics) {
    throw new SnapshotError("--graphics requires a JSON object or JSON file path");
  }
  if (graphics.startsWith("{")) {
    return validateDirectSettingsPayload(loadJsonText(graphics, "--graphics"), {
      optionName: "--graphics",
      sourceLabel: "--graphics",
      allowedKeys: GRAPHICS_OPTION_KEYS,
      settingLabel: "implicit graphics settings",
    });
  }

  const graphicsPath = resolveMaybeRelative(graphics, cwd);
  if (!fs.existsSync(graphicsPath)) {
    throw new SnapshotError(`Graphics JSON file does not exist: ${graphics}`);
  }
  return validateDirectSettingsPayload(loadJsonText(fs.readFileSync(graphicsPath, "utf8"), graphicsPath), {
    optionName: "--graphics",
    sourceLabel: graphicsPath,
    allowedKeys: GRAPHICS_OPTION_KEYS,
    settingLabel: "implicit graphics settings",
  });
}

function cloneJson(value) {
  return JSON.parse(JSON.stringify(value));
}

function applyOptionOverridesToJob(job, options, { cwd }) {
  if (!isPlainObject(job)) {
    return job;
  }
  if (!options.modeSpecified &&
      !options.appearanceSpecified &&
      !options.cameraSpecified &&
      !options.sizeProfile &&
      !options.width &&
      !options.height &&
      !options.paramsSpecified &&
      !options.graphicsSpecified) {
    return job;
  }
  const nextJob = cloneJson(job);
  if (options.modeSpecified) {
    nextJob.mode = options.mode;
  }
  if (options.appearanceSpecified) {
    nextJob.appearance = loadAppearanceOption(options.appearance, { cwd });
  }
  if (options.cameraSpecified) {
    nextJob.camera = parseCameraOption(options.camera);
  }
  if (options.width) {
    nextJob.width = options.width;
  }
  if (options.height) {
    nextJob.height = options.height;
  }
  if (options.sizeProfile) {
    nextJob.render = {
      ...(isPlainObject(nextJob.render) ? nextJob.render : {}),
      sizeProfile: options.sizeProfile,
    };
  }
  if (options.paramsSpecified) {
    nextJob.implicitParameters = parseParamsOption(options.params);
  }
  if (options.graphicsSpecified) {
    nextJob.graphics = loadGraphicsOption(options.graphics, { cwd });
  }
  return nextJob;
}

async function readStream(stream) {
  return new Promise((resolve, reject) => {
    let text = "";
    stream.setEncoding("utf8");
    stream.on("data", (chunk) => {
      text += chunk;
    });
    stream.on("error", reject);
    stream.on("end", () => resolve(text));
  });
}

export async function loadJobFromOptions(options, {
  stdin = process.stdin,
  cwd = process.cwd(),
} = {}) {
  const resolvedCwd = path.resolve(cwd);
  if (options.job) {
    const text = options.job === "-"
      ? await readStream(stdin)
      : fs.readFileSync(resolveMaybeRelative(options.job, resolvedCwd), "utf8");
    const sourceLabel = options.job === "-" ? "stdin" : resolveMaybeRelative(options.job, resolvedCwd);
    const payload = loadJsonText(text, sourceLabel);
    if (Array.isArray(payload)) {
      return payload.map((job) => applyOptionOverridesToJob(job, options, { cwd: resolvedCwd }));
    }
    if (isPlainObject(payload) && Array.isArray(payload.jobs)) {
      return {
        ...cloneJson(payload),
        jobs: payload.jobs.map((job) => applyOptionOverridesToJob(job, options, { cwd: resolvedCwd })),
      };
    }
    return applyOptionOverridesToJob(payload, options, { cwd: resolvedCwd });
  }

  if (!stdin.isTTY && !options.input) {
    const text = await readStream(stdin);
    if (text.trim()) {
      return loadJsonText(text, "stdin");
    }
  }

  if (!options.input) {
    throw new SnapshotError("render requires --job, stdin JSON, or --input");
  }
  if (!options.output) {
    throw new SnapshotError("render shortcut requires --output");
  }

  const output = {
    path: options.output,
    camera: parseCameraOption(options.camera),
  };
  if (options.width) {
    output.width = options.width;
  }
  if (options.height) {
    output.height = options.height;
  }
  let mode = String(options.mode || "").trim().toLowerCase();
  if (!mode) {
    mode = options.output.toLowerCase().endsWith(".gif") ? "orbit" : "view";
  }
  const job = {
    input: options.input,
    mode,
    outputs: [output],
    appearance: loadAppearanceOption(options.appearance, { cwd: resolvedCwd }),
  };
  if (options.sizeProfile) {
    job.render = { sizeProfile: options.sizeProfile };
  }
  if (options.paramsSpecified) {
    job.implicitParameters = parseParamsOption(options.params);
  }
  if (options.graphicsSpecified) {
    job.graphics = loadGraphicsOption(options.graphics, { cwd: resolvedCwd });
  }
  return job;
}

function pathIsInsideOrEqual(child, parent) {
  const resolvedChild = path.resolve(child);
  const resolvedParent = path.resolve(parent);
  const relative = path.relative(resolvedParent, resolvedChild);
  return relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative));
}

function isImplicitPath(filePath) {
  const name = path.basename(filePath).toLowerCase();
  return name.endsWith(".implicit.js") || name.endsWith(".implicit.mjs");
}

function resolveInputPath(rawInput, { cwd }) {
  const inputText = String(rawInput || "").trim();
  if (!inputText) {
    throw new SnapshotError("render job is missing input");
  }
  const selected = resolveMaybeRelative(inputText, cwd);
  if (!fs.existsSync(selected)) {
    throw new SnapshotError(`Render input does not exist: ${inputText}`);
  }
  if (!isImplicitPath(selected)) {
    throw new SnapshotError("Snapshot supports only .implicit.js and .implicit.mjs inputs");
  }
  return selected;
}

function encodePathParam(value) {
  return value.replaceAll(path.sep, "/").split("/").map(encodeURIComponent).join("/");
}

function assetUrlForPath(filePath, rootPath) {
  if (!pathIsInsideOrEqual(filePath, rootPath)) {
    throw new SnapshotError(`Render asset must be inside the snapshot render root: ${filePath}`);
  }
  const stat = fs.statSync(filePath);
  const versionSource = `${path.resolve(filePath)}:${stat.mtimeMs}:${stat.size}`;
  const version = Buffer.from(versionSource).toString("base64url");
  return `/__render_asset/${encodePathParam(path.relative(path.resolve(rootPath), path.resolve(filePath)))}?v=${version}`;
}

export function snapshotTimestamp() {
  return new Date().toISOString().replace(/[-:]/gu, "").replace(/\.\d{3}Z$/u, "Z");
}

export function timestampOutputPath(outputPath, timestamp) {
  if (!outputPath) {
    return "";
  }
  const parsed = path.parse(outputPath);
  return path.join(parsed.dir, `${parsed.name}_${timestamp}${parsed.ext}`);
}

function normalizeSnapshotJobPacket(rawPayload) {
  if (Array.isArray(rawPayload)) {
    return { single: false, jobs: rawPayload };
  }
  if (isPlainObject(rawPayload) && Array.isArray(rawPayload.jobs)) {
    return { single: false, jobs: rawPayload.jobs };
  }
  return { single: true, jobs: [rawPayload] };
}

function appearanceThemeIdForJob(job) {
  const appearance = job.appearance;
  return typeof appearance === "string"
    ? (appearance.trim().toLowerCase() || DEFAULT_RENDER_THEME_ID)
    : DEFAULT_RENDER_THEME_ID;
}

function normalizeSizeProfile(value) {
  return String(value || "").trim().toLowerCase().replaceAll("_", "-");
}

function explicitSizeProfile(job, output) {
  const render = isPlainObject(job.render) ? job.render : {};
  return normalizeSizeProfile(output.sizeProfile || render.sizeProfile || job.sizeProfile || "");
}

function defaultRenderSize(job, output) {
  const mode = String(job.mode || "view").trim().toLowerCase();
  const profile = explicitSizeProfile(job, output);
  if (profile === "simple-square" || profile === "square") {
    return [SIMPLE_SQUARE_RENDER_WIDTH, SIMPLE_SQUARE_RENDER_HEIGHT];
  }
  if (["simple", "simple-part", "unlabeled"].includes(profile)) {
    return [SIMPLE_RENDER_WIDTH, SIMPLE_RENDER_HEIGHT];
  }
  if (["presentation-large", "hero", "large-presentation"].includes(profile)) {
    return [PRESENTATION_LARGE_RENDER_WIDTH, PRESENTATION_LARGE_RENDER_HEIGHT];
  }
  if (profile === "presentation") {
    return [PRESENTATION_RENDER_WIDTH, PRESENTATION_RENDER_HEIGHT];
  }
  if (["complex-assembly-large", "assembly-large"].includes(profile)) {
    return [COMPLEX_ASSEMBLY_LARGE_RENDER_WIDTH, COMPLEX_ASSEMBLY_LARGE_RENDER_HEIGHT];
  }
  if (["complex-assembly", "assembly"].includes(profile)) {
    return [COMPLEX_ASSEMBLY_RENDER_WIDTH, COMPLEX_ASSEMBLY_RENDER_HEIGHT];
  }
  if (profile === "contact-sheet" || profile === "contactsheet") {
    return [CONTACT_SHEET_RENDER_WIDTH, CONTACT_SHEET_RENDER_HEIGHT];
  }
  if (profile === "orbit" || mode === "orbit" || mode === "animate" || isPlainObject(job.implicitAnimation)) {
    return [ORBIT_RENDER_WIDTH, ORBIT_RENDER_HEIGHT];
  }
  if (["dimensioned", "section", "labeled", "diagnostic"].includes(profile) ||
      WORKBENCH_RENDER_THEME_IDS.has(appearanceThemeIdForJob(job))) {
    return [DIAGNOSTIC_RENDER_WIDTH, DIAGNOSTIC_RENDER_HEIGHT];
  }
  return [SIMPLE_RENDER_WIDTH, SIMPLE_RENDER_HEIGHT];
}

function resolveOutputSize(job, output) {
  const [defaultWidth, defaultHeight] = defaultRenderSize(job, output);
  return [
    positiveInteger(output.width || job.width || defaultWidth, "output width"),
    positiveInteger(output.height || job.height || defaultHeight, "output height"),
  ];
}

export function resolveRenderJob(rawJob, {
  cwd = process.cwd(),
  timestamp = snapshotTimestamp(),
} = {}) {
  if (!isPlainObject(rawJob)) {
    throw new SnapshotError("render job must be an object");
  }
  const job = cloneJson(rawJob);
  if ("theme" in job) {
    throw new SnapshotError("render jobs use appearance; theme is reserved for saved appearance settings");
  }
  if ("params" in job) {
    throw new SnapshotError("render jobs use implicitParameters; params is reserved for shortcut --params parsing");
  }
  const mode = String(job.mode || "view").trim().toLowerCase();
  if (!["view", "orbit", "animate"].includes(mode)) {
    throw new SnapshotError("Implicit CAD snapshot supports only view, orbit, and animate modes");
  }
  const renderSettings = isPlainObject(job.render) ? { ...job.render } : {};
  const graphicsSettings = isPlainObject(job.graphics) ? { ...job.graphics } : {};
  const appearanceSettings = job.appearance || DEFAULT_RENDER_THEME_ID;
  const resolvedCwd = path.resolve(cwd);
  const inputPath = resolveInputPath(job.input, { cwd: resolvedCwd });
  const rootPath = path.dirname(inputPath);
  const outputs = Array.isArray(job.outputs) ? job.outputs : [];
  if (!outputs.length) {
    throw new SnapshotError("render job must include outputs");
  }
  const normalizedOutputs = outputs.map((output) => {
    const outputObject = isPlainObject(output) ? { ...output } : {};
    const [width, height] = resolveOutputSize({
      ...job,
      mode,
      appearance: appearanceSettings,
      render: renderSettings,
    }, outputObject);
    const outputPath = String(outputObject.path || "");
    const timestampedOutputPath = timestampOutputPath(outputPath, timestamp);
    return {
      ...outputObject,
      path: timestampedOutputPath ? path.resolve(resolvedCwd, timestampedOutputPath) : "",
      width,
      height,
      camera: outputObject.camera || job.camera || "iso",
    };
  });

  return {
    ...job,
    mode,
    appearance: appearanceSettings,
    graphics: graphicsSettings,
    render: renderSettings,
    outputs: normalizedOutputs,
    resolved: {
      rootPath,
      inputPath,
      inputUrl: assetUrlForPath(inputPath, rootPath),
      kind: "implicit",
    },
  };
}

export function resolveRenderJobPacket(rawPayload, {
  cwd = process.cwd(),
  timestamp = snapshotTimestamp(),
} = {}) {
  const { single, jobs } = normalizeSnapshotJobPacket(rawPayload);
  return {
    single,
    jobs: jobs.map((job) => resolveRenderJob(job, { cwd, timestamp })),
  };
}

function contentTypeForPath(filePath) {
  const suffix = path.extname(filePath).toLowerCase();
  if (suffix === ".mjs" || suffix === ".js") {
    return "text/javascript; charset=utf-8";
  }
  if (suffix === ".html") {
    return "text/html; charset=utf-8";
  }
  if (suffix === ".json") {
    return "application/json; charset=utf-8";
  }
  if (suffix === ".png") {
    return "image/png";
  }
  if (suffix === ".gif") {
    return "image/gif";
  }
  return "application/octet-stream";
}

function routeFile(pathname, prefix, root) {
  const relativePath = decodeURIComponent(pathname.slice(prefix.length));
  const filePath = path.resolve(root, relativePath.replace(/^\/+/u, ""));
  if (!pathIsInsideOrEqual(filePath, root)) {
    throw new RouteFileError(`forbidden route path: ${pathname}`, { status: 403 });
  }
  return filePath;
}

export function resolveSnapshotRouteFile(rawUrl, { activeRootPath = null } = {}) {
  const parsed = new URL(rawUrl);
  if (parsed.origin !== SNAPSHOT_ORIGIN) {
    throw new RouteFileError(`unsupported snapshot origin: ${parsed.origin}`, { status: 403 });
  }
  if (parsed.pathname === "/render.html") {
    return RENDER_HTML_PATH;
  }
  if (parsed.pathname.startsWith("/src/")) {
    return routeFile(parsed.pathname, "/src/", path.join(PACKAGE_ROOT, "src"));
  }
  if (parsed.pathname.startsWith("/node_modules/")) {
    return routeFile(parsed.pathname, "/node_modules/", path.join(PACKAGE_ROOT, "node_modules"));
  }
  if (parsed.pathname.startsWith("/__render_asset/")) {
    if (!activeRootPath) {
      throw new RouteFileError("snapshot render asset requested without an active render root");
    }
    return routeFile(parsed.pathname, "/__render_asset/", activeRootPath);
  }
  throw new RouteFileError(`snapshot route not found: ${parsed.pathname}`);
}

function maxOutputSize(job) {
  const outputs = Array.isArray(job.outputs) && job.outputs.length ? job.outputs : [];
  const widths = outputs.filter(isPlainObject).map((output) => Number(output.width || DEFAULT_RENDER_WIDTH));
  const heights = outputs.filter(isPlainObject).map((output) => Number(output.height || DEFAULT_RENDER_HEIGHT));
  return [
    Math.max(...(widths.length ? widths : [DEFAULT_RENDER_WIDTH])),
    Math.max(...(heights.length ? heights : [DEFAULT_RENDER_HEIGHT])),
  ];
}

async function withSnapshotTimeout(promise, timeoutSeconds, label = "snapshot") {
  const timeout = Math.max(1, Number(timeoutSeconds || DEFAULT_TIMEOUT_SECONDS));
  let timer = null;
  try {
    return await Promise.race([
      promise,
      new Promise((_, reject) => {
        timer = setTimeout(() => reject(new SnapshotError(`${label} timed out after ${timeoutSeconds}s`)), timeout * 1000);
      }),
    ]);
  } finally {
    if (timer) {
      clearTimeout(timer);
    }
  }
}

class BatchSnapshotRenderer {
  constructor() {
    this.browser = null;
    this.context = null;
    this.page = null;
    this.activeRootPath = null;
    this.started = false;
  }

  async start() {
    if (this.started) {
      return;
    }
    try {
      const { chromium } = await import("playwright").catch((error) => {
        throw new SnapshotError(
          `Implicit CAD snapshot requires the JavaScript playwright package. Install implicitjs dependencies and run playwright install chromium if needed. ${error instanceof Error ? error.message : String(error)}`
        );
      });
      this.browser = await chromium.launch({
        headless: true,
        timeout: RENDER_BROWSER_STARTUP_TIMEOUT_MS,
        args: ["--single-process"],
      });
      this.context = await this.browser.newContext({
        viewport: { width: DEFAULT_RENDER_WIDTH, height: DEFAULT_RENDER_HEIGHT },
        deviceScaleFactor: 1,
      });
      this.page = await this.context.newPage();
      await this.page.route(SNAPSHOT_ROUTE_GLOB, (route) => this.handleRoute(route));
      await this.page.goto(SNAPSHOT_RENDER_URL, {
        waitUntil: "load",
        timeout: DEFAULT_TIMEOUT_SECONDS * 1000,
      });
      await this.page.waitForFunction(
        "typeof window.__implicitCadSnapshotRender === 'function'",
        null,
        { timeout: DEFAULT_TIMEOUT_SECONDS * 1000 }
      );
      this.started = true;
    } catch (error) {
      await this.close();
      throw error;
    }
  }

  async handleRoute(route) {
    const request = route.request();
    if (request.method() !== "GET") {
      await route.fulfill({ status: 405, contentType: "text/plain; charset=utf-8", body: "method not allowed" });
      return;
    }
    let filePath = "";
    try {
      filePath = resolveSnapshotRouteFile(request.url(), { activeRootPath: this.activeRootPath });
    } catch (error) {
      await route.fulfill({
        status: error instanceof RouteFileError ? error.status : 500,
        contentType: "text/plain; charset=utf-8",
        body: error instanceof Error ? error.message : String(error),
      });
      return;
    }
    if (!fs.existsSync(filePath) || !fs.statSync(filePath).isFile()) {
      await route.fulfill({ status: 404, contentType: "text/plain; charset=utf-8", body: "not found" });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: contentTypeForPath(filePath),
      headers: { "cache-control": "no-store" },
      body: fs.readFileSync(filePath),
    });
  }

  async render(job) {
    await this.start();
    const resolved = isPlainObject(job.resolved) ? job.resolved : {};
    this.activeRootPath = path.resolve(String(resolved.rootPath || ""));
    const [width, height] = maxOutputSize(job);
    await this.page.setViewportSize({ width, height });
    const result = await withSnapshotTimeout(
      this.page.evaluate((renderJob) => window.__implicitCadSnapshotRender(renderJob), { ...job }),
      job.timeoutSeconds || DEFAULT_TIMEOUT_SECONDS
    );
    if (!isPlainObject(result) || !result.ok) {
      throw new SnapshotError(String(isPlainObject(result) ? result.error || "" : "") || "unknown browser snapshot failure");
    }
    return result;
  }

  async close() {
    if (this.context) {
      try {
        await this.context.close();
      } catch {
        // Best-effort cleanup.
      }
      this.context = null;
    }
    if (this.browser) {
      try {
        await this.browser.close();
      } catch {
        // Best-effort cleanup.
      }
      this.browser = null;
    }
    this.page = null;
    this.started = false;
  }
}

export async function renderResolvedJobPacket(packet) {
  const renderer = new BatchSnapshotRenderer();
  const started = performance.now();
  const results = [];
  try {
    for (const job of packet.jobs) {
      const result = await renderer.render(job);
      results.push(packet.single ? result : { input: job.input, ...result });
    }
  } finally {
    await renderer.close();
  }
  if (packet.single) {
    return results[0];
  }
  return {
    ok: results.every((result) => result.ok !== false),
    jobs: results,
    timings: {
      jobCount: results.length,
      totalMs: performance.now() - started,
    },
  };
}

function writeOutputPayload(output) {
  const outputPath = String(output.path || "");
  if (!outputPath) {
    return;
  }
  const dataUrl = String(output.dataUrl || "");
  const match = dataUrl.match(/^data:([^;]+);base64,(.+)$/su);
  if (!match) {
    throw new SnapshotError(`Snapshot output did not include a base64 data URL: ${outputPath}`);
  }
  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  fs.writeFileSync(outputPath, Buffer.from(match[2], "base64"));
}

export function writeRenderOutputs(result) {
  if (Array.isArray(result.jobs)) {
    for (const jobResult of result.jobs) {
      if (isPlainObject(jobResult)) {
        writeRenderOutputs(jobResult);
      }
    }
    return;
  }
  const outputs = Array.isArray(result.outputs) ? result.outputs : [];
  for (const output of outputs) {
    if (isPlainObject(output)) {
      writeOutputPayload(output);
    }
  }
}

export function printRenderResult(result, { jsonOutput = false, stdout = process.stdout } = {}) {
  if (jsonOutput) {
    stdout.write(`${JSON.stringify(result, null, 2)}\n`);
    return;
  }
  if (Array.isArray(result.jobs)) {
    for (const jobResult of result.jobs) {
      if (isPlainObject(jobResult)) {
        printRenderResult(jobResult, { jsonOutput: false, stdout });
      }
    }
    return;
  }
  const outputs = Array.isArray(result.outputs) ? result.outputs : null;
  if (!outputs) {
    stdout.write(`${JSON.stringify(result, null, 2)}\n`);
    return;
  }
  for (const output of outputs) {
    if (isPlainObject(output) && output.path) {
      stdout.write(`saved snapshot: ${output.path}\n`);
    }
  }
}

export async function runRenderCli(argv, {
  cwd = process.cwd(),
  stdin = process.stdin,
  stdout = process.stdout,
  stderr = process.stderr,
} = {}) {
  try {
    const options = parseSnapshotArgs(argv);
    if (options.help) {
      stdout.write(helpText());
      return 0;
    }
    const rawPayload = await loadJobFromOptions(options, { stdin, cwd });
    const packet = resolveRenderJobPacket(rawPayload, { cwd });
    const result = await renderResolvedJobPacket(packet);
    writeRenderOutputs(result);
    printRenderResult(result, { jsonOutput: options.json, stdout });
    return 0;
  } catch (error) {
    stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    return 1;
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  runRenderCli(process.argv.slice(2)).then((status) => {
    process.exitCode = status;
  });
}

export const snapshotCliModuleUrl = pathToFileURL(fileURLToPath(import.meta.url)).href;
