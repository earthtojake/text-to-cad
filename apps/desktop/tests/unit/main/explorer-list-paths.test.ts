/**
 * `listPaths` reads directories ahead of the one it is taking apart, and
 * still answers exactly what the one-`readdir`-per-await walk it replaced did
 * — including which paths a capped walk keeps. That walk is kept, as it was,
 * in `list-paths-reference.ts`. How much faster the read-ahead is, is not
 * asserted here: a timing in the unit suite is a lie on a loaded runner. It is
 * measured by hand with `scripts/bench/explorer-list-paths/list-paths.mjs`.
 */
import { afterAll, beforeAll, expect, it } from "vitest";

import { listPaths } from "@main/explorer/fs";
import { serialListPaths, writeProjectTree } from "./list-paths-reference";
import { cleanTempDirs, tempDir } from "./temp-dirs";

let root: string;

beforeAll(async () => {
  root = await tempDir("text-to-cad-list-paths-");
  await writeProjectTree(root);
});

afterAll(() => cleanTempDirs());

it("answers what the serial walk answered, whole and capped", async () => {
  const whole = await listPaths(root);
  expect(whole.paths.length).toBe(250 * 16 + 20 * 10);
  expect(whole).toEqual(await serialListPaths(root));

  // A cap inside the project content, and one inside the dependency cache:
  // the same paths are kept, because directories are still consumed in the
  // order they were found.
  for (const limit of [1_234, 4_100]) {
    const capped = await listPaths(root, "", { limit });
    expect(capped.truncated).toBe(true);
    expect(capped).toEqual(await serialListPaths(root, limit));
  }
});
