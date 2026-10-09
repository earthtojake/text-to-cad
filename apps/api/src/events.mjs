/**
 * What cadgen sends (`cadgen/analytics.py`), checked field by field and turned into rows. Every schema a
 * released cadgen sends is read, for as long as that release can still be running (README.md): a copy
 * nobody updates keeps counting. Anything outside the contract is refused, not stored: an unknown field, a
 * name outside its vocabulary, a count that is not one, a string longer than a version or a client name
 * needs, or an event counted twice in one batch. A row carries the batch's context and one event's counts;
 * nothing in it names a person, a file or what they made.
 *
 * Each event counts what one process -- the CAD app (`app`), the browser viewer (`viewer`) or the build
 * daemon (`daemon`) -- saw since its last batch (`FIELDS`):
 *
 *   tool      a CAD tool's calls, and how many of them failed
 *   tool_failure
 *             a CAD tool's failed calls for one reason (`FAILURES`), a word cadgen chose where the call
 *             failed: never what the failure said
 *   view      times a person touched a CAD view, or it switched models
 *   files     distinct files of one format a view showed for the first time that day
 *   build     builds of one format, by who asked: how they ended, how many the store answered, how long
 *             they took in all and at the longest
 *   snapshot  snapshots of one format, how many failed, and how long they took
 *   feature   uses of one feature
 *   health    the daemon's build workers: started, crashed and recycled, and builds refused for memory
 *   exception one crash, and how many times it happened: where (a CAD tool's call, a viewer route, a
 *             request the daemon served, a build, a command, a page), its type, and its innermost frames
 *             in code that may be named -- cadgen's, the standard library's, a dependency's, the page's
 *             assets -- with the person's own code a bare `<user>`. Never a message, a variable or a path.
 *
 * cadgen 0.7.7 to 0.7.15 (schemas 1 and 2) send `tool`, `view` and `file`: one distinct file, once a day,
 * by a salted code. Its code goes no further: a batch's are read as `files`, one of each format they name.
 * Schema 4 adds `tool_failure`. A receiver that reads a new schema is deployed before any release sends it.
 */

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const TOOL = /^cad_[a-z_]{1,40}$/;
const TOKEN = /^[A-Za-z0-9_.+:-]{0,64}$/;
const FILE_CODE = /^[0-9a-f]{16}$/;
const MAX_EVENTS = 64;
const MAX_COUNT = 1_000_000;
const MAX_SECONDS = 10_000_000; // a window's builds, added up across every worker: far past any there are
const MAX_FRAMES = 30;
// A crash's frame, as cadgen names one (`cadgen/analytics.py`: `signature`; a page's: core's `crashOf`).
// A path inside a place: segments of letters, digits and `_.+-`, none of them `.` or `..`.
const FRAME_FILE = /^(?:<user>|<\?>|<frozen>|(?!\.\.?(?:\/|$))[A-Za-z0-9_.+-]{1,64}(?:\/(?!\.\.?(?:\/|$))[A-Za-z0-9_.+-]{1,64}){0,8})$/;
const FUNCTION = /^(?:<user>|<\?>|[A-Za-z_$<][A-Za-z0-9_$.<>]{0,79})$/;
const TYPE = /^(?:<user>|<\?>|[A-Za-z_][A-Za-z0-9_.]{0,127})$/;
export const MAX_BYTES = 64 * 1024;

const SHARED = new Set(['schema', 'install', 'session', 'version', 'platform', 'arch', 'client', 'presentation', 'events']);
// Where the install came from, as its plugin's startup command named it (`cadgen/_internal/channel.py`).
const CHANNELS = new Set(['claude-github', 'codex-github', 'cursor-github', 'gemini-github', 'claude-desktop',
  'claude-directory', 'openai-directory', 'cursor-marketplace', 'agent-plugins', 'dev', 'unknown']);
