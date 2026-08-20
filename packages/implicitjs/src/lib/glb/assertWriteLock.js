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
 * ONE case does not throw, and it is not a policy preference: when the PARENT reports that
 * locking was unavailable (`--lock-degraded`, from `BuildRun.degraded`). No run id reaches
 * the sentinel then, so there is nothing here to check, and failing would make this the
 * reason a build dies on a filesystem that cannot lock -- exactly what the Python side's
 * `require_write_lock()` refuses to do. Only the parent can tell that apart from an
 * unverified id; from here both look like an empty sentinel.
 *
 * That case warns and continues with no `CADGEN_STRICT_LOCKS` escape, deliberately. Python's
 * flag turns a MISSING lock into an error, and a degraded run does not read as missing there
 * either -- `exclusive()` registers it, so `require_write_lock()` returns true. Honouring the
 * flag only here would invent a third policy that fires in no environment CI can reach: a
 * filesystem that refuses `flock` is not one any runner has.
 *
 * A degraded run does not read the sentinel at all. It may still hold an id from an earlier
 * run that DID lock -- on a share reached from two machines, say -- and refusing on that
 * would be liveness inferred from a run id, which `coordination/lock.py` forbids in capitals:
 * a stamped id says who ran, never who is running.
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
 *
 * `degraded` is the parent's report that locking was unavailable, so no id was stamped and
 * there is nothing to verify -- see the note above.
 */
export function assertWriteLock(packageDir, runId, { degraded = false } = {}) {
  const sentinel = writeLockPath(packageDir);
  const expected = String(runId || "").trim();

  if (degraded) {
    // stderr, not stdout: stdout carries the progress protocol and the result payload.
    console.warn(
      `cadgen: writing ${packageDir} without mutual exclusion -- this filesystem does not `
      + "support the generation lock, so a concurrent build of the same model is not prevented."
    );
    return;
  }

  let stamped = "";
  let readError = null;
  try {
    stamped = fs.readFileSync(sentinel).subarray(0, RUN_ID_BYTES).toString("ascii").trim();
  } catch (error) {
    // Say WHICH failure this is. Collapsing an unreadable sentinel into "" reported a
    // mismatch against a file that held exactly the right run id, which is how issue #269
    // presented: EBUSY from a mandatory Windows lock, described as a lock violation. The
    // lock no longer sits on this file, so a read error here means something else -- and
    // whatever it is, the reader deserves to be told about it rather than misdirected.
    readError = error;
  }
  if (readError && readError.code === "ENOENT") {
    // No sentinel at all. Not a read failure and not a mismatch: nobody has ever held this
    // lock, so a parent that thinks it holds one is wrong about which directory it is in.
    throw new Error(
      `no generation lock exists for ${packageDir} `
      + `(nothing has ever held ${sentinel}, so --run-id ${expected || "<missing>"} `
      + "cannot have been stamped by its holder)"
    );
  }
  if (readError) {
    throw new Error(
      `could not read the generation sentinel for ${packageDir}: `
      + `${readError.code || readError.message} reading ${sentinel}. `
      + "The run id could not be checked, so the package was not written."
    );
  }
  if (!expected || stamped !== expected) {
    throw new Error(
      `render package written without its generation lock: ${packageDir} `
      + `(--run-id ${expected || "<missing>"} does not match ${sentinel})`
    );
  }
}
