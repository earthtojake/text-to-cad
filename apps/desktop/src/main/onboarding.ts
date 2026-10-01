/**
 * The first-run flow's main-side pieces: whether this run shows it, and the
 * sample project.
 *
 * The sample ships in `resources/sample/` (an extraResource, so it is
 * `Contents/Resources/sample` packaged) and is copied, never opened in place:
 * a signed bundle must not be written into, and the agent will edit it.
 */
import fs from "node:fs";
import path from "node:path";
import { app } from "electron";

import { resourcesDir } from "./app-paths";

export const SAMPLE_FOLDER_NAME = "text-to-cad Sample";

export function onboardingEnabled(env: NodeJS.ProcessEnv = process.env): boolean {
  return env.NODE_ENV !== "test" || env.TEXT_TO_CAD_ONBOARDING === "1";
}

/** What Finder and Explorer leave in a folder nobody put anything in. */
const OS_LITTER = new Set([".DS_Store", "Thumbs.db"]);

const RENAME_ATTEMPTS = 5;

/** A synchronous wait: the copy is synchronous, and a timer would not run inside it. */
function sleepSync(ms: number): void {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
}

/**
 * The sample's folder, copied from the bundle the first time. A folder that
 * already has files in it is the person's from an earlier run, and is
 * reused as it is rather than overwritten. A `.DS_Store` alone is not a file
 * anyone put there: that folder is empty, and the sample goes in.
 */
export function createSampleProject(
  target = path.join(app.getPath("documents"), SAMPLE_FOLDER_NAME),
  source = path.join(resourcesDir(), "sample"),
  pause: (ms: number) => void = sleepSync,
): string {
  const existing = (fs.existsSync(target) ? fs.readdirSync(target) : []).filter((name) => !OS_LITTER.has(name));
  if (existing.length > 0) {
    return target;
  }
  if (!fs.existsSync(source)) {
    throw new Error(`The sample project is missing from this build (${source}).`);
  }
  // Copied beside the target and renamed into place, so `target` holds files
  // only once it holds all of them: a copy that dies midway (disk full, the
  // app killed) leaves a `.copying` folder that the next run discards, not a
  // half-sample the check above would take for the person's own.
  const staging = `${target}.copying`;
  fs.rmSync(staging, { recursive: true, force: true });
  try {
    fs.cpSync(source, staging, { recursive: true });
    // Only litter is in `target` here; a rename onto a directory is refused
    // on Windows even when it is empty.
    fs.rmSync(target, { recursive: true, force: true });
    renameIntoPlace(staging, target, pause);
  } catch (error) {
    fs.rmSync(staging, { recursive: true, force: true });
    throw error;
  }
  return target;
}

/**
 * `renameSync` right after a copy often fails on Windows (EPERM, EBUSY) while
 * Defender or the indexer still holds handles in the new tree, though nothing
 * is wrong with the copy. Retried a few times; if the handles outlast that, the
 * staging tree is copied into place instead, and `target` is cleared again
 * should that copy die so a half-sample is never left for the next run to
 * take for the person's own.
 */
function renameIntoPlace(staging: string, target: string, pause: (ms: number) => void): void {
  for (let attempt = 1; attempt <= RENAME_ATTEMPTS; attempt += 1) {
    try {
      fs.renameSync(staging, target);
      return;
    } catch (error) {
      const code = (error as NodeJS.ErrnoException).code;
      if (code !== "EPERM" && code !== "EBUSY" && code !== "EACCES") {
        throw error;
      }
      if (attempt < RENAME_ATTEMPTS) {
        pause(50 * attempt);
      }
    }
  }
  try {
    fs.cpSync(staging, target, { recursive: true });
  } catch (error) {
    fs.rmSync(target, { recursive: true, force: true });
    throw error;
  }
  fs.rmSync(staging, { recursive: true, force: true });
}
