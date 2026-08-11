import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const viewerSrcRoot = path.dirname(fileURLToPath(import.meta.url));
const selfPath = fileURLToPath(import.meta.url);

function collectSourceFiles(directory, files = []) {
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const entryPath = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      collectSourceFiles(entryPath, files);
    } else if (/\.[cm]?jsx?$/u.test(entry.name)) {
      files.push(entryPath);
    }
  }
  return files;
}

test("viewer imports implicit CAD APIs through cadjs/implicit/*, never implicitjs directly", () => {
  // The viewer installs cadjs alone; implicitjs arrives transitively and its
  // APIs are consumed via the cadjs/implicit/* re-export layer (AGENTS.md).
  // A bare `implicitjs` import still resolves through the hoisted transitive
  // link, so nothing else fails loudly when one sneaks in (e.g. via a merge
  // from a branch that predates the re-export layer) — this test is the fence.
  const offenders = [];
  for (const filePath of collectSourceFiles(viewerSrcRoot)) {
    if (filePath === selfPath) {
      continue;
    }
    const source = fs.readFileSync(filePath, "utf8");
    if (/["']implicitjs(?:\/[^"']*)?["']/u.test(source)) {
      offenders.push(path.relative(viewerSrcRoot, filePath));
    }
  }
  assert.deepEqual(
    offenders,
    [],
    `viewer sources must import cadjs/implicit/* instead of implicitjs directly: ${offenders.join(", ")}`
  );
});
