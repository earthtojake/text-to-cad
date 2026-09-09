// bin/mesh-export.mjs end-to-end: a real render package (assembly.json + a
// surf fixture) exports to every format, byte-deterministically, through the
// component mesh cache (design/unified-tessellation.md Phases 3-4).
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const CLI = path.join(HERE, "..", "..", "..", "bin", "mesh-export.mjs");
const FIXTURE_SURF = path.join(HERE, "..", "surf", "fixtures", "sun_gear.surf");

function makePackage(t) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "mesh-export-")));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const packageDir = path.join(root, "pkg");
  fs.mkdirSync(path.join(packageDir, "components"), { recursive: true });
  fs.copyFileSync(FIXTURE_SURF, path.join(packageDir, "components", "c0.surf"));
  const descriptor = {
    kind: "assembly-package",
    components: { c0: { surf: "components/c0.surf" } },
    occurrences: [
      { id: "o1.1", name: "gear", component: "c0",
        transform: [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1] },
      { id: "o1.2", name: "gear", component: "c0", color: [0.8, 0.1, 0.1, 1],
        transform: [1, 0, 0, 40, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1] },
      // A MIDTONE occurrence: 0 and 1 are fixed points of the sRGB transfer
      // function, so a package of saturated primaries cannot tell a correct
      // linear -> sRGB encoding from no encoding at all. Linear 0.5 can.
      { id: "o1.3", name: "gear", component: "c0", color: [0.5, 0.5, 0.5, 1],
        transform: [1, 0, 0, 80, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1] },
    ],
  };
  fs.writeFileSync(path.join(packageDir, "assembly.json"), JSON.stringify(descriptor));
  return { root, packageDir };
}

// The mesh cache must land INSIDE the sandbox on every platform, or these
// tests read (and pollute) the runner's real user cache. cadgenCacheRootDir
// consults, in order: CADGEN_CACHE_DIR, then XDG_CACHE_HOME (POSIX) or
// LOCALAPPDATA (Windows), then os.homedir()/.cache/cadgen. Blanking the first
// three and pointing the home at the sandbox leaves ONE resolution -- the
// platform default -- and puts it at <root>/.cache/cadgen on both. os.homedir()
// reads HOME on POSIX and USERPROFILE on Windows, hence both.
function sandboxEnv(root) {
  return { HOME: root, USERPROFILE: root, LOCALAPPDATA: "" };
}

// Where the CLI's tessellation cache lands under sandboxEnv(root).
function meshCacheDir(root) {
  return path.join(root, ".cache", "cadgen", "meshes");
}

function runCli(cliArgs, env = {}) {
  return spawnSync(process.execPath, [CLI, ...cliArgs], {
    encoding: "utf-8",
    env: { ...process.env, CADGEN_CACHE_DIR: "", XDG_CACHE_HOME: "", ...env },
  });
}

test("exports every format from one package, byte-deterministically", (t) => {
  const { root, packageDir } = makePackage(t);
  const env = sandboxEnv(root);
  let triangleCount = null;
  for (const format of ["stl", "glb", "3mf"]) {
    const out = path.join(root, `first.${format}`);
    const result = runCli(
      ["--package-dir", packageDir, "--format", format, "--out", out, "--name", "gear"], env);
    assert.equal(result.status, 0, result.stdout + result.stderr);
    const payload = JSON.parse(result.stdout);
    assert.equal(payload.ok, true);
    assert.equal(payload.files.length, 1);
    assert.equal(payload.files[0].path, out);
    assert.equal(payload.files[0].format, format);
    assert.ok(payload.files[0].triangleCount > 100, `${format}: ${payload.files[0].triangleCount} triangles`);
    triangleCount = triangleCount ?? payload.files[0].triangleCount;
    assert.equal(payload.files[0].triangleCount, triangleCount, "same mesh across formats");

    // Second export: cache hit, identical bytes.
    const again = path.join(root, `second.${format}`);
    const rerun = runCli(
      ["--package-dir", packageDir, "--format", format, "--out", again, "--name", "gear"], env);
    assert.equal(rerun.status, 0, rerun.stdout + rerun.stderr);
    assert.deepEqual(fs.readFileSync(again), fs.readFileSync(out), `${format} bytes differ`);
  }
  const cacheEntries = fs.readdirSync(meshCacheDir(root));
  assert.equal(cacheEntries.length, 1, "one unique component, one cache entry");
  assert.match(cacheEntries[0], /^c0-t\d+-l[0-9.e+-]+-a[0-9.e+-]+\.tess$/);
});

