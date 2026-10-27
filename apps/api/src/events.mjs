/**
 * What cadgen sends (`cadgen/analytics.py`), checked field by field and turned into rows. Every schema a
 * released cadgen sends is read, for as long as that release can still be running (README.md): a copy
 * nobody updates keeps counting. Anything outside the contract is refused, not stored: an unknown field, a
 * name outside its vocabulary, a count that is not one, a string longer than a version or a client name
 * needs, or an event counted twice in one batch. A row carries the batch's context and one event's counts;
 * nothing in it names a person, a file or what they made.
 *
 * Each event counts what one process -- the CAD app (`app`), the browser viewer (`viewer`), the build
 * daemon (`daemon`), or the sender a `cadgen` command starts for what commands counted (`cli`) -- saw since
 * its last batch (`FIELDS`):
 *
 *   tool      a CAD tool's calls, and how many of them failed (`cad_unknown`: the calls naming no tool of cadgen's)
 *   tool_failure
 *             a CAD tool's failed calls for one reason (`FAILURES`), a word cadgen chose where the call
 *             failed: never what the failure said
 *   view      times a person touched a CAD view, or it switched models
 *   files     distinct files of one format a view showed for the first time that day
 *   build     builds of one format, by who asked: how they ended, how many the store answered, how long
 *             they took in all and at the longest
 *   build_failure
 *             failed builds of one format, by who asked, for one reason (`BUILD_FAILURES`), a word cadgen
 *             chose where the build failed: never what the failure said
 *   snapshot  snapshots of one format, how many failed, and how long they took
 *   snapshot_failure
 *             failed snapshots of one format for one reason (`SNAPSHOT_FAILURES`), likewise
 *   feature   uses of one feature
 *   health    the daemon's build workers: started, crashed and recycled, and builds refused for memory
 *   control   a viewer's control (`CONTROLS`): a tool, a tool's mode or setting, a Display or Preview setting, a
 *             menu item, a button -- how many times a person used it, and for a tool that stays on (a tool in
 *             hand, Preview) the whole seconds it was on. A setting is counted, never the value chosen, unless
 *             the value is itself a name of the vocabulary (a render mode, an axis).
 *   exception one crash, and how many times it happened: where (a CAD tool's call, a viewer route, a
 *             request the daemon served, a build, a command, a page), its type, and its innermost frames
 *             in code that may be named -- cadgen's, the standard library's, a dependency's, the page's
 *             assets -- with the person's own code a bare `<user>`. Never a message, a variable or a path.
 *
 * cadgen 0.7.7 to 0.7.15 (schemas 1 and 2) send `tool`, `view` and `file`: one distinct file, once a day,
 * by a salted code. Its code goes no further: a batch's are read as `files`, one of each format they name.
 * Schema 4 adds `tool_failure`. Schema 5 adds `build_failure` and `snapshot_failure`, and names each batch: a
 * random id (`batch`), and when it was made (`at`, whole seconds of the sender's clock). A sender that is not
 * sure its batch was taken sends it again as it was, so each of its rows gets an id of its own (`id`, a UUIDv5
 * of the batch's id and the row's key) that is the same every time, and a store tells the copy for what it is.
 * Schema 6 is schema 5 with one more format, the engine's document (`xbf`), and one more process, `cli`: the
 * sender a command starts when no CAD app or viewer has sent what commands counted. A schema before it names
 * neither. Schema 7 is schema 6 with the viewers' controls (`control`), and room for more events in a batch
 * (`MAX_EVENTS_7`): one per control a person used that window. A receiver that reads a new schema is deployed
 * before any release sends it. Schema 8 adds `model` for live model builds, views and snapshots, while
 * actual file formats (including opened/exported `xbf`) keep their names. Earlier `xbf` rows remain as sent:
 * their mixed model/file usage cannot be separated after the fact.
 */

