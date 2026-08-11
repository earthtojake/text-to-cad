/**
 * Source-closure capture for the implicit builder.
 *
 * `beginClosureCapture(modelDir)` installs `implicitClosureHooks.mjs` and returns a handle
 * whose `files()` lists every FIRST-PARTY file the model loaded -- the model's own module and
 * anything it imported that is not part of the runtime. The runtime (`packages/**`,
 * `node_modules/**`) is excluded deliberately: it is versioned with the tool, not with the
 * model, and putting it in a model's closure would invalidate every package on any package
 * edit.
 *
 * The list goes back to Python, which computes the digest (design §5.2).
 */

import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { register } from "node:module";
import { fileURLToPath } from "node:url";

// packages/cadjs/bin/ -> packages/. Everything under it is runtime, not model source.
const PACKAGES_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");

function isRuntimeFile(file) {
  return file.startsWith(`${PACKAGES_ROOT}${path.sep}`) || file.split(path.sep).includes("node_modules");
}

export function beginClosureCapture(modelDir) {
  const logPath = path.join(
    os.tmpdir(),
    `implicit-closure-${process.pid}-${Date.now()}-${Math.random().toString(36).slice(2)}.log`
  );
  register("./implicitClosureHooks.mjs", import.meta.url, { data: { logPath } });
  return {
    logPath,
    /** First-party closure files, deduped, in load order. Consumes the log. */
    files() {
      let text = "";
      try {
        text = fs.readFileSync(logPath, "utf8");
      } catch {
        return [];
      } finally {
        try {
          fs.unlinkSync(logPath);
        } catch { /* a leftover temp file must not fail a build */ }
      }
      const seen = new Set();
      for (const line of text.split("\n")) {
        const file = line.trim();
        if (!file || isRuntimeFile(file) || seen.has(file)) continue;
        seen.add(file);
      }
      // `modelDir` is accepted for symmetry with the producer's `base` and to keep the
      // relationship explicit; the filter above is what decides membership, because a model
      // may legitimately import a shared helper from a parent directory.
      void modelDir;
      return [...seen];
    },
  };
}