test("every occurrence lands in the mesh: distinct transforms, distinct colors", (t) => {
  const { root, packageDir } = makePackage(t);
  const out = path.join(root, "pair.glb");
  const result = runCli(
    ["--package-dir", packageDir, "--format", "glb", "--out", out],
    { ...sandboxEnv(root), CADGEN_MESH_CACHE: "0" },
  );
  assert.equal(result.status, 0, result.stdout + result.stderr);
  const bytes = fs.readFileSync(out);
  const jsonLength = bytes.readUInt32LE(12);
  const gltf = JSON.parse(bytes.subarray(20, 20 + jsonLength).toString("utf8"));
  // Uncolored occurrence -> default; colored occurrences -> their own material.
  // baseColorFactor is linear-space per glTF, so a descriptor colour (also
  // linear) must come back out UNCHANGED: encode to sRGB hex once on the way
  // in, decode once on the way out.
  assert.equal(gltf.materials.length, 3);
  const linearToSrgb = (c) =>
    Math.round((c <= 0.0031308 ? c * 12.92 : 1.055 * c ** (1 / 2.4) - 0.055) * 255);
  const factors = gltf.materials
    .map((m) => m.pbrMetallicRoughness.baseColorFactor.slice(0, 3))
    .sort((a, b) => b[0] - a[0] || b[1] - a[1]);
  // Descriptor [0.8, 0.1, 0.1] linear -> #e75959 -> back to linear.
  assert.deepEqual(factors[0].map(linearToSrgb), [231, 89, 89]);
  // The default #d4d4d8 is AUTHORED sRGB, not a linear colour: it passes
  // through the hex slot unconverted and must still read back as itself.
  assert.deepEqual(factors[1].map(linearToSrgb), [212, 212, 216]);
  // The midtone: linear 0.5 -> #bcbcbc -> ~0.5 again, not 0.214.
  assert.deepEqual(factors[2].map(linearToSrgb), [188, 188, 188]);
  for (const channel of factors[2]) {
    assert.ok(Math.abs(channel - 0.5) < 0.004, `linear midtone must survive: ${channel}`);
  }
  // Cache disabled: no cache dir appears.
  assert.equal(fs.existsSync(meshCacheDir(root)), false);
});

test("3MF displaycolor carries sRGB bytes, not the raw linear floats", (t) => {
  const { root, packageDir } = makePackage(t);
  const out = path.join(root, "colors.3mf");
  assert.equal(
    runCli(["--package-dir", packageDir, "--format", "3mf", "--out", out], sandboxEnv(root)).status,
    0,
  );
  // Stored (uncompressed) zip entries, so the model XML is readable as-is.
  const text = fs.readFileSync(out).toString("latin1");
  assert.match(text, /displaycolor="#E75959FF"/, "linear [0.8,0.1,0.1] -> sRGB #E75959");
  assert.match(text, /displaycolor="#BCBCBCFF"/, "linear 0.5 -> sRGB #BCBCBC, not #808080");
  assert.doesNotMatch(text, /displaycolor="#CC1A1AFF"/, "the raw linear bytes must not appear");
});

test("cached and fresh tessellations export identical bytes", (t) => {
  const { root, packageDir } = makePackage(t);
  const cold = path.join(root, "cold.stl");
  const warm = path.join(root, "warm.stl");
  const uncached = path.join(root, "uncached.stl");
  const env = sandboxEnv(root);
  const base = ["--package-dir", packageDir, "--format", "stl", "--name", "gear", "--out"];
  assert.equal(runCli([...base, cold], env).status, 0);
  assert.equal(runCli([...base, warm], env).status, 0);
  assert.equal(runCli([...base, uncached], { ...env, CADGEN_MESH_CACHE: "0" }).status, 0);
  const coldBytes = fs.readFileSync(cold);
  assert.deepEqual(fs.readFileSync(warm), coldBytes, "cache round-trip must be lossless");
  assert.deepEqual(fs.readFileSync(uncached), coldBytes, "cache must not change output");
});