const SOURCES = new Set(['store', 'manual']);
const PROCESSES = new Set(['app', 'viewer', 'daemon']);
const PLATFORMS = new Set(['darwin', 'linux', 'win32', 'other']);
const PRESENTATIONS = new Set(['tabs', 'inline', 'text', 'browser']);
const CHUNK_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const KINDS = new Set(['step', 'stl', '3mf', 'glb', 'dxf', 'urdf', 'srdf', 'sdf']);
const VIAS = new Set(['script', 'command']);
const FEATURES = new Set(['assembly', 'declared_mesh', 'kinematics', 'animation', 'drawing', 'quick_edit']);
const WHERE = new Set(['tool', 'route', 'request', 'build', 'command', 'page']);
// Why a CAD tool's call failed (`cadgen/analytics.py`: `FAILURES`): the caller's, the view's, the machine's or
// cadgen's own, as cadgen named it where the call failed.
const FAILURES = new Set(['no_path', 'relative_path', 'no_file', 'not_cad', 'no_view', 'wrong_view', 'bad_request',
  'timeout', 'view_error', 'too_large', 'no_viewer', 'bug', 'other']);

/** Each event as a row carries it: the names it is told apart by, then what it counts. */
export const FIELDS = {
  tool: ['tool', 'calls', 'errors'],
  tool_failure: ['tool', 'reason', 'count'],
  view: ['calls'],
  files: ['kind', 'count'],
  build: ['kind', 'via', 'count', 'failed', 'crashed', 'cancelled', 'cached', 'seconds', 'longest'],
  snapshot: ['kind', 'count', 'failed', 'seconds'],
  feature: ['feature', 'count'],
  health: ['workers', 'crashes', 'recycles', 'refusals'],
  exception: ['where', 'tool', 'type', 'handled', 'status', 'frames', 'count'],
};

export class Invalid extends Error {}

const fail = message => { throw new Invalid(message); };
const token = (value, name, limit = 64) =>
  typeof value === 'string' && value.length <= limit && TOKEN.test(value) ? value : fail(`${name} is not a short token`);
const oneOf = (value, allowed, name) => (allowed.has(value) ? value : fail(`${name} is not one of ${[...allowed].join(', ')}`));
const count = (value, name) => (Number.isInteger(value) && value >= 0 && value <= MAX_COUNT ? value : fail(`${name} is not a count`));
const some = (value, name) => (count(value, name) > 0 ? value : fail(`${name} counts nothing`));
// A process's exit status: an exit code or a signal (-N), or on Windows the exception code a fault ended it
// with (an NTSTATUS error, 0xC0000000 and up).
const exitStatus = value => Number.isInteger(value) && (Math.abs(value) < 512 || (value >= 0xC0000000 && value <= 0xFFFFFFFF));
const matches = (value, pattern, name) => (typeof value === 'string' && pattern.test(value) ? value : fail(`${name} is not one`));
const frameOf = (frame, name) => {
  if (!frame || typeof frame !== 'object' || Array.isArray(frame)) fail(`${name} is not a frame`);
  only(frame, ['file', 'function', 'line', 'column', 'chunk_id'], name);
  const read = { file: matches(frame.file, FRAME_FILE, `${name}.file`), function: matches(frame.function, FUNCTION, `${name}.function`) };
  // A page's chunk, by the debug id its build stamped on it and on the source map a release uploads.
  if (frame.chunk_id !== undefined) read.chunk_id = matches(frame.chunk_id, CHUNK_ID, `${name}.chunk_id`);
  // A minified script's one line runs to millions of columns.
  for (const key of ['line', 'column']) {
    if (frame[key] === undefined) continue;
    read[key] = Number.isInteger(frame[key]) && frame[key] >= 0 && frame[key] < 10_000_000 ? frame[key] : fail(`${name}.${key} is not a place`);
  }
  return read;
};
const seconds = (value, name) =>
  (typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= MAX_SECONDS ? value : fail(`${name} is not seconds`));
const only = (object, keys, name) => {
  for (const key of Object.keys(object)) if (!keys.includes(key)) fail(`${name} has an unknown field ${key}`);
};
// An event's fields, every one of them there and no other.
const exactly = (event, fields, name) => {
  only(event, ['name', ...fields], name);
  for (const field of fields) if (event[field] === undefined) fail(`${name} has no ${field}`);
};

