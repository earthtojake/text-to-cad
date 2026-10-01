/**
 * Does a project root hold a CAD model near its top? Answers "is a viewer worth
 * starting before anyone asks": `warmCad` runs on every session bind, and a
 * project of prose or code has nothing for a `cadgen viewer` to serve. Looks
 * breadth-first, `MAX_DEPTH` folders down and at most `MAX_DIRECTORIES`
 * listings, so a shallow model is found at once and a build tree costs a
 * bounded scan. This repository's own models sit three folders down
 * (`models/examples/imported/`). A model deeper than that, or written later,
 * gets its viewer when its tab opens, which is what `cad.viewerOrigin` is for.
 */
import fs from "node:fs/promises";
import path from "node:path";

/**
 * The files the viewer client opens: core's `isCadFile` set (`RENDER_FORMAT`
 * and its `stp`/`gltf` spellings) — STEP, the meshes, DXF and the robot
 * descriptions. Main does not import core, so `has-cad-file.test.ts` pins this
 * list to it.
 */
export const CAD_FILE = /\.(?:step|stp|stl|3mf|glb|gltf|dxf|urdf|srdf|sdf)$/i;
const SKIPPED_DIRECTORIES = new Set(["node_modules"]);
const MAX_DEPTH = 3;
const MAX_DIRECTORIES = 400;

export async function hasCadFile(root: string): Promise<boolean> {
  let level = [root];
  let listed = 0;
  for (let depth = 0; depth <= MAX_DEPTH && level.length > 0; depth += 1) {
    const next: string[] = [];
    for (const directory of level) {
      if (listed >= MAX_DIRECTORIES) {
        return false;
      }
      listed += 1;
      const entries = await fs.readdir(directory, { withFileTypes: true }).catch(() => []);
      if (entries.some((entry) => !entry.isDirectory() && CAD_FILE.test(entry.name))) {
        return true;
      }
      for (const entry of entries) {
        if (entry.isDirectory() && !entry.name.startsWith(".") && !SKIPPED_DIRECTORIES.has(entry.name)) {
          next.push(path.join(directory, entry.name));
        }
      }
    }
    level = next;
  }
  return false;
}
