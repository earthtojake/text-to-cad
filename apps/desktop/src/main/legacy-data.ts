import fs from "node:fs";
import path from "node:path";

/**
 * The rename's one loose end. Until 0.7.0 the app was Hardcore, and its data —
 * the sessions database, the explorer strips, the settings — lived in
 * `appData/Hardcore`. The renamed app reads `appData/text-to-cad`, which a
 * machine that ran the old app does not have, so its first launch would open
 * on an empty sidebar and every thread would look lost.
 *
 * So, once: if the new directory does not exist and the old one does, copy the
 * old one over before anything opens it. A copy, not a move — the old app may
 * still be installed, and it keeps working on its own data. After that the two
 * diverge; nothing is copied twice, because the new directory now exists.
 *
 * Returns what it did, for the log and for the test.
 */
export function migrateLegacyUserData(appData: string, options: { legacyName?: string; name?: string } = {}):
  "copied" | "present" | "none" {
  const legacy = path.join(appData, options.legacyName ?? "Hardcore");
  const current = path.join(appData, options.name ?? "text-to-cad");
  if (fs.existsSync(current)) return "present";
  if (!fs.existsSync(legacy) || !fs.statSync(legacy).isDirectory()) return "none";
  // `errorOnExist` so a directory that appeared between the check and the copy
  // (a second launch racing this one) is left alone rather than merged into.
  fs.cpSync(legacy, current, { recursive: true, errorOnExist: true, force: false });
  return "copied";
}