test("tolerance overrides change the cache key and the mesh density", (t) => {
  const { root, packageDir } = makePackage(t);
  const env = sandboxEnv(root);
  const fine = path.join(root, "fine.stl");
  const coarse = path.join(root, "coarse.stl");
  assert.equal(
    runCli(["--package-dir", packageDir, "--format", "stl", "--out", fine,
      "--chord-tolerance", "5e-4"], env).status,
    0,
  );
  assert.equal(
    runCli(["--package-dir", packageDir, "--format", "stl", "--out", coarse,
      "--chord-tolerance", "5e-3"], env).status,
    0,
  );
  const triangles = (file) => fs.readFileSync(file).readUInt32LE(80);
  assert.ok(triangles(fine) > triangles(coarse),
    `finer tolerance must mean more triangles (${triangles(fine)} vs ${triangles(coarse)})`);
  const cacheEntries = fs.readdirSync(meshCacheDir(root));
  assert.equal(cacheEntries.length, 2, "distinct tolerances, distinct cache entries");
});

test("one invocation serializes every format from one tessellation", (t) => {
  const { root, packageDir } = makePackage(t);
  const env = sandboxEnv(root);
  const outs = { stl: path.join(root, "multi.stl"), glb: path.join(root, "multi.glb"), "3mf": path.join(root, "multi.3mf") };
  const result = runCli(
    ["--package-dir", packageDir, "--name", "gear",
      "--format", "stl", "--out", outs.stl,
      "--format", "glb", "--out", outs.glb,
      "--format", "3mf", "--out", outs["3mf"]],
    env,
  );
  assert.equal(result.status, 0, result.stdout + result.stderr);
  const payload = JSON.parse(result.stdout);
  assert.equal(payload.ok, true);
  assert.deepEqual(payload.files.map((f) => f.format), ["stl", "glb", "3mf"], "pair order preserved");
  for (const file of payload.files) {
    assert.equal(file.path, outs[file.format]);
    assert.ok(fs.existsSync(file.path), `${file.format} written`);
    assert.equal(file.triangleCount, payload.files[0].triangleCount, "one mesh for all formats");
  }
  // Byte parity with the single-format contract: same package, same bytes.
  const single = path.join(root, "single.stl");
  assert.equal(
    runCli(["--package-dir", packageDir, "--name", "gear", "--format", "stl", "--out", single], env).status,
    0,
  );
  assert.deepEqual(fs.readFileSync(outs.stl), fs.readFileSync(single), "multi-pair stl matches single-pair stl");
});

test("failures are one JSON error line: bad args, bad package", (t) => {
  const { root, packageDir } = makePackage(t);
  for (const cliArgs of [
    ["--package-dir", "relative/pkg", "--format", "stl", "--out", path.join(root, "x.stl")],
    ["--package-dir", packageDir, "--format", "obj", "--out", path.join(root, "x.obj")],
    ["--package-dir", packageDir, "--format", "stl", "--out", "relative.stl"],
    ["--package-dir", path.join(root, "nope"), "--format", "stl", "--out", path.join(root, "x.stl")],
    // Pair mismatches: an extra --format, and two pairs sharing one --out.
    ["--package-dir", packageDir, "--format", "stl", "--format", "glb", "--out", path.join(root, "x.stl")],
    ["--package-dir", packageDir, "--format", "stl", "--out", path.join(root, "x.stl"),
      "--format", "glb", "--out", path.join(root, "x.stl")],
  ]) {
    const result = runCli(cliArgs, sandboxEnv(root));
    assert.equal(result.status, 1, cliArgs.join(" "));
    const payload = JSON.parse(result.stdout);
    assert.equal(payload.ok, false);
    assert.ok(payload.error);
  }
});

// --- animation: a package plus the render module beside its document ---------
//
// The end-to-end claim, made against a real package and a real .step.js: the
// clip in that module comes back out of the finished .glb as glTF animation a
// stock loader plays, on a node per occurrence, at the schedule that was asked
// for. Everything between (the module loader, the sampler, the writer) is
// pinned by its own unit tests; this is the one that proves they meet.

/** A render module beside the package, rotating ONE of the two occurrences. */
function writeRenderModule(root) {
  const modulePath = path.join(root, "gear.step.js");
  fs.writeFileSync(modulePath, [
    "export const clips = {",
    "  showcase: {",
    "    label: \"Showcase\",",
    "    duration: 4,",
    "    update(t, m) {",
    "      m.get(\"#o1.2\").rotate([0, 0, 1], 90 * (t / 4), [40, 0, 0]);",
    "    },",
    "  },",
    "};",
    "",
  ].join("\n"));
  return modulePath;
}

