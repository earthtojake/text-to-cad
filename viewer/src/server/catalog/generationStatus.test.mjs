import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  generationStatusDir,
  isGenerationStatusPath,
  readGenerationStatus,
} from "./generationStatus.mjs";

function makeTempRepo() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "cad-generation-status-"));
}

function writeStatus(repoRoot, outputFile, name, payload) {
  const outputPath = path.join(repoRoot, outputFile);
  const statusPath = path.join(
    path.dirname(outputPath),
    `.${path.basename(outputPath)}.${name}.generation.lock.json`
  );
  fs.mkdirSync(path.dirname(statusPath), { recursive: true });
  fs.writeFileSync(statusPath, `${JSON.stringify(payload)}\n`);
  return statusPath;
}

test("readGenerationStatus reports running generator outputs relative to the viewer root", () => {
  const repoRoot = makeTempRepo();
  const updatedAt = new Date().toISOString();
  const payload = {
    schemaVersion: 1,
    id: "run-1",
    status: "running",
    pid: process.pid,
    startedAt: updatedAt,
    updatedAt,
    sourcePath: "models/part.py",
    generator: "gen_step",
    outputs: [
      { path: "models/part.step", kind: "step" },
      { path: "models/.part.step.glb", kind: "glb" },
      { path: "other/ignored.step", kind: "step" },
    ],
  };
  writeStatus(repoRoot, "models/part.step", "run-1", payload);
  writeStatus(repoRoot, "models/.part.step.glb", "run-1", payload);

  const status = readGenerationStatus({ repoRoot, rootDir: "models" });

  assert.deepEqual(Object.keys(status.files).sort(), [".part.step.glb", "part.step"]);
  assert.deepEqual(status.files["part.step"], {
    running: true,
    runId: "run-1",
    pid: process.pid,
    startedAt: updatedAt,
    updatedAt,
    sourcePath: "models/part.py",
    generator: "gen_step",
    kind: "step",
  });
  assert.deepEqual(status.runs[0].files.sort(), [".part.step.glb", "part.step"]);
});

test("readGenerationStatus resolves status-local relative paths", () => {
  const repoRoot = makeTempRepo();
  const updatedAt = new Date().toISOString();
  const payload = {
    schemaVersion: 1,
    id: "run-local",
    status: "running",
    pid: process.pid,
    startedAt: updatedAt,
    updatedAt,
    sourcePath: "../sources/part.py",
    generator: "gen_step",
    outputs: [
      { path: "part.step", kind: "step" },
      { path: ".part.step.glb", kind: "glb" },
    ],
  };
  writeStatus(repoRoot, "models/part.step", "run-local", payload);

  const status = readGenerationStatus({ repoRoot, rootDir: "models" });

  assert.deepEqual(Object.keys(status.files).sort(), [".part.step.glb", "part.step"]);
  assert.equal(status.files["part.step"].sourcePath, "sources/part.py");
  assert.deepEqual(status.runs[0].files.sort(), [".part.step.glb", "part.step"]);
});

test("readGenerationStatus ignores finished, dead, and stale generator markers", () => {
  const repoRoot = makeTempRepo();
  const nowMs = Date.parse("2026-05-27T10:00:00.000Z");
  writeStatus(repoRoot, "models/finished.step", "finished", {
    status: "finished",
    pid: process.pid,
    updatedAt: "2026-05-27T10:00:00.000Z",
    outputs: [{ path: "models/finished.step", kind: "step" }],
  });
  writeStatus(repoRoot, "models/dead.step", "dead", {
    status: "running",
    pid: 99999999,
    updatedAt: "2026-05-27T10:00:00.000Z",
    outputs: [{ path: "models/dead.step", kind: "step" }],
  });
  writeStatus(repoRoot, "models/stale.step", "stale", {
    status: "running",
    pid: process.pid,
    updatedAt: "2026-05-27T09:55:00.000Z",
    outputs: [{ path: "models/stale.step", kind: "step" }],
  });

  assert.deepEqual(readGenerationStatus({ repoRoot, rootDir: "models", nowMs }).files, {});
});

test("isGenerationStatusPath identifies local status files", () => {
  const repoRoot = makeTempRepo();
  assert.equal(
    isGenerationStatusPath(path.join(repoRoot, "models", ".part.step.run-1.generation.lock.json"), repoRoot),
    true
  );
  assert.equal(isGenerationStatusPath(path.join(repoRoot, "models", "part.step"), repoRoot), false);
});
