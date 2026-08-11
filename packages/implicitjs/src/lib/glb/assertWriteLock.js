/**
 * The Node half of `cadgen.coordination.require_write_lock`.
 *
 * A render package is only ever written from inside the artifact's generation lock, and for
 * the JS builders that lock is held by the PYTHON PARENT (`cadgen/_internal/node_runtime.py`)
 * -- Node cannot take it: `fs.flock` and `O_EXLOCK` do not exist. So the child cannot verify
 * the lock by taking it. What it can do is prove it was started by the holder:
 *
 * a run id reaches the sentinel ONLY from inside `exclusive()`, after `LOCK_EX` was taken
 * (`coordination/lock.py`), so a `--run-id` matching the sentinel's stamp is unforgeable
 * outside a held lock.
 *
 * That makes this a real boundary rather than a comment: a builder run by hand against a
 * package directory, or with a stale run id, throws before it writes a byte.
 *
 * It throws UNCONDITIONALLY -- there is no `CADGEN_STRICT_LOCKS` escape hatch like the Python
 * side's. The Python check is old enough to have callers whose environments must degrade
 * rather than fail; this one is new, and new code fails loud
 * (design/unified-glb-render-artifacts.md §0.2, §4.4).
 */

import fs from "node:fs";
import path from "node:path";

/** Mirrors `coordination/paths.py` WRITE_LOCK_SUFFIX, which is declared FROZEN there. */
const WRITE_LOCK_SUFFIX = ".generation.lock";

/** Mirrors `coordination/lock.py` _RUN_ID_BYTES. */
const RUN_ID_BYTES = 32;

/** The hidden sibling sentinel a writer of `packageDir` holds. */
export function writeLockPath(packageDir) {
  const resolved = path.resolve(packageDir);
  return path.join(path.dirname(resolved), `.${path.basename(resolved)}${WRITE_LOCK_SUFFIX}`);
}

/**
 * Throw unless `runId` is the run id currently stamped into `packageDir`'s write sentinel.
 */
export function assertWriteLock(packageDir, runId) {
  const sentinel = writeLockPath(packageDir);
  const expected = String(runId || "").trim();
  let stamped = "";
  try {
    stamped = fs.readFileSync(sentinel).subarray(0, RUN_ID_BYTES).toString("ascii").trim();
  } catch {
    stamped = "";
  }
  if (!expected || stamped !== expected) {
    throw new Error(
      `render package written without its generation lock: ${packageDir} `
      + `(--run-id ${expected || "<missing>"} does not match ${sentinel})`
    );
  }
}