async function parseAnimatedGlb(file) {
  const { GLTFLoader } = await import("three/examples/jsm/loaders/GLTFLoader.js");
  const bytes = fs.readFileSync(file);
  const copy = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
  return new Promise((resolve, reject) => new GLTFLoader().parse(copy, "", resolve, reject));
}

test("--animation writes the clip into the GLB as glTF animation", async (t) => {
  const { root, packageDir } = makePackage(t);
  const modulePath = writeRenderModule(root);
  const out = path.join(root, "animated.glb");
  const result = runCli([
    "--package-dir", packageDir, "--name", "gear",
    "--format", "glb", "--out", out,
    "--animation", JSON.stringify({ clip: "showcase", fps: 10, seconds: 2 }),
    "--render-module", modulePath,
  ], sandboxEnv(root));
  assert.equal(result.status, 0, result.stdout + result.stderr);
  const payload = JSON.parse(result.stdout);
  assert.deepEqual(payload.files[0].animation, {
    clip: "showcase", fps: 10, samples: 20, seconds: 2, start: 0, channels: 1, warnings: [],
  });

  const gltf = await parseAnimatedGlb(out);
  assert.equal(gltf.animations.length, 1);
  const [clip] = gltf.animations;
  assert.equal(clip.name, "showcase");
  // 20 samples at 10 fps: the last one sits at 1.9s, one interval before 2s, so
  // a looping clip does not render its first frame twice.
  assert.ok(Math.abs(clip.duration - 1.9) < 1e-5, `duration ${clip.duration}`);
  for (const track of clip.tracks) {
    assert.equal(track.times.length, 20);
  }
  // Position AND quaternion, because the rotation is about a pivot 40 mm off the
  // origin: a channel carrying only the quaternion would spin the part in place.
  assert.deepEqual(
    clip.tracks.map((track) => track.name.split(".").pop()).sort(),
    ["position", "quaternion"],
  );

  // One node per OCCURRENCE — the fixture's three occurrences all share the
  // display name "gear", so identity is the cadOccurrenceId extra, which is
  // also what the clip's "#o1.2" target resolved against.
  const occurrenceIds = [];
  gltf.scene.traverse((node) => {
    if (node.isMesh) {
      occurrenceIds.push(node.userData.cadOccurrenceId);
    }
  });
  assert.deepEqual(occurrenceIds.sort(), ["o1.1", "o1.2", "o1.3"]);
  // ...and only the moving one is animated: both tracks name the same node.
  const animated = new Set(clip.tracks.map((track) => track.name.split(".")[0]));
  assert.equal(animated.size, 1);
  assert.equal(
    gltf.scene.getObjectByName([...animated][0]).userData.cadOccurrenceId,
    "o1.2",
  );
});

test("an animated export refuses what it cannot carry, by name", (t) => {
  const { root, packageDir } = makePackage(t);
  const modulePath = writeRenderModule(root);
  const out = path.join(root, "refused.glb");
  const base = ["--package-dir", packageDir, "--render-module", modulePath];
  const cases = [
    // A clip the module does not declare, named against the ones it does.
    [{ clip: "nope" }, "glb", /Unknown animation clip: nope/],
    // fps outside the schedule's bounds.
    [{ clip: "showcase", fps: 0 }, "glb", /animation fps must be/],
    // A format with nowhere to put a clip.
    [{ clip: "showcase" }, "stl", /carries no animation/],
  ];
  for (const [request, format, expected] of cases) {
    const result = runCli([
      ...base, "--format", format, "--out", path.join(root, `refused.${format}`),
      "--animation", JSON.stringify(request),
    ], sandboxEnv(root));
    assert.equal(result.status, 1, JSON.stringify(request));
    const payload = JSON.parse(result.stdout);
    assert.equal(payload.ok, false);
    assert.match(payload.error, expected);
  }
  assert.equal(fs.existsSync(out), false, "a refused export writes nothing");
});