import { createHash } from 'node:crypto';

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const TOOL = /^cad_[a-z_]{1,40}$/;
const TOKEN = /^[A-Za-z0-9_.+:-]{0,64}$/;
const FILE_CODE = /^[0-9a-f]{16}$/;
const MAX_EVENTS = 64;
const MAX_EVENTS_7 = 256; // schema 7's: a window's controls, one event each, beside everything else
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
// Who sends, and the formats an event counts: each schema's own (`SCHEMAS`), the later a superset.
const PROCESSES = new Set(['app', 'viewer', 'daemon']);
const PROCESSES_6 = new Set([...PROCESSES, 'cli']);
const PLATFORMS = new Set(['darwin', 'linux', 'win32', 'other']);
const PRESENTATIONS = new Set(['tabs', 'inline', 'text', 'browser']);
const CHUNK_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const KINDS = new Set(['step', 'stl', '3mf', 'glb', 'dxf', 'urdf', 'srdf', 'sdf']);
const KINDS_6 = new Set([...KINDS, 'xbf']);
const KINDS_8 = new Set([...KINDS_6, 'model', 'kicad_pcb']);
const VIAS = new Set(['script', 'command']);
const FEATURES = new Set(['assembly', 'declared_mesh', 'kinematics', 'animation', 'drawing', 'quick_edit']);
// What a person used in a CAD view (`cadgen/analytics.py`: `CONTROLS`, the page's own in `@text-to-cad/ui`'s
// `usage/controls.js`): a closed list of names the page chose, never a value typed or a file's.
export const CONTROLS = new Set([
  // The tools on the strip, each one a mode that stays on (its seconds counted), and Preview; Explode
  // and Clip are popovers from their tiles, no mode, counted as used each time one opens (no seconds).
  'select', 'pencil', 'shapes', 'measure', 'explode', 'clip', 'preview',
  // Select's and Measure's filters.
  'select_filter_all', 'select_filter_parts', 'select_filter_faces', 'select_filter_edges', 'select_filter_position',
  'select_filter_links', 'select_group_faces', 'select_group_edges',
  'measure_filter_all', 'measure_filter_vertices', 'measure_filter_edges', 'measure_filter_faces',
  'measure_taken', 'measure_delete', 'measure_clear',
  // Pencil's and Shapes' tools, and what is done to their ink.
  'pencil_pen', 'pencil_highlighter', 'pencil_eraser',
  'shapes_rectangle', 'shapes_line', 'shapes_arrow', 'shapes_ellipse', 'shapes_text',
  'annotate_mark', 'annotate_color', 'annotate_stroke_width', 'annotate_on_surface', 'annotate_on_plane',
  'annotate_restyle', 'annotate_fill', 'annotate_delete', 'annotate_clear', 'annotate_copy', 'undo', 'redo',
  // Explode's and Clip's controls.
  'explode_amount', 'explode_reset', 'clip_amount', 'clip_axis_x', 'clip_axis_y', 'clip_axis_z', 'clip_part_colors',
  'clip_reverse', 'clip_reset',
  // Display and Projection.
  'display_solid', 'display_shaded', 'display_parts', 'display_xray', 'display_hidden_line', 'display_wireframe',
  'display_grid', 'projection_orthographic', 'projection_perspective',
  // Preview's settings.
  'preview_settings', 'preview_orbit', 'preview_orbit_speed', 'preview_parts_color_mode', 'preview_parts_colors',
  'preview_parts_color', 'preview_lighting_quality', 'preview_lighting_exposure', 'preview_lighting_rotation',
  'preview_lighting_size', 'preview_lighting_fill', 'preview_background_color', 'preview_background_opacity',
  'preview_floor_enabled', 'preview_floor_color', 'preview_floor_opacity', 'preview_floor_placement',
  'preview_floor_finish', 'preview_reset',
  // A model's routines (the sidebar's Animation or Motion, Preview's playbar), and its Position.
  'animation_play', 'animation_clip', 'animation_speed', 'animation_loop', 'animation_autoplay', 'animation_release',
  'position_joint', 'position_preset', 'position_reset', 'position_knob',
  // The file sidebar's sections, and its trees.
  'sidebar_tree', 'sidebar_position', 'sidebar_animation', 'sidebar_layers', 'sidebar_sdf',
  'tree_filter', 'tree_visibility', 'layer_visibility',
  // A part's menu, over the model or in its tree.
  'menu_copy_reference', 'menu_select', 'menu_isolate', 'menu_exit_all_isolates', 'menu_hide_others', 'menu_show_all',
  'menu_hide', 'menu_reveal', 'menu_expand', 'menu_collapse', 'menu_expand_all', 'menu_collapse_all', 'menu_zoom_fit',
  'menu_zoom_selection',
  // The view itself: a double-click's Look at and isolate, the view cube, F's fit.
  'look_at', 'isolate', 'view_cube', 'view_cube_drag', 'fit',
  // Quick Edit's Copy, Queue and Send.
  'quick_edit_copy', 'quick_edit_queue', 'quick_edit_send',
  // The navbar, its file menu and its name menu's Models and Files (the explorer), and the app menu.
  'navbar_back', 'navbar_forward', 'models', 'models_open', 'models_filter',
  'explorer', 'explorer_filter', 'file_copy_path', 'file_reveal', 'home',
  'theme_system', 'theme_light', 'theme_dark', 'language', 'feedback',
  // Export, by format.
  'export_step', 'export_stl', 'export_threemf', 'export_glb', 'export_dxf', 'export_xbf', 'export_original',
  // The home.
  'home_search', 'home_filter_all', 'home_filter_models', 'home_filter_files', 'home_layout_grid', 'home_layout_list',
  'home_open', 'home_pick', 'home_copy_path', 'home_reveal', 'home_pin', 'home_unpin', 'home_delete', 'home_delete_cancel',
]);
const WHERE = new Set(['tool', 'route', 'request', 'build', 'command', 'page']);
// Why a CAD tool's call failed (`cadgen/analytics.py`: `FAILURES`): the caller's, the view's, the machine's or
// cadgen's own, as cadgen named it where the call failed.
const FAILURES = new Set(['no_path', 'relative_path', 'no_file', 'not_cad', 'no_view', 'wrong_view', 'bad_request',
  'timeout', 'view_error', 'too_large', 'no_viewer', 'bug', 'other']);