// Each event as a schema sends it: its key in the batch (one event per key), and its row's fields.
const READERS = {
  tool(event, at) {
    only(event, ['name', 'tool', 'calls', 'errors'], at);
    const tool = typeof event.tool === 'string' && TOOL.test(event.tool) ? event.tool : fail(`${at}.tool is not a tool`);
    const calls = some(event.calls, `${at}.calls`);
    const errors = event.errors === undefined ? 0 : count(event.errors, `${at}.errors`);
    if (errors > calls) fail(`${at} counts more errors than calls`);
    return { key: `tool ${tool}`, fields: { tool, calls, errors } };
  },
  tool_failure(event, at) {
    exactly(event, FIELDS.tool_failure, at);
    const tool = matches(event.tool, TOOL, `${at}.tool`);
    const reason = oneOf(event.reason, FAILURES, `${at}.reason`);
    return { key: `tool_failure ${tool} ${reason}`, fields: { tool, reason, count: some(event.count, `${at}.count`) } };
  },
  view(event, at) {
    only(event, ['name', 'calls'], at);
    return { key: 'view', fields: { calls: some(event.calls, `${at}.calls`) } };
  },
  file(event, at) {
    only(event, ['name', 'file', 'kind'], at);
    const file = typeof event.file === 'string' && FILE_CODE.test(event.file) ? event.file : fail(`${at}.file is not a file code`);
    return { key: `file ${file}`, event: 'files', fields: { kind: oneOf(event.kind, KINDS, `${at}.kind`), count: 1 } };
  },
  files(event, at) {
    exactly(event, FIELDS.files, at);
    const kind = oneOf(event.kind, KINDS, `${at}.kind`);
    return { key: `files ${kind}`, fields: { kind, count: some(event.count, `${at}.count`) } };
  },
  build(event, at) {
    exactly(event, FIELDS.build, at);
    const kind = oneOf(event.kind, KINDS, `${at}.kind`);
    const via = oneOf(event.via, VIAS, `${at}.via`);
    const builds = some(event.count, `${at}.count`);
    const [failed, crashed, cancelled, cached] = ['failed', 'crashed', 'cancelled', 'cached'].map(name => count(event[name], `${at}.${name}`));
    // A build ends one way, and only one that ended well was the store's answer.
    if (failed + crashed + cancelled + cached > builds) fail(`${at} counts more endings than builds`);
    return { key: `build ${kind} ${via}`, fields: { kind, via, count: builds, failed, crashed, cancelled, cached,
      seconds: seconds(event.seconds, `${at}.seconds`), longest: seconds(event.longest, `${at}.longest`) } };
  },
  snapshot(event, at) {
    exactly(event, FIELDS.snapshot, at);
    const kind = oneOf(event.kind, KINDS, `${at}.kind`);
    const snapshots = some(event.count, `${at}.count`);
    const failed = count(event.failed, `${at}.failed`);
    if (failed > snapshots) fail(`${at} counts more failures than snapshots`);
    return { key: `snapshot ${kind}`, fields: { kind, count: snapshots, failed, seconds: seconds(event.seconds, `${at}.seconds`) } };
  },
  feature(event, at) {
    exactly(event, FIELDS.feature, at);
    const feature = oneOf(event.feature, FEATURES, `${at}.feature`);
    return { key: `feature ${feature}`, fields: { feature, count: some(event.count, `${at}.count`) } };
  },
  health(event, at) {
    exactly(event, FIELDS.health, at);
    const fields = Object.fromEntries(FIELDS.health.map(name => [name, count(event[name], `${at}.${name}`)]));
    if (!Object.values(fields).some(Boolean)) fail(`${at} counts nothing`);
    return { key: 'health', fields };
  },
  exception(event, at) {
    only(event, ['name', ...FIELDS.exception], at);
    if (typeof event.handled !== 'boolean') fail(`${at}.handled is not true or false`);
    if (!Array.isArray(event.frames) || event.frames.length > MAX_FRAMES) fail(`${at}.frames is a list of at most ${MAX_FRAMES}`);
    const fields = {
      where: oneOf(event.where, WHERE, `${at}.where`),
      ...(event.tool === undefined ? {} : { tool: matches(event.tool, TOOL, `${at}.tool`) }),
      type: matches(event.type, TYPE, `${at}.type`),
      handled: event.handled,
      ...(event.status === undefined ? {} : { status: exitStatus(event.status) ? event.status : fail(`${at}.status is not an exit status`) }),
      frames: event.frames.map((frame, index) => frameOf(frame, `${at}.frames[${index}]`)),
      count: some(event.count, `${at}.count`),
    };
    if (fields.where !== 'page' && fields.frames.some(frame => frame.chunk_id)) fail(`${at}: only a page's frames name a chunk`);
    const crash = [fields.where, fields.tool, fields.type, fields.handled, fields.status, fields.frames];
    return { key: `exception ${JSON.stringify(crash)}`, fields };
  },
};