test("--animation without --render-module is refused: the clips live in the .step.js", (t) => {
  const { root, packageDir } = makePackage(t);
  const result = runCli([
    "--package-dir", packageDir, "--format", "glb", "--out", path.join(root, "x.glb"),
    "--animation", JSON.stringify({ clip: "showcase" }),
  ], sandboxEnv(root));
  assert.equal(result.status, 1);
  assert.match(JSON.parse(result.stdout).error, /--animation needs --render-module/);
});

test("a reveal clip — hidden at start AND moving — exports with a warning, not a writer error", async (t) => {
  // The shape the visibility refusal's own escape hatch used to break on:
  // `drop: ["visible"]` omits the occurrence's primitives, so a channel for it
  // targets a node no primitive declared and writeGlb aborts the whole export
  // with a glTF invariant. It has to come out the other end as a file, with the
  // lost motion said out loud.
  const { root, packageDir } = makePackage(t);
  const modulePath = path.join(root, "reveal.step.js");
  fs.writeFileSync(modulePath, [
    "export const clips = {",
    "  reveal: {",
    "    duration: 4,",
    "    update(t, m) {",
    "      const cover = m.get(\"#o1.2\");",
    "      cover.visible(t > 1);",
    "      cover.translate([10 * t, 0, 0]);",
    "    },",
    "  },",
    "};",
    "",
  ].join("\n"));
  const out = path.join(root, "reveal.glb");
  const result = runCli([
    "--package-dir", packageDir, "--name", "gear",
    "--format", "glb", "--out", out,
    "--animation", JSON.stringify({ clip: "reveal", fps: 10, seconds: 2, drop: ["visible"] }),
    "--render-module", modulePath,
  ], sandboxEnv(root));
  assert.equal(result.status, 0, result.stdout + result.stderr);
  const { animation } = JSON.parse(result.stdout).files[0];
  assert.equal(animation.channels, 0, "the hidden occurrence's motion is not carried");
  assert.match(
    animation.warnings.join("\n"),
    /o1\.2 moves in this clip and is hidden at start/,
  );

  const gltf = await parseAnimatedGlb(out);
  // No channels means no animation at all in the file, and the hidden
  // occurrence's geometry is gone with it.
  assert.equal(gltf.animations.length, 0);
  const occurrenceIds = [];
  gltf.scene.traverse((node) => {
    if (node.isMesh) occurrenceIds.push(node.userData.cadOccurrenceId);
  });
  assert.deepEqual(occurrenceIds.sort(), ["o1.1", "o1.3"]);
});

// --- deform: "morph" --------------------------------------------------------
//
// The end-to-end claim for a DEFORMING tube, which is per-vertex motion no node
// transform carries: what a stock GLTFLoader blends out of the finished file at
// a given moment is where the render module's own deformation puts those
// vertices at that same moment. Everything between — the fit, the delta bake,
// the colour partitioning, the change of basis, the weights schedule — is
// pinned by its own unit tests; this is the one that proves they meet.

/** A render module whose clip BENDS the first gear off a straight rest line. */
function writeDeformingModule(root) {
  const modulePath = path.join(root, "gear-flex.step.js");
  fs.writeFileSync(modulePath, [
    "const REST = { normal: [0, 0, 1], segments: [",
    "  { kind: \"line\", start: [-30, 0, 4], end: [30, 0, 4] },",
    "] };",
    "function bent(sweepDeg) {",
    "  if (Math.abs(sweepDeg) < 1e-9) return REST;",
    "  const lead = -30 + 60 * 0.25;",
    "  const radius = (30 - lead) / (Math.abs(sweepDeg) * Math.PI / 180);",
    "  const sign = Math.sign(sweepDeg);",
    "  return { normal: [0, 0, 1], segments: [",
    "    { kind: \"line\", start: [-30, 0, 4], end: [lead, 0, 4] },",
    "    { kind: \"arc\", center: [lead, sign * radius, 4], axis: [0, 0, 1],",
    "      start: [lead, 0, 4], sweepDeg },",
    "  ] };",
    "}",
    "export const clips = {",
    "  flex: {",
    "    duration: 2,",
    "    update(t, m) {",
    "      m.get(\"#o1.1\").deformTube({",
    "        rest: REST, path: bent(6 * Math.sin((t / 2) * Math.PI * 2)), maxSegmentLength: 6,",
    "      });",
    "    },",
    "  },",
    "};",
    "",
  ].join("\n"));
  return modulePath;
}