// Why a build failed (`cadgen/analytics.py`: `BUILD_FAILURES`), from what the error was and whose code raised it:
// the model's, the CAD kernel's under it, cadgen's refusal or its mistake, the machine's.
const BUILD_FAILURES = new Set(['model_error', 'kernel_error', 'refused', 'script_error', 'arguments', 'child_failed',
  'missing_module', 'missing_file', 'io_error', 'timeout', 'memory', 'export_error', 'bug', 'other']);
// Why a snapshot failed (`SNAPSHOT_FAILURES`), by what it was doing or what the error was.
const SNAPSHOT_FAILURES = new Set(['bad_request', 'no_file', 'input_error', 'browser', 'timeout', 'memory', 'render_error',
  'bug', 'other']);
// A batch's time, in whole seconds since 1970: any a clock can say (a wrong one included), never a fraction.
const MAX_AT = 100_000_000_000;
// Ours: the namespace every row's id is made in (`idOf`).
const ROWS = 'a67b62d4-a188-43d2-bebc-29fd3ae2cb82';

/** Each event as a row carries it: the names it is told apart by, then what it counts. */
export const FIELDS = {
  tool: ['tool', 'calls', 'errors'],
  tool_failure: ['tool', 'reason', 'count'],
  view: ['calls'],
  files: ['kind', 'count'],
  build: ['kind', 'via', 'count', 'failed', 'crashed', 'cancelled', 'cached', 'seconds', 'longest'],
  build_failure: ['kind', 'via', 'reason', 'count'],
  snapshot: ['kind', 'count', 'failed', 'seconds'],
  snapshot_failure: ['kind', 'reason', 'count'],
  feature: ['feature', 'count'],
  health: ['workers', 'crashes', 'recycles', 'refusals'],
  control: ['control', 'count', 'seconds'],
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

// Each event as a schema sends it: its key in the batch (one event per key), and its row's fields. A format is
// one of the schema's own (`kinds`).
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
  file(event, at, kinds) {
    only(event, ['name', 'file', 'kind'], at);
    const file = typeof event.file === 'string' && FILE_CODE.test(event.file) ? event.file : fail(`${at}.file is not a file code`);
    return { key: `file ${file}`, event: 'files', fields: { kind: oneOf(event.kind, kinds, `${at}.kind`), count: 1 } };
  },
  files(event, at, kinds) {
    exactly(event, FIELDS.files, at);
    const kind = oneOf(event.kind, kinds, `${at}.kind`);
    return { key: `files ${kind}`, fields: { kind, count: some(event.count, `${at}.count`) } };
  },
  build(event, at, kinds) {
    exactly(event, FIELDS.build, at);
    const kind = oneOf(event.kind, kinds, `${at}.kind`);
    const via = oneOf(event.via, VIAS, `${at}.via`);
    const builds = some(event.count, `${at}.count`);
    const [failed, crashed, cancelled, cached] = ['failed', 'crashed', 'cancelled', 'cached'].map(name => count(event[name], `${at}.${name}`));
    // A build ends one way, and only one that ended well was the store's answer.
    if (failed + crashed + cancelled + cached > builds) fail(`${at} counts more endings than builds`);
    return { key: `build ${kind} ${via}`, fields: { kind, via, count: builds, failed, crashed, cancelled, cached,
      seconds: seconds(event.seconds, `${at}.seconds`), longest: seconds(event.longest, `${at}.longest`) } };
  },
  build_failure(event, at, kinds) {
    exactly(event, FIELDS.build_failure, at);
    const kind = oneOf(event.kind, kinds, `${at}.kind`);
    const via = oneOf(event.via, VIAS, `${at}.via`);
    const reason = oneOf(event.reason, BUILD_FAILURES, `${at}.reason`);
    return { key: `build_failure ${kind} ${via} ${reason}`, fields: { kind, via, reason, count: some(event.count, `${at}.count`) } };
  },
  snapshot_failure(event, at, kinds) {
    exactly(event, FIELDS.snapshot_failure, at);
    const kind = oneOf(event.kind, kinds, `${at}.kind`);
    const reason = oneOf(event.reason, SNAPSHOT_FAILURES, `${at}.reason`);
    return { key: `snapshot_failure ${kind} ${reason}`, fields: { kind, reason, count: some(event.count, `${at}.count`) } };
  },
  snapshot(event, at, kinds) {
    exactly(event, FIELDS.snapshot, at);
    const kind = oneOf(event.kind, kinds, `${at}.kind`);
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
  // Times a person used a control that window, and the whole seconds a control that stays on was on: either may
  // be 0 (a mode taken up in an earlier window and on all this one; a button), never both.
  control(event, at) {
    exactly(event, FIELDS.control, at);
    const control = oneOf(event.control, CONTROLS, `${at}.control`);
    const used = count(event.count, `${at}.count`);
    const on = Number.isInteger(event.seconds) && event.seconds >= 0 && event.seconds <= MAX_SECONDS
      ? event.seconds : fail(`${at}.seconds is not whole seconds`);
    if (!used && !on) fail(`${at} counts nothing`);
    return { key: `control ${control}`, fields: { control, count: used, seconds: on } };
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
const NAMED_EVENTS = [...WITH_DAEMON, 'tool_failure', 'build_failure', 'snapshot_failure'];
const byProcess = processes => batch => ({
  channel: oneOf(batch.channel, CHANNELS, 'channel'), source: null, process: oneOf(batch.process, processes, 'process'),
});
// What each schema says beside the shared fields -- where the install came from, and which process sent
// it -- the events it sends, and the formats they count (`kinds`). A new schema adds a reader here and keeps the
// old ones.
const SCHEMAS = new Map([
  // cadgen 0.7.7 to 0.7.11: how it was installed, which names no channel. Kept as `source`.
  [1, { fields: ['source'], events: BEFORE_DAEMON, kinds: KINDS,
    origin: batch => ({ channel: 'unknown', source: oneOf(batch.source, SOURCES, 'source'), process: appOf(batch) }) }],
  // cadgen 0.7.12 to 0.7.15: the channel its plugin's startup command named.
  [2, { fields: ['channel'], events: BEFORE_DAEMON, kinds: KINDS,
    origin: batch => ({ channel: oneOf(batch.channel, CHANNELS, 'channel'), source: null, process: appOf(batch) }) }],
  // The build daemon joins the apps: each batch names its process, and counts files rather than naming them.
  [3, { fields: ['channel', 'process'], events: new Set(WITH_DAEMON), kinds: KINDS, origin: byProcess(PROCESSES) }],
  // Why tool calls failed, beside how many did.
  [4, { fields: ['channel', 'process'], events: new Set([...WITH_DAEMON, 'tool_failure']), kinds: KINDS,
    origin: byProcess(PROCESSES) }],
  // Why builds and snapshots failed; and each batch's id and time, which give each row an id of its own.
  [5, { fields: ['channel', 'process', 'batch', 'at'], events: new Set(NAMED_EVENTS), kinds: KINDS,
    origin: byProcess(PROCESSES), named: true }],
  // The engine's documents (`xbf`), and the sender a command starts (`cli`).
  [6, { fields: ['channel', 'process', 'batch', 'at'], events: new Set(NAMED_EVENTS), kinds: KINDS_6,
    origin: byProcess(PROCESSES_6), named: true }],
  // The controls a person used in a CAD view, and room in a batch for one event each.
  [7, { fields: ['channel', 'process', 'batch', 'at'], events: new Set([...NAMED_EVENTS, 'control']), kinds: KINDS_6,
    origin: byProcess(PROCESSES_6), named: true, maxEvents: MAX_EVENTS_7 }],
  // A live model is distinct from an actual file, even an xbf. Older schemas keep their own vocabulary.
  [8, { fields: ['channel', 'process', 'batch', 'at'], events: new Set([...NAMED_EVENTS, 'control']), kinds: KINDS_8,
    origin: byProcess(PROCESSES_6), named: true, maxEvents: MAX_EVENTS_7 }],
]);

export function isUuid(value) {
  return typeof value === 'string' && UUID.test(value);
}

/** RFC 9562's UUIDv5 of `name` in `namespace`: the same name, the same id, anywhere. */
export function uuidV5(name, namespace = ROWS) {
  const hash = createHash('sha1').update(Buffer.from(namespace.replace(/-/g, ''), 'hex')).update(name, 'utf8').digest();
  hash[6] = (hash[6] & 0x0f) | 0x50;
  hash[8] = (hash[8] & 0x3f) | 0x80;
  const hex = hash.subarray(0, 16).toString('hex');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

/** A row's id: its batch's id and its key, which one batch never repeats (`rowsOf`), made one UUID. */
export const idOf = (batch, key) => uuidV5(`${batch}/${key}`);

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
  // Schemas 5 on name their batch, so each row carries an id that is the same however often the batch is sent,
  // and the time the batch was made. Earlier schemas' rows carry neither, as ever.
  const named = schema.named ? {
    batch: isUuid(batch.batch) ? batch.batch : fail('batch is not a uuid'),
    at: Number.isInteger(batch.at) && batch.at >= 0 && batch.at <= MAX_AT ? batch.at : fail('at is not a time'),
  } : null;
  const events = batch.events;
  const most = schema.maxEvents ?? MAX_EVENTS;
  if (!Array.isArray(events) || events.length === 0 || events.length > most) fail(`events is a list of 1 to ${most}`);
  // One event per key, as cadgen sends them: a repeat is refused, never added up.
  const seen = new Set();
  const rows = [];
  events.forEach((event, index) => {
    const at = `events[${index}]`;
    if (!event || typeof event !== 'object' || Array.isArray(event) || !schema.events.has(event.name)) fail(`${at} is not an event`);
    const { key, event: name = event.name, fields } = READERS[event.name](event, at, schema.kinds);
    if (seen.has(key)) fail(`${at} is already in the batch`);
    seen.add(key);
    // A file by its code (schemas 1 and 2) is one more of its format's.
    const same = name === 'files' ? rows.find(row => row.event === 'files' && row.kind === fields.kind) : undefined;
    if (same) same.count += fields.count;
    else rows.push({ ...context, ...(named ? { id: idOf(named.batch, key), at: named.at } : {}), event: name, ...fields });
  });
  return rows;
}
