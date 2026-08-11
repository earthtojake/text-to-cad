/**
 * A module-load hook that records WHICH files a model actually loaded.
 *
 * The Python producer needs the model's source closure to record a freshness digest over it
 * (design §5.2: "Node knows which files, Python owns the digest"). Static analysis of the
 * source would miss a dynamic import; asking the runtime cannot.
 *
 * Hooks run on their OWN thread, so the recording channel has to cross a thread boundary. It
 * is a file rather than a `MessagePort` on purpose: `appendFileSync` returns before the hook
 * does, so by the time `await import(model)` resolves in the builder every line is already on
 * disk. A port would deliver its messages asynchronously and the builder would have to guess
 * how long to wait for the last one.
 */

import fs from "node:fs";
import { fileURLToPath } from "node:url";

let logPath = "";

export async function initialize(data) {
  logPath = String(data?.logPath || "");
}

export async function load(url, context, nextLoad) {
  if (logPath && url.startsWith("file:")) {
    try {
      fs.appendFileSync(logPath, `${fileURLToPath(url)}\n`);
    } catch {
      // A closure we could not record is a freshness question, not a build failure: the
      // producer still records the entry file, and a missing dependency shows up as a model
      // that does not rebuild when that dependency changes. Never fail the build for it.
    }
  }
  return nextLoad(url, context);
}