/** What the RENDER MODULE puts those vertices at, in the file's own space. */
async function renderModuleWorldPositions(root, moduleSource, timeSec) {
  const THREE = await import("three");
  const { parseSurf } = await import("../surf/container.js");
  const { DEFAULT_OPTIONS, tessellateComponent } = await import("../surf/tessellate.js");
  const { applyRecordTubeDeformation } = await import("../../common/tubeDeformation.js");
  const { evaluateAnimationClip, normalizeAnimationClips } = await import("../../common/animationRuntime.js");
  const { importRenderModule } = await import("../../common/renderModule.js");
  const { animationTargetsFromDescriptor } = await import("./packageAnimation.js");

  const bytes = fs.readFileSync(FIXTURE_SURF);
  const { index, floats } = parseSurf(
    bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength),
  );
  const tessellation = tessellateComponent(index, floats, { ...DEFAULT_OPTIONS });
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(Float32Array.from(tessellation.positions), 3));
  geometry.setAttribute("normal", new THREE.BufferAttribute(Float32Array.from(tessellation.normals), 3));
  const flat = [];
  for (const range of tessellation.faceRanges) {
    for (let k = range.indexStart; k + 2 < range.indexStart + range.indexCount; k += 3) {
      flat.push(tessellation.indices[k], tessellation.indices[k + 1], tessellation.indices[k + 2]);
    }
  }
  geometry.setIndex(new THREE.BufferAttribute(Uint32Array.from(flat), 1));

  const namespace = await importRenderModule(moduleSource, { name: "gear-flex.step.js" });
  const clip = normalizeAnimationClips(namespace.clips).flex;
  const descriptor = JSON.parse(fs.readFileSync(path.join(root, "pkg", "assembly.json"), "utf8"));
  const frame = evaluateAnimationClip(
    THREE, animationTargetsFromDescriptor(descriptor), clip, timeSec,
  );
  const record = {
    mesh: { geometry, material: { userData: {} }, userData: {} },
    material: { userData: {} },
  };
  applyRecordTubeDeformation(THREE, record, frame.deformations.get("o1.1"));
  const position = record.mesh.geometry.attributes.position;
  const out = new Float64Array(position.count * 3);
  for (let i = 0; i < position.count; i += 1) {
    // CAD Z-up millimetres -> glTF Y-up metres, the export's own change of basis.
    out[i * 3] = position.getX(i) * 0.001;
    out[i * 3 + 1] = position.getZ(i) * 0.001;
    out[i * 3 + 2] = -position.getY(i) * 0.001;
  }
  return out;
}

/** Every point of `a` to its nearest neighbour in `b`, in millimetres. */
function cloudDistanceMm(a, b) {
  const cell = 0.004;
  const grid = new Map();
  const key = (x, y, z) => `${Math.floor(x / cell)},${Math.floor(y / cell)},${Math.floor(z / cell)}`;
  for (let i = 0; i < b.length; i += 3) {
    const k = key(b[i], b[i + 1], b[i + 2]);
    let bucket = grid.get(k);
    if (!bucket) grid.set(k, (bucket = []));
    bucket.push(i);
  }
  let worst = 0;
  for (let i = 0; i < a.length; i += 3) {
    let best = Infinity;
    const c = [Math.floor(a[i] / cell), Math.floor(a[i + 1] / cell), Math.floor(a[i + 2] / cell)];
    for (let dx = -1; dx <= 1; dx += 1) {
      for (let dy = -1; dy <= 1; dy += 1) {
        for (let dz = -1; dz <= 1; dz += 1) {
          for (const j of grid.get(`${c[0] + dx},${c[1] + dy},${c[2] + dz}`) || []) {
            const d = (a[i] - b[j]) ** 2 + (a[i + 1] - b[j + 1]) ** 2 + (a[i + 2] - b[j + 2]) ** 2;
            if (d < best) best = d;
          }
        }
      }
    }
    if (best > worst) worst = best;
  }
  return Math.sqrt(worst) * 1000;
}

