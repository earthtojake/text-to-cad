import { readdirSync } from "node:fs";
import path from "node:path";

/** Every file under `dir`, recursively, whose name matches `match`. */
export function sourceFiles(dir: string, match: RegExp): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) return sourceFiles(full, match);
    return match.test(entry.name) ? [full] : [];
  });
}
