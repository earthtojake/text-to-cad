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