test('deform: "morph" bakes the deformation, and the file replays what the render module draws', async (t) => {
  const { root, packageDir } = makePackage(t);
  const modulePath = writeDeformingModule(root);
  const out = path.join(root, "flex.glb");
  const request = { clip: "flex", fps: 12, seconds: 2, deform: "morph", deformTolerance: 0.5 };
  const result = runCli([
    "--package-dir", packageDir, "--name", "gear",
    "--format", "glb", "--out", out,
    "--animation", JSON.stringify(request),
    "--render-module", modulePath,
  ], sandboxEnv(root));
  assert.equal(result.status, 0, result.stdout + result.stderr);
  const { animation } = JSON.parse(result.stdout).files[0];
  assert.equal(animation.deform.mode, "morph");
  assert.equal(animation.deform.nodes, 1);
  assert.ok(animation.deform.targets > 1, `${animation.deform.targets} targets`);
  assert.equal(animation.deform.toleranceMm, 0.5);
  assert.equal(animation.deform.fitGridHz, 96, "the fit measures 4x finer than the export's 12 fps, floored at 96");
  assert.ok(
    animation.deform.deviationMm <= 0.5 + 1e-3,
    `deviation ${animation.deform.deviationMm}mm past the 0.5mm asked for`,
  );

  const gltf = await parseAnimatedGlb(out);
  let deforming = null;
  gltf.scene.traverse((node) => {
    if (node.isMesh && node.userData.cadOccurrenceId === "o1.1") deforming = node;
  });
  assert.ok(deforming, "the deforming occurrence has a node");
  assert.equal(deforming.geometry.morphAttributes.position.length, animation.deform.targets);
  assert.equal(deforming.geometry.morphAttributes.normal.length, animation.deform.targets);
  assert.equal(deforming.geometry.morphTargetsRelative, true);

  const track = gltf.animations[0].tracks.find((entry) => entry.name.endsWith(".morphTargetInfluences"));
  assert.ok(track, "the clip carries a morph weights track");
  assert.equal(track.getValueSize(), animation.deform.targets);

  // Blend the file by hand at a moment that is NOT a keyframe, which is where a
  // per-keyframe bake would look perfect and be wrong.
  const blendAt = (timeSec) => {
    const size = track.getValueSize();
    let high = track.times.findIndex((value) => value >= timeSec);
    if (high < 0) high = track.times.length - 1;
    const low = Math.max(0, high - 1);
    const span = track.times[high] - track.times[low];
    const alpha = span > 0 ? (timeSec - track.times[low]) / span : 0;
    const base = deforming.geometry.attributes.position;
    const targets = deforming.geometry.morphAttributes.position;
    const out = new Float64Array(base.count * 3);
    for (let v = 0; v < base.count; v += 1) {
      out[v * 3] = base.getX(v);
      out[v * 3 + 1] = base.getY(v);
      out[v * 3 + 2] = base.getZ(v);
      for (let k = 0; k < targets.length; k += 1) {
        const weight = track.values[low * size + k] * (1 - alpha) + track.values[high * size + k] * alpha;
        if (!weight) continue;
        out[v * 3] += targets[k].getX(v) * weight;
        out[v * 3 + 1] += targets[k].getY(v) * weight;
        out[v * 3 + 2] += targets[k].getZ(v) * weight;
      }
    }
    return out;
  };

  const moduleSource = fs.readFileSync(modulePath, "utf8");
  // Moments deliberately BETWEEN the fit's own targets, which is where a bake at
  // the clip's keyframes looks perfect in a still and is wrong in motion.
  for (const moment of [0, 0.2917, 0.5, 1.1667, 1.9167]) {
    const truth = await renderModuleWorldPositions(root, moduleSource, moment);
    const actual = blendAt(moment);
    const worst = Math.max(cloudDistanceMm(actual, truth), cloudDistanceMm(truth, actual));
    assert.ok(
      worst <= 0.5 + 1e-3,
      `t=${moment}s: the file's morphed vertices are ${worst.toFixed(4)}mm off the render module's`,
    );
  }
});

test('deform: "morph" is what the default refusal now offers first', (t) => {
  const { root, packageDir } = makePackage(t);
  const modulePath = writeDeformingModule(root);
  const result = runCli([
    "--package-dir", packageDir,
    "--format", "glb", "--out", path.join(root, "refused.glb"),
    "--animation", JSON.stringify({ clip: "flex", fps: 8, seconds: 1 }),
    "--render-module", modulePath,
  ], sandboxEnv(root));
  assert.equal(result.status, 1);
  const { error } = JSON.parse(result.stdout);
  assert.match(error, /deforms tube geometry on o1\.1/);
  assert.match(error, /deform: "morph"/);
  assert.match(error, /deform: "rest"/);
});
