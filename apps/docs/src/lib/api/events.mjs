/**
 * What CAD's two apps send (`cadgen/analytics.py`), checked field by field and turned into rows.
 * Every schema a released cadgen sends is read, for as long as that release can still be running
 * (README.md): a copy nobody updates keeps counting. Anything outside the contract is refused, not
 * stored: an unknown field, a tool name that is not a tool's, a file code that is not 16 hex
 * characters, a string longer than a version or a client name needs, a tool or a file counted twice
 * in one batch, or a second view. A row carries the batch's context and one event; nothing in it
 * names a person, a file or what they made.
 *
 * Events: `tool` (a CAD tool's calls and failures since the last batch), `view` (times a person
 * touched a CAD view, or it switched models) and `file` (a distinct file on screen, once a day per
 * server process: its salted code and its format).
 */

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const TOOL = /^cad_[a-z_]{1,40}$/;
const TOKEN = /^[A-Za-z0-9_.+:-]{0,64}$/;
const FILE_CODE = /^[0-9a-f]{16}$/;
const MAX_EVENTS = 64;
export const MAX_BYTES = 16 * 1024;

const SHARED = new Set(['schema', 'install', 'session', 'version', 'platform', 'arch', 'client', 'presentation', 'events']);
// Where the install came from, as its plugin's startup command named it (`cadgen/_internal/channel.py`).
const CHANNELS = new Set(['claude-github', 'codex-github', 'cursor-github', 'gemini-github', 'claude-desktop',
  'claude-directory', 'openai-directory', 'cursor-marketplace', 'cursor-directory', 'dev', 'unknown']);
const SOURCES = new Set(['store', 'manual']);
// What each schema says beside the shared fields: where the install came from. A new schema adds a reader
// here and keeps the old ones.
const SCHEMAS = new Map([
  // cadgen 0.7.7 to 0.7.11: how it was installed, which names no channel. Kept as `source`.
  [1, { field: 'source', origin: batch => ({ channel: 'unknown', source: oneOf(batch.source, SOURCES, 'source') }) }],
  // cadgen 0.7.12 on: the channel its plugin's startup command named.
  [2, { field: 'channel', origin: batch => ({ channel: oneOf(batch.channel, CHANNELS, 'channel'), source: null }) }],
]);
const PLATFORMS = new Set(['darwin', 'linux', 'win32', 'other']);
const PRESENTATIONS = new Set(['tabs', 'inline', 'text', 'browser']);
const KINDS = new Set(['step', 'stl', '3mf', 'glb', 'dxf', 'urdf', 'srdf', 'sdf']);

export class Invalid extends Error {}

const fail = message => { throw new Invalid(message); };
const token = (value, name, limit = 64) =>
  typeof value === 'string' && value.length <= limit && TOKEN.test(value) ? value : fail(`${name} is not a short token`);
const oneOf = (value, allowed, name) => (allowed.has(value) ? value : fail(`${name} is not one of ${[...allowed].join(', ')}`));
const count = (value, name) => (Number.isInteger(value) && value >= 0 && value <= 1_000_000 ? value : fail(`${name} is not a count`));
const only = (object, keys, name) => {
  for (const key of Object.keys(object)) if (!keys.includes(key)) fail(`${name} has an unknown field ${key}`);
};

export function isUuid(value) {
  return typeof value === 'string' && UUID.test(value);
}

/** The rows a batch stores, or `Invalid`. */
export function rowsOf(batch) {
  if (!batch || typeof batch !== 'object' || Array.isArray(batch)) fail('a batch is an object');
  const schema = SCHEMAS.get(batch.schema) ?? fail(`schema is not one of ${[...SCHEMAS.keys()].join(', ')}`);
  for (const key of Object.keys(batch)) if (key !== schema.field && !SHARED.has(key)) fail(`unknown field ${key}`);
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
  // One event per tool and per file, and one view, as cadgen sends them: a repeat is refused, never added up.
  const seen = new Set();
  const once = (key, message) => (seen.has(key) ? fail(message) : seen.add(key));
  return events.map((event, index) => {
    if (!event || typeof event !== 'object' || Array.isArray(event)) return fail(`events[${index}] is not an event`);
    const row = { ...context, event: event.name, tool: null, file: null, kind: null, calls: 1, errors: 0 };
    if (event.name === 'tool') {
      only(event, ['name', 'tool', 'calls', 'errors'], `events[${index}]`);
      const tool = typeof event.tool === 'string' && TOOL.test(event.tool) ? event.tool : fail(`events[${index}].tool is not a tool`);
      once(`tool ${tool}`, `events[${index}].tool is already in the batch`);
      const calls = count(event.calls, `events[${index}].calls`);
      const errors = event.errors === undefined ? 0 : count(event.errors, `events[${index}].errors`);
      if (calls === 0 || errors > calls) fail(`events[${index}] counts no calls, or more errors than calls`);
      return { ...row, tool, calls, errors };
    }
    if (event.name === 'view') {
      only(event, ['name', 'calls'], `events[${index}]`);
      once('view', `events[${index}] is the batch's second view`);
      const calls = count(event.calls, `events[${index}].calls`);
      if (calls === 0) fail(`events[${index}] counts nothing`);
      return { ...row, calls };
    }
    if (event.name === 'file') {
      only(event, ['name', 'file', 'kind'], `events[${index}]`);
      const file = typeof event.file === 'string' && FILE_CODE.test(event.file) ? event.file : fail(`events[${index}].file is not a file code`);
      once(`file ${file}`, `events[${index}].file is already in the batch`);
      return { ...row, file, kind: oneOf(event.kind, KINDS, `events[${index}].kind`) };
    }
    return fail(`events[${index}] is not an event`);
  });
}
