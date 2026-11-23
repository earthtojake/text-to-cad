// The scene's blues are written once (`@cad/core/lib/viewportTheme.js`): no 3D view spells one again.
import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import { join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { SCENE_COLORS } from "@cad/core/lib/viewportTheme.js";

const ROOTS = ["..", "../../../../../core/src/common", "../../../../../core/src/lib/viewer"].map(path => fileURLToPath(new URL(path, import.meta.url)));
const BLUES = [SCENE_COLORS.selected, SCENE_COLORS.selectedFill, SCENE_COLORS.hover, SCENE_COLORS.selectedEdge, "41, 121, 255"];

async function sources(dir) {
  const found = [];
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) found.push(...await sources(path));
    else if (/\.(jsx?|mjs)$/u.test(entry.name) && !/\.test\./u.test(entry.name)) found.push(path);
  }
  return found;
}

test("no 3D view hard-codes a selection, hover or box blue: each is lib/viewportTheme.js's", async () => {
  const stray = [];
  for (const root of ROOTS) for (const file of await sources(root)) {
    const text = (await readFile(file, "utf8")).toLowerCase();
    for (const blue of BLUES) if (text.includes(blue)) stray.push(`${file}: ${blue}`);
  }
  assert.deepEqual(stray, []);
});
