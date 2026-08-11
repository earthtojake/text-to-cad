import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const cli = path.join(path.dirname(fileURLToPath(import.meta.url)), "export.mjs");

function runCli(args, { cwd = process.cwd() } = {}) {
  return spawnSync(process.execPath, [cli, ...args], { cwd, encoding: "utf-8" });
}

function writeFixture() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "implicit-cad-cli-"));
  const input = path.join(dir, "orb.implicit.js");
  fs.writeFileSync(input, `
export default {
  schema: "implicit.js/0.1.0",
  name: "cli orb",
  bounds: [[-6, -6, -6], [6, 6, 6]],
  glsl: \`float sdf(vec3 p) { return length(p) - 4.0; }\`
};
`, "utf-8");
  return { dir, input };
}

test("export CLI writes every requested format beside the model", () => {
  const { dir, input } = writeFixture();
  const result = runCli([input, "--stl", "--3mf", "--glb", "--resolution", "10", "--json"]);
  assert.equal(result.status, 0, result.stderr);
  const payload = JSON.parse(result.stdout);
  assert.deepEqual(payload.files.map((file) => file.format), ["glb", "stl", "3mf"]);
  for (const file of payload.files) {
    assert.equal(path.dirname(file.output), dir);
    assert.equal(path.basename(file.output), `orb.${file.format}`);
    assert.equal(fs.statSync(file.output).size, file.bytes);
  }
  assert.ok(payload.triangleCount > 0);
});

test("export CLI resolves a per-format path against the working directory", () => {
  const { dir, input } = writeFixture();
  const cwd = fs.mkdtempSync(path.join(os.tmpdir(), "implicit-cad-cwd-"));
  const result = runCli([input, "--stl", "nested/mesh.stl", "--resolution", "10"], { cwd });
  assert.equal(result.status, 0, result.stderr);
  assert.equal(fs.existsSync(path.join(cwd, "nested", "mesh.stl")), true);
  assert.equal(fs.existsSync(path.join(dir, "orb.stl")), false);
});

test("export CLI exits 2 when no format flag is given", () => {
  const { input } = writeFixture();
  const result = runCli([input, "--resolution", "10"]);
  assert.equal(result.status, 2);
  assert.match(result.stderr, /at least one export format is required: --glb, --stl, --3mf/);
});

test("export CLI exits 2 on a format output with the wrong extension", () => {
  const { dir, input } = writeFixture();
  const result = runCli([input, "--stl", path.join(dir, "mesh.glb"), "--resolution", "10"]);
  assert.equal(result.status, 2);
  assert.match(result.stderr, /--stl output must end with \.stl/);
});

test("export CLI exits 1 on an export failure", () => {
  const result = runCli([path.join(os.tmpdir(), "missing-implicit-model.implicit.js"), "--stl"]);
  assert.equal(result.status, 1);
});
