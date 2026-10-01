/**
 * `settings.fallbacks`: what the Settings pages say about a stored value that
 * is not the one in effect.
 *
 * Two different things, kept apart because the rows word them differently: a
 * `refused` value main could not parse (or git refuses) and read as the
 * default, and a remembered folder that parses fine but is `gone`. A stored
 * value of the wrong type is the first; it must never surface as the second,
 * whose note says the folder no longer exists. `gone` carries why: a path
 * that is now a file is not a folder that can be made again, and its note
 * says so.
 */
import { stat } from "node:fs/promises";

import { settings } from "../db/repositories";
import { existingPath } from "./dialogs";

/** `missing`: nothing at the path. `file`: something is, and it is not a folder, so no folder is made there either. */
export type GoneReason = "missing" | "file";

export async function settingsFallbacks(): Promise<{
  refused: Record<string, string>;
  gone: Record<string, { path: string; reason: GoneReason }>;
}> {
  // `get` has already read a wrong-typed folder as null, so only a real,
  // well-formed path is stat'ed.
  const stored = settings.get();
  const gone: Record<string, { path: string; reason: GoneReason }> = {};
  for (const key of ["defaultProjectFolder", "worktreeRoot"] as const) {
    const folder = stored[key];
    if (folder && (await existingPath(folder, { directory: true })) === undefined) {
      gone[key] = { path: folder, reason: (await stat(folder).then(() => true, () => false)) ? "file" : "missing" };
    }
  }
  return { refused: settings.fallbacks(), gone };
}
