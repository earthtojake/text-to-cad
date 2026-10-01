import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, beforeEach, expect, it } from "vitest";

import { isCadFile, RENDER_FORMAT } from "@text-to-cad/core/lib/fileFormats.js";

import { CAD_FILE, hasCadFile } from "@main/cad/has-cad-file";

let root: string;
beforeEach(() => { root = mkdtempSync(path.join(tmpdir(), "has-cad-")); });
afterEach(() => { rmSync(root, { recursive: true, force: true }); });

const touch = (...parts: string[]) => {
  const file = path.join(root, ...parts);
  mkdirSync(path.dirname(file), { recursive: true });
  writeFileSync(file, "");
};

it("finds a model in the root or a few folders down, in any case", async () => {
  touch("README.md");
  expect(await hasCadFile(root)).toBe(false);
  touch("models", "examples", "imported", "Bracket.STEP");
  expect(await hasCadFile(root)).toBe(true);
});

it("does not look into dependency folders, hidden folders or past the depth bound", async () => {
  touch("node_modules", "pkg", "a.glb");
  touch("node_modules", "b.step");
  touch(".cache", "c.step");
  touch("a", "b", "c", "d", "deep.step");
  expect(await hasCadFile(root)).toBe(false);
  touch("part.glb");
  expect(await hasCadFile(root)).toBe(true);
});

it("is false for a root that does not exist", async () => {
  expect(await hasCadFile(path.join(root, "missing"))).toBe(false);
});

it("matches every file the viewer client renders, and only those", () => {
  expect(CAD_FILE.test("a.stl")).toBe(true);
  expect(CAD_FILE.test("a.DXF")).toBe(true);
  expect(CAD_FILE.test("robot.urdf")).toBe(true);
  // Pinned to core's own answer, over every format it names plus the aliases and some non-models.
  const extensions = [...Object.values(RENDER_FORMAT), "stp", "gltf", "md", "ts", "png", "pdf", "json", "step.bak"];
  for (const extension of extensions) {
    expect(CAD_FILE.test(`part.${extension}`), extension).toBe(isCadFile(`part.${extension}`));
  }
});

it("finds a project whose only model is a DXF, STL or URDF", async () => {
  touch("part.dxf");
  expect(await hasCadFile(root)).toBe(true);
});
