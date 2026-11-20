/**
 * What the install command sends (`scripts/install/`: `install.sh`, `install.ps1` and `install.py`) where a run of it
 * failed with no working cad to count it: one report of where it failed, checked field by field. A run that ends with
 * a cad that works sends nothing here: that cad counts the plugin's install itself (`events.mjs`: `install`,
 * `install_failure`).
 *
 * A report names its run by a random id made for that run alone and kept nowhere on the computer (`run`), so nothing
 * is held under an id that lasts and there is nothing to forget; when it was made (`at`, whole seconds of the sender's
 * clock); the stage that failed (`STAGES`); whether the stage failed or the script itself crashed (`OUTCOMES`); the
 * exit status (`code`); the platform and the machine's architecture, as a batch of counts names them; who ran the
 * command, a person or cad (`BY`); and uv's version, or `none`. A crash alone says more: its type's name, and up to
 * ten of its frames in `install.py`, each a function and a line -- never a file's name, a path or a message.
 *
 * Anything outside that is refused (`Invalid`), not stored.
 */
import { FUNCTION, idOf, Invalid, MAX_AT, matches, oneOf, only, PLATFORMS, token, TYPE } from './events.mjs';

export const SCHEMA = 1;
// A whole report is a few hundred bytes, a crash's frames included.
export const MAX_REPORT_BYTES = 4096;
// A run's id, as Python's `uuid4`, PowerShell's `NewGuid` and a shell's `uuidgen` write one: the last in capitals on
// macOS, so either case is read, and kept in lower case.
const RUN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
// Where a run failed: uv could not be installed or is too old; `install.py` could not be downloaded; uv could not run
// it; cad could not be installed; no cad could run the plugin's step; or `install.py` crashed.
const STAGES = new Set(['uv', 'fetch', 'python', 'cad', 'plugin', 'script']);
const OUTCOMES = new Set(['failed', 'crashed']);
const BY = new Set(['person', 'cad']);
const MAX_CODE = 255; // an exit status
const UV = /^(?:none|\d+\.\d+\.\d+)$/;
const MAX_UV = 32; // as long as a version's name
const MAX_FRAMES = 10;
const MAX_LINE = 10_000_000;

/** What a report says of its run, as the store passes it on: a crash's `type` and `frames` where it names them. */
export const FIELDS = ['stage', 'outcome', 'code', 'platform', 'arch', 'by', 'uv', 'type', 'frames'];

const fail = message => { throw new Invalid(message); };
const frameOf = (frame, name) => {
  if (!frame || typeof frame !== 'object' || Array.isArray(frame)) fail(`${name} is not a frame`);
  only(frame, ['function', 'line'], name);
  const read = { function: matches(frame.function, FUNCTION, `${name}.function`) };
  if (frame.line !== undefined) {
    read.line = Number.isInteger(frame.line) && frame.line >= 0 && frame.line < MAX_LINE ? frame.line : fail(`${name}.line is not a place`);
  }
  return read;
};

/**
 * The report a body is, or `Invalid`: its fields as checked, the run's id in lower case, and an id of its own (`id`,
 * made of the run and the stage as a row's is of its batch and key) that is the same however often the report is sent.
 */
export function reportOf(body) {
  if (!body || typeof body !== 'object' || Array.isArray(body)) fail('a report is an object');
  only(body, ['schema', 'run', 'at', ...FIELDS], 'the report');
  if (body.schema !== SCHEMA) fail(`schema is not ${SCHEMA}`);
  const run = matches(body.run, RUN, 'run').toLowerCase();
  const at = Number.isInteger(body.at) && body.at >= 0 && body.at <= MAX_AT ? body.at : fail('at is not a time');
  const stage = oneOf(body.stage, STAGES, 'stage');
  const outcome = oneOf(body.outcome, OUTCOMES, 'outcome');
  const report = {
    id: idOf(run, `install_failed ${stage}`), run, at, stage, outcome,
    code: Number.isInteger(body.code) && body.code >= 0 && body.code <= MAX_CODE ? body.code : fail('code is not an exit status'),
    platform: oneOf(body.platform, PLATFORMS, 'platform'),
    arch: token(body.arch, 'arch', 16),
    by: oneOf(body.by, BY, 'by'),
    uv: typeof body.uv === 'string' && body.uv.length <= MAX_UV && UV.test(body.uv) ? body.uv : fail("uv is not a version's name or none"),
  };
  // Only a crash has a type and frames: a stage that failed names neither.
  if (outcome !== 'crashed') {
    for (const key of ['type', 'frames']) if (body[key] !== undefined) fail(`${key}: only a crash names one`);
    return report;
  }
  report.type = matches(body.type, TYPE, 'type');
  if (body.frames !== undefined) {
    if (!Array.isArray(body.frames) || body.frames.length > MAX_FRAMES) fail(`frames is a list of at most ${MAX_FRAMES}`);
    report.frames = body.frames.map((frame, index) => frameOf(frame, `frames[${index}]`));
  }
  return report;
}
