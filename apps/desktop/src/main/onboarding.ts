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

export const SAMPLE_FOLDER_NAME = "Hardcore Sample";

export function onboardingEnabled(env: NodeJS.ProcessEnv = process.env): boolean {
  return env.NODE_ENV !== "test" || env.HARDCORE_ONBOARDING === "1";
}

/**
 * The sample's folder, copied from the bundle the first time. A folder that
 * already has files in it is the person's from an earlier run, and is
 * reused as it is rather than overwritten.
 */
export function createSampleProject(
  target = path.join(app.getPath("documents"), SAMPLE_FOLDER_NAME),
  source = path.join(resourcesDir(), "sample"),
): string {
  const existing = fs.existsSync(target) ? fs.readdirSync(target) : [];
  if (existing.length > 0) {
    return target;
  }
  if (!fs.existsSync(source)) {
    throw new Error(`The sample project is missing from this build (${source}).`);
  }
  fs.cpSync(source, target, { recursive: true });
  return target;
}
