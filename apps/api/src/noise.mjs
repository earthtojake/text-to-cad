/**
 * Crash reports that are never cadgen's bug, dropped before they reach PostHog (README.md, "Never cadgen's
 * bug"). Released clients keep sending what a later one learned to leave out, and every one of these would be
 * an issue to triage that has no fix in cadgen: the other end of a connection leaving, a model's own mistake
 * that an older cadgen let Python word, a worker someone stopped.
 *
 * The rule: a signature goes on `NEVER_OURS` only when it can never be a mistake in cadgen's code -- never
 * because it is frequent -- and in the same change the client stops sending it (`cadgen/analytics.py`:
 * `stdout_closed`, `signature`). Each entry matches on a row's `where`, `type`, `status` and frames alone. Dropping
 * a row is not a refusal: the batch is still taken, and its other rows stored.
 */

const USER = '<user>';
// Python's names for a connection the other end closed or refused: `ConnectionError` and its subclasses.
const CONNECTION_ERRORS = new Set(['ConnectionError', 'BrokenPipeError', 'ConnectionAbortedError',
  'ConnectionResetError', 'ConnectionRefusedError']);
// What a person's interrupt or logout stops a build worker with: SIGTERM, SIGINT, SIGHUP, as a negative exit status.
const STOPPED = new Set([-15, -2, -1]);
// The only cadgen code a person's own recursion runs through: the decorator wrapper that calls their model.
const THEIR_CYCLE = new Set(['cadgen/authoring.py']);

// The innermost frame is cadgen's `file` at `fn`, and the person's code called its way there: cadgen only
// passed on what the model asked of it.
const askedOf = (frames, file, fn) => {
  const last = frames.at(-1);
  return last?.file === file && last.function === fn && frames.slice(0, -1).some(frame => frame.file === USER);
};

/** Each signature by its name, as the log counts it, and the test a crash row must pass to be dropped. */
export const NEVER_OURS = [
  // A page that left a viewer route mid-reply (Windows' WSAECONNABORTED): cadgen 0.7.16 to 0.7.18.
  // Only when the response writer raised it (`cadgen/viewer/response.py`): a route's own connection out is cadgen's.
  { name: 'page_left', test: row => row.where === 'route' && CONNECTION_ERRORS.has(row.type)
    && row.frames.some(frame => frame.file === 'cadgen/viewer/response.py') },
  // Whatever read a command's output closed it (`cadgen ... | head`): cadgen 0.7.19 and earlier.
  // Only when cadgen's own code wrote it (a print: its innermost frame is cadgen's), not a child's pipe (`subprocess`).
  { name: 'output_closed', test: row => row.where === 'command' && row.type === 'BrokenPipeError'
    && (row.frames.at(-1)?.file ?? '').startsWith('cadgen/') },
  // A model asking `cadgen.build123d` for a name build123d does not have: before 0.7.19 it said so as Python did.
  { name: 'no_such_build123d_name', test: row => row.type === 'AttributeError' && askedOf(row.frames, 'cadgen/build123d.py', '__getattr__') },
  // A colour that is not a string, handed to `srgb()`: before 0.7.19 its `.strip()` failed.
  { name: 'colour_not_a_string', test: row => row.type === 'AttributeError' && askedOf(row.frames, 'cadgen/color.py', '_parse_hex') },
  // A build worker someone stopped, not one that crashed: before 0.7.19 it counted as dead.
  { name: 'worker_stopped', test: row => row.type === 'WorkerDied' && STOPPED.has(row.status) },
  // A RecursionError with the person's code among its innermost frames: their code is in the cycle (a model
  // that calls itself never ends). cadgen's own recursion fills those frames with cadgen's.
  // Of cadgen's code, only the decorator wrapper that calls the model may be in it: anything else may be cadgen's cycle.
  { name: 'their_recursion', test: row => row.type === 'RecursionError' && row.frames.some(frame => frame.file === USER)
    && row.frames.every(frame => !frame.file.startsWith('cadgen/') || THEIR_CYCLE.has(frame.file)) },
  // A page's cancellation: an AbortError is what the page's own `abort()`, or the browser leaving the page, makes
  // -- a view's feed aborting its request as the view unmounts. Asked for, never a crash: cadgen 0.7.20 and earlier.
  { name: 'page_cancelled', test: row => row.where === 'page' && row.type === 'AbortError' },
];

/**
 * A batch's rows without the crashes that are never cadgen's (`NEVER_OURS`), and how many of each were left
 * out, by name. Only an `exception` row is ever left out.
 * @param {object[]} rows
 * @returns {{ rows: object[], dropped: Map<string, number> }}
 */
export function withoutNoise(rows) {
  const dropped = new Map();
  const kept = rows.filter(row => {
    if (row.event !== 'exception') return true;
    const noise = NEVER_OURS.find(({ test }) => test(row));
    if (noise) dropped.set(noise.name, (dropped.get(noise.name) ?? 0) + row.count);
    return !noise;
  });
  return { rows: kept, dropped };
}