// Before schema 3 only the apps sent, and the browser viewer said so by how it shows CAD.
const appOf = batch => (batch.presentation === 'browser' ? 'viewer' : 'app');
const BEFORE_DAEMON = new Set(['tool', 'view', 'file']);
const WITH_DAEMON = ['tool', 'view', 'files', 'build', 'snapshot', 'feature', 'health', 'exception'];
const byProcess = batch => ({
  channel: oneOf(batch.channel, CHANNELS, 'channel'), source: null, process: oneOf(batch.process, PROCESSES, 'process'),
});
// What each schema says beside the shared fields -- where the install came from, and which process sent
// it -- and the events it sends. A new schema adds a reader here and keeps the old ones.
const SCHEMAS = new Map([
  // cadgen 0.7.7 to 0.7.11: how it was installed, which names no channel. Kept as `source`.
  [1, { fields: ['source'], events: BEFORE_DAEMON,
    origin: batch => ({ channel: 'unknown', source: oneOf(batch.source, SOURCES, 'source'), process: appOf(batch) }) }],
  // cadgen 0.7.12 to 0.7.15: the channel its plugin's startup command named.
  [2, { fields: ['channel'], events: BEFORE_DAEMON,
    origin: batch => ({ channel: oneOf(batch.channel, CHANNELS, 'channel'), source: null, process: appOf(batch) }) }],
  // The build daemon joins the apps: each batch names its process, and counts files rather than naming them.
  [3, { fields: ['channel', 'process'], events: new Set(WITH_DAEMON), origin: byProcess }],
  // Why tool calls failed, beside how many did.
  [4, { fields: ['channel', 'process'], events: new Set([...WITH_DAEMON, 'tool_failure']), origin: byProcess }],
]);

export function isUuid(value) {
  return typeof value === 'string' && UUID.test(value);
}

/** The rows a batch stores, or `Invalid`. */
export function rowsOf(batch) {
  if (!batch || typeof batch !== 'object' || Array.isArray(batch)) fail('a batch is an object');
  const schema = SCHEMAS.get(batch.schema) ?? fail(`schema is not one of ${[...SCHEMAS.keys()].join(', ')}`);
  for (const key of Object.keys(batch)) if (!schema.fields.includes(key) && !SHARED.has(key)) fail(`unknown field ${key}`);
  if (!isUuid(batch.install)) fail('install is not a uuid');
  if (!isUuid(batch.session)) fail('session is not a uuid');
  const client = batch.client ?? {};
  if (typeof client !== 'object' || Array.isArray(client)) fail('client is an object');
  only(client, ['name', 'version'], 'client');
  const context = {
    install_id: batch.install,
    session_id: batch.session,
    version: token(batch.version, 'version', 32),
    ...schema.origin(batch),
    platform: oneOf(batch.platform, PLATFORMS, 'platform'),
    arch: batch.arch === undefined ? null : token(batch.arch, 'arch', 16),
    client: client.name === undefined ? null : token(client.name, 'client.name'),
    client_version: client.version === undefined ? null : token(client.version, 'client.version', 32),
    presentation: batch.presentation === undefined ? null : oneOf(batch.presentation, PRESENTATIONS, 'presentation'),
  };
  const events = batch.events;
  if (!Array.isArray(events) || events.length === 0 || events.length > MAX_EVENTS) fail(`events is a list of 1 to ${MAX_EVENTS}`);
  // One event per key, as cadgen sends them: a repeat is refused, never added up.
  const seen = new Set();
  const rows = [];
  events.forEach((event, index) => {
    const at = `events[${index}]`;
    if (!event || typeof event !== 'object' || Array.isArray(event) || !schema.events.has(event.name)) fail(`${at} is not an event`);
    const { key, event: name = event.name, fields } = READERS[event.name](event, at);
    if (seen.has(key)) fail(`${at} is already in the batch`);
    seen.add(key);
    // A file by its code (schemas 1 and 2) is one more of its format's.
    const same = name === 'files' ? rows.find(row => row.event === 'files' && row.kind === fields.kind) : undefined;
    if (same) same.count += fields.count;
    else rows.push({ ...context, event: name, ...fields });
  });
  return rows;
}
