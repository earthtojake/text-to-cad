/**
 * The child half of the Node-builder progress protocol.
 *
 * A render-package builder runs as a Node child of the Python process that holds the
 * artifact's generation lock (`cadgen/_internal/node_runtime.py`). The child owns geometry
 * and GLB bytes; it owns NO coordination state -- it never derives a lock path, never writes
 * `.generation.progress.json`, and never decides that a build is current. All it does is
 * describe what it is doing, one JSON object per line on **stdout**, and the parent applies
 * that to the `BuildRun` that is actually holding the lock.
 *
 * Every builder speaks this, so it is written once here rather than hand-rolled per format.
 *
 * ```js
 * import { reportPhase, reportTotal, reportAdvance, reportResult }
 *   from "implicitjs/glb/progressStream.js";
 *
 * reportPhase("sample", 96);
 * for (const slice of slices) { …; reportAdvance(1, `slice ${i}/96`); }
 * reportResult({ ok: true, packagePath, triangles });
 * ```
 *
 * Rules:
 *
 * * **stdout is the protocol.** Anything a builder wants to *say* goes to stderr (which the
 *   parent inherits). Do not `console.log`. A stray line is tolerated -- the parent ignores
 *   what it cannot parse -- but it is noise in a channel that has a job.
 * * **`result` is terminal.** Emit exactly one, last; the parent stops reading there and
 *   expects the process to exit promptly afterwards.
 * * **Dependency-free and synchronous.** `writeSync` on fd 1 with a retry on `EAGAIN`,
 *   because a piped stdout can be non-blocking and `process.stdout.write` would buffer the
 *   final lines into a race with exit.
 */

import fs from "node:fs";

const STDOUT_FD = 1;

function writeLine(payload) {
  const line = `${JSON.stringify(payload)}\n`;
  const bytes = Buffer.from(line, "utf8");
  let offset = 0;
  while (offset < bytes.length) {
    try {
      offset += fs.writeSync(STDOUT_FD, bytes, offset, bytes.length - offset);
    } catch (error) {
      if (error?.code === "EAGAIN") continue; // non-blocking pipe; retry rather than drop
      if (error?.code === "EPIPE") return; // parent stopped reading (it has its result)
      throw error;
    }
  }
}

function finiteInt(value) {
  // Explicit null/undefined check first: `Number(null)` is 0, which would silently turn "this
  // phase has no denominator" into "this phase has 0 units of work".
  if (value === null || value === undefined || value === "") return null;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? Math.trunc(numeric) : null;
}

/**
 * Enter a phase. `total` is the phase's denominator when it has one, and omitted/null when
 * the work is opaque -- the parent's bar interpolates an indeterminate phase against the
 * previous build's measured duration, so lying about a total is worse than having none.
 */
export function reportPhase(phase, total = null, detail = "") {
  const name = String(phase || "").trim();
  if (!name) return;
  writeLine({ type: "phase", phase: name, total: finiteInt(total), detail: String(detail || "") });
}

/** Set (or replace) the current phase's denominator once it becomes known mid-phase. */
export function reportTotal(total) {
  const value = finiteInt(total);
  if (value === null) return;
  writeLine({ type: "total", total: value });
}

/** Advance the current phase by `n` units of work. */
export function reportAdvance(n = 1, detail = "") {
  const count = finiteInt(n);
  writeLine({ type: "advance", n: count === null ? 1 : count, detail: String(detail || "") });
}

/**
 * The builder's terminal payload -- this object (minus `type`) becomes the Python wrapper's
 * return value and, through it, the CLI's JSON line. Emit exactly one, then exit.
 */
export function reportResult(payload) {
  const body = payload && typeof payload === "object" ? payload : {};
  writeLine({ ...body, type: "result" });
}
