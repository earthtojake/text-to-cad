/**
 * What text-to-cad sends (`cad_server/analytics.py`), checked field by field and turned into rows. Every schema a
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
 *   arrival   one step of how a computer got to the sending version (schema 11's): its setup, its server serving
 *             for the first time, or the hand-over that server runs after it (`ARRIVAL_OUTCOMES`), how it ended,
 *             and where it failed why (`ARRIVAL_FAILURES`), a word cad chose; by which route (`ROUTES`), from
 *             which version (`from`, `none` for none), and for a hand-over after how many attempts.
 *   update    one attempt of cad's own update of itself that ended (schema 11's), counted once by the server that
 *             runs after it: the version before (`from`), how it ended (`UPDATE_OUTCOMES`), for a failure which
 *             step failed (`UPDATE_FAILURES`), a word cad chose, its tries, the installer (`UPDATE_INSTALLERS`),
 *             whether it was typed (`asked`), and for a newer cad installed how the install command's run for it
 *             ended (`plugin`, `UPDATE_PLUGIN`: `underway` where a new attempt began before it ended; `none` for any
 *             other outcome).
 *   install   one run of the plugin's install in the agent apps (schema 12's; `cad plugin install`, `cad plugin
 *             update`): who began it (`INSTALL_BY`), how it ended (`INSTALL_OUTCOMES`), what its terminal showed
 *             (`INSTALL_LOGOS`, `INSTALL_COLOURS`), the whole seconds it took, how many apps it found and how many
 *             of those failed.
 *   install_app
 *             one app of such a run (schema 12's): which (`app`, the install's own key for it, checked by its shape),
 *             what was done there (`INSTALL_STATUSES`), for a failure why (`INSTALL_FAILURES`), a word cad chose, and
 *             the whole seconds it took. Its row names the app `plugin_app`: a row's `app` is the batch's, the agent
 *             app running cad.
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
 * their mixed model/file usage cannot be separated after the fact. Schema 9 says which part of a snapshot's
 * request a refusal named (`part`, `SNAPSHOT_PARTS`: a word cadgen chose, never the value; `none` for a failure
 * that was no refusal), and two more reasons a snapshot or a build failed, the machine's: no OpenGL context
 * (`no_gl`, a snapshot's) and no kernel process the engine could start (`no_kernel`). A schema before it sends
 * none of them, and its rows are read, and keyed, as ever. Schema 10 is schema 9 with one more reason a CAD tool's call
 * failed, the machine's: no kernel process the engine could start for it (`no_kernel`), which earlier schemas counted
 * as `other`; and that failure's crash says which failure it was (`cause`, `KERNEL_CAUSES`: a word cadgen chose
 * where it classified the failure, never read from its message), on that crash's type alone; and one more reason a
 * build failed, the server older than the library that asked it (`outdated`), earlier `export_error`. A model build's
 * `failed` from schema 10 counts the failures the system or the machine caused alone: a script that raised is in its
 * `count`, never `failed`. A schema before it sends none of these, and its rows are read, and keyed, as ever.
 *
 * Schema 11 (text-to-cad 0.11.12 on) describes an install with one field, `app`, the agent app running it, detected
 * (`AGENT_APPS`): an open set, checked by its shape and not by a list. It sends no channel, and its rows carry none.
 * A batch of schema 10 or earlier is translated on arrival (`translated`): its rows carry a `channel` and an `app`,
 * worked out from the old combined channel and the MCP client's name, and the old channel as it was sent
 * (`legacy_channel`). Every schema before it is still checked as it always was, and its rows keep their ids. A
 * development build's schema 11 batch that still names a channel (no release sent one) is refused, as any batch
 * with a field its schema lacks.
 * Schema 11 adds `arrival`, which no schema before it sends: whether a computer's update or install reached the
 * version, step by step, so a computer stuck on its way to one is counted; and `update`, which no schema before it
 * sends either: whether each of cad's own updates of itself went, and where one did not, which step failed.
 *
 * Schema 12 is schema 11 with `install` and `install_app`, which no schema before it sends: cad installs the plugin
 * in the agent apps itself (`cad plugin install`), so it counts each run and each app of it, where before the install
 * command did that work and counted nothing.
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
// A crash's frame, as the server names one (`cad_server/analytics.py`: `signature`; a page's: core's `crashOf`).
// A path inside a place: segments of letters, digits and `_.+-`, none of them `.` or `..`.
const FRAME_FILE = /^(?:<user>|<\?>|<frozen>|(?!\.\.?(?:\/|$))[A-Za-z0-9_.+-]{1,64}(?:\/(?!\.\.?(?:\/|$))[A-Za-z0-9_.+-]{1,64}){0,8})$/;
// A frame in our own code: the library's (`cad/`) and the server's (`cad_server/`), and, from releases before
// 0.10, the one package they were (`cadgen/`).
export const OUR_FRAMES = /^(?:cad|cad_server|cadgen)\//;
export const FUNCTION = /^(?:<user>|<\?>|[A-Za-z_$<][A-Za-z0-9_$.<>]{0,79})$/;
export const TYPE = /^(?:<user>|<\?>|[A-Za-z_][A-Za-z0-9_.]{0,127})$/;
export const MAX_BYTES = 64 * 1024;

const SHARED = new Set(['schema', 'install', 'session', 'version', 'platform', 'arch', 'client', 'presentation', 'events']);
// Schemas 2 to 10: where the install came from, as its plugin's startup command named it, a closed list.
// `-github`: by hand from the repository, and through 0.11 the install command too; `-install`: the install
// command. Every schema up to 10 reads them all; each is translated to schema 11's two fields (`translated`).
const CHANNELS = new Set(['claude-github', 'codex-github', 'cursor-github', 'gemini-github', 'claude-install',
  'codex-install', 'cursor-install', 'gemini-install', 'claude-desktop', 'claude-directory', 'openai-directory',
  'cursor-marketplace', 'agent-plugins', 'dev', 'unknown']);
const SOURCES = new Set(['store', 'manual']);
// Schema 11's: the agent app running the copy. An open set, checked by its shape (`cad_server/_internal/engine_host.py`
// makes it).
const APP = /^[a-z0-9][a-z0-9._-]{0,39}$/;
// The app an MCP client's name stands for, where the name is not the app's own: the same table as the server's
// (`cad_server/_internal/engine_host.py`: `APPS`). Any other client's name is its own app, made a token (`appOfClient`).
export const AGENT_APPS = {
  'codex-mcp-client': 'codex', 'cursor-vscode': 'cursor', 'claude-code': 'claude-code', 'claude-ai': 'claude-desktop',
  'gemini-cli': 'gemini', 'grok-build': 'grok', 'visual studio code': 'vscode', 'visual-studio-code': 'vscode',
};
// Client names that are no MCP client: the browser viewer's page names itself (`cad-viewer`, `cadgen-viewer` before
// 0.10), and a client that could not say sends `unknown`. They name no app.
const NO_APP = new Set(['cad-viewer', 'cadgen-viewer', 'unknown']);
// A schema 10 or earlier channel, as the delivery channel it was: a store's copy carries the store's channel, every
// copy of ours or a person's own is the default channel's, and `dev` and `unknown` stay as they were.
const LEGACY_CHANNELS = { 'claude-directory': 'claude', 'openai-directory': 'codex', dev: 'dev', unknown: 'unknown' };
// And the app it names, by its prefix, where the batch's MCP client said nothing.
const LEGACY_APPS = [[/^claude-desktop$/, 'claude-desktop'], [/^claude-/, 'claude-code'], [/^(?:codex-|openai-directory$)/, 'codex'],
  [/^cursor-/, 'cursor'], [/^gemini-/, 'gemini']];
// Who sends, and the formats an event counts: each schema's own (`SCHEMAS`), the later a superset.
const PROCESSES = new Set(['app', 'viewer', 'daemon']);
const PROCESSES_6 = new Set([...PROCESSES, 'cli']);
export const PLATFORMS = new Set(['darwin', 'linux', 'win32', 'other']);
const PRESENTATIONS = new Set(['tabs', 'inline', 'text', 'browser']);
const CHUNK_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const KINDS = new Set(['step', 'stl', '3mf', 'glb', 'dxf', 'urdf', 'srdf', 'sdf']);
const KINDS_6 = new Set([...KINDS, 'xbf']);
const KINDS_8 = new Set([...KINDS_6, 'model', 'kicad_pcb', 'kicad_sch']);
const VIAS = new Set(['script', 'command']);
const FEATURES = new Set(['assembly', 'declared_mesh', 'kinematics', 'animation', 'drawing', 'quick_edit']);
// What a person used in a CAD view (`cad_server/analytics.py`: `CONTROLS`, the page's own in `@cad/ui`'s
// `usage/controls.js`): a closed list of names the page chose, never a value typed or a file's.
export const CONTROLS = new Set([
  // The tools on the strip, each one a mode that stays on (its seconds counted), and Preview; Explode
  // and Clip are popovers from their tiles, no mode, counted as used each time one opens (no seconds).
  'select', 'pencil', 'shapes', 'measure', 'explode', 'clip', 'preview',
  // Select's and Measure's filters (Group faces and Group edges, which older releases send).
  'select_filter_all', 'select_filter_parts', 'select_filter_faces', 'select_filter_edges', 'select_filter_position',
  'select_filter_links', 'select_group_faces', 'select_group_edges',
  'select_filter_annotations', 'select_filter_measurements', 'select_filter_texts', 'select_filter_tracks', 'select_filter_vias',
  'select_filter_pads', 'select_filter_graphics', 'select_filter_zones', 'select_filter_rule_areas', 'select_filter_dimensions',
  'select_filter_locked', 'select_filter_symbols', 'select_filter_pins', 'select_filter_wires', 'select_filter_labels',
  'select_filter_sheets', 'select_filter_other',
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
  // The floating sidebar's sections (which older releases send), and the trees.
  'sidebar_tree', 'sidebar_position', 'sidebar_animation', 'sidebar_layers', 'sidebar_sdf',
  'tree_filter', 'tree_visibility', 'layer_visibility',
  // A part's menu, over the model or in its tree, and the view's menu's Select tangent faces and edges.
  'menu_copy_reference', 'menu_select', 'menu_isolate', 'menu_exit_all_isolates', 'menu_hide_others', 'menu_show_all',
  'menu_hide', 'menu_reveal', 'menu_expand', 'menu_collapse', 'menu_expand_all', 'menu_collapse_all', 'menu_zoom_fit',
  'menu_zoom_selection',
  'menu_select_tangent_faces', 'menu_select_tangent_edges',
  // The view itself: a double-click's Look at and isolate, the view cube, F's fit.
  'look_at', 'isolate', 'view_cube', 'view_cube_drag', 'fit',
  // Quick Edit's Copy, Queue and Send.
  'quick_edit_copy', 'quick_edit_queue', 'quick_edit_send',
  // The navbar, its file menu and its name menu's Models and Files (the explorer), and the app menu.
  'navbar_back', 'navbar_forward', 'models', 'models_open', 'models_filter',
  'explorer', 'explorer_filter', 'file_copy_path', 'file_copy_link', 'file_reveal', 'file_open_app', 'home',
  'theme_system', 'theme_light', 'theme_dark', 'language', 'feedback',
  // Export, by format.
  'export_step', 'export_stl', 'export_threemf', 'export_glb', 'export_dxf', 'export_xbf', 'export_original',
  'export_gerbers', 'export_drill', 'export_pos', 'export_bom', 'export_odb', 'export_ipc', 'export_pdf',
  // The home.
  'home_search', 'home_filter_all', 'home_filter_models', 'home_filter_files', 'home_layout_grid', 'home_layout_list',
  'home_open', 'home_pick', 'home_copy_path', 'home_copy_link', 'home_reveal', 'home_pin', 'home_unpin', 'home_delete', 'home_delete_cancel',
]);
const WHERE = new Set(['tool', 'route', 'request', 'build', 'command', 'page']);
// Why a CAD tool's call failed (`cad_server/analytics.py`: `FAILURES`): the caller's, the view's, the machine's or
// cadgen's own, as cadgen named it where the call failed.
const FAILURES = new Set(['no_path', 'relative_path', 'no_file', 'not_cad', 'no_view', 'wrong_view', 'bad_request',
  'timeout', 'view_error', 'too_large', 'no_viewer', 'bug', 'other']);
// Why a build failed (`cad_server/analytics.py`: `BUILD_FAILURES`), from what the error was and whose code raised it:
// the model's, the CAD kernel's under it, cadgen's refusal or its mistake, the machine's.
const BUILD_FAILURES = new Set(['model_error', 'kernel_error', 'refused', 'script_error', 'arguments', 'child_failed',
  'missing_module', 'missing_file', 'io_error', 'timeout', 'memory', 'export_error', 'bug', 'other']);
// Why a snapshot failed (`SNAPSHOT_FAILURES`), by what it was doing or what the error was.
const SNAPSHOT_FAILURES = new Set(['bad_request', 'no_file', 'input_error', 'browser', 'timeout', 'memory', 'render_error',
  'bug', 'other']);
// Schema 9's: no OpenGL context to draw in (`no_gl`: no X display, no GLX, a GDI 1.1), and the engine could not
// start the kernel process the work runs in (`no_kernel`), which earlier schemas counted as a refusal.
const SNAPSHOT_FAILURES_9 = new Set([...SNAPSHOT_FAILURES, 'no_gl', 'no_kernel']);
const BUILD_FAILURES_9 = new Set([...BUILD_FAILURES, 'no_kernel']);
// Schema 10's: a CAD tool's call the engine could start no kernel process for (`no_kernel`), earlier `other`; and
// a build (an export) the CAD server running did without an option the library asked of it, being older
// (`outdated`), earlier `export_error`.
const FAILURES_10 = new Set([...FAILURES, 'no_kernel']);
const BUILD_FAILURES_10 = new Set([...BUILD_FAILURES_9, 'outdated']);
// Why the engine could start no kernel process, on that crash (`exception`'s `cause`), schema 10's
// (`cad_server/analytics.py`: `KERNEL_CAUSES`): the system refused the process pool, or the kernel environment could
// not be made -- the network, a denial, uv killed, the installation's Python, resolving or installing the release, a
// file, no uv, the made environment not running -- or none of these.
const KERNEL_CAUSES = new Set(['pool', 'network', 'denied', 'killed', 'python', 'resolve', 'install', 'files', 'uv',
  'probe', 'other']);
const KERNEL_UNAVAILABLE = 'cad.engine.serve.KernelProcessesUnavailable';
// Which part of a snapshot's request a refusal (`bad_request`) named, schema 9's (`cad_server/analytics.py`:
// `SNAPSHOT_PARTS`): a word cadgen chose where it refused, never the value given. `none`: a failure that was no
// refusal.
const SNAPSHOT_PARTS = new Set(['source', 'out', 'display', 'display.mode', 'display.exploded', 'display.clip',
  'display.grid', 'display.visibility', 'camera', 'pose', 'size', 'annotation', 'measurements', 'references', 'job',
  'other']);
// How a computer got to a version, schema 11's (`cad_server/analytics.py`: `ROUTES`, `ARRIVAL_OUTCOMES`,
// `ARRIVAL_FAILURES`): an earlier release's updater or `cad setup` itself; each step's endings; why a step failed, a
// word cad chose where it failed (a step that cannot fail has none); and the version it came from, a version's name
// or `none`, as short as a batch's `version`.
const ROUTES = new Set(['updater', 'setup']);
const ARRIVAL_OUTCOMES = {
  setup: new Set(['ok', 'failed']), serving: new Set(['ok']), handover: new Set(['done', 'failed', 'gave_up', 'superseded']),
};
const ARRIVAL_FAILURES = { setup: new Set(['uv', 'network', 'denied', 'other']), handover: new Set(['no_report', 'setup', 'app', 'other']) };
const EARLIER = /^(?:none|[0-9][0-9A-Za-z.+_-]{0,31})$/;
const MAX_ATTEMPTS = 1000;
// How cad's own update of itself ended, schema 11's (`cad_server/analytics.py`: `UPDATE_OUTCOMES`, `UPDATE_FAILURES`,
// `UPDATE_INSTALLERS`, `UPDATE_PLUGIN`): a newer cad installed, nothing newer, failed, or failed and the release
// before put back; for a failure which step, a word cad chose (the installer's upgrade, a release it may not end on,
// and for one not put back the put-back too); the installer that made the global install; and the install command's
// run for the cad an update installed (`ok`, `failed`, `underway` where a new attempt began before it ended; `none`
// where none ran for it, and for any other outcome). Tries from 1, as many as attempts.
const UPDATE_OUTCOMES = new Set(['installed', 'current', 'failed', 'restored']);
const UPDATE_FAILURES = { failed: new Set(['upgrade', 'older', 'put_back']), restored: new Set(['upgrade', 'older']) };
const UPDATE_INSTALLERS = new Set(['uv', 'pipx']);
const UPDATE_PLUGIN = new Set(['none', 'ok', 'failed', 'underway']);
// One run of the plugin's install in the agent apps, schema 12's (`cad_server/analytics.py`): who began it -- a person
// who typed the command, the install command handing over, or cad's server; how it ended -- well, every app found
// failed, or another run held the lock and this one left at once; what its terminal showed -- the logo built, the
// logo still, none, or one that failed, in which colours; and each app of it -- what was done there, and for a
// failure why, a word cad chose where it failed. A run and an app each take whole seconds, and a run finds so many
// apps at most.
const INSTALL_BY = new Set(['person', 'script', 'server']);
const INSTALL_OUTCOMES = new Set(['ok', 'failed', 'busy']);
const INSTALL_LOGOS = new Set(['played', 'still', 'none', 'failed']);
const INSTALL_COLOURS = new Set(['24bit', '256', 'none']);
const INSTALL_STATUSES = new Set(['installed', 'updated', 'removed', 'skipped', 'failed']);
const INSTALL_FAILURES = new Set(['timeout', 'command', 'network', 'exception', 'other']);
const MAX_INSTALL_SECONDS = 100_000;
const MAX_INSTALL_APPS = 64;
// A batch's time, in whole seconds since 1970: any a clock can say (a wrong one included), never a fraction.
export const MAX_AT = 100_000_000_000;
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
  snapshot_failure: ['kind', 'reason', 'part', 'count'], // `part` from schema 9
  feature: ['feature', 'count'],
  health: ['workers', 'crashes', 'recycles', 'refusals'],
  control: ['control', 'count', 'seconds'],
  exception: ['where', 'tool', 'type', 'handled', 'status', 'frames', 'count'],
  arrival: ['step', 'route', 'from', 'outcome', 'reason', 'attempts', 'count'], // `reason`, `attempts` where they apply
  update: ['from', 'outcome', 'reason', 'tries', 'installer', 'asked', 'plugin', 'count'], // `reason` for a failure
  install: ['by', 'outcome', 'logo', 'colour', 'seconds', 'found', 'failed', 'count'],
  // `plugin_app`: the event's `app`, the app the plugin was installed in (a row's `app` is the batch's); `reason` for a failure
  install_app: ['plugin_app', 'status', 'reason', 'seconds', 'count'],
};

export class Invalid extends Error {}
/**
 * A batch of a schema newer than this receiver reads: a release that reached people before the receiver that reads
 * its schema was deployed. Never refused, which the sender would take as final: answered "try later" (503), so the
 * sender keeps it and sends it again once this receiver reads it.
 */
export class Later extends Error {}

const fail = message => { throw new Invalid(message); };
export const token = (value, name, limit = 64) =>
  typeof value === 'string' && value.length <= limit && TOKEN.test(value) ? value : fail(`${name} is not a short token`);
export const oneOf = (value, allowed, name) => (allowed.has(value) ? value : fail(`${name} is not one of ${[...allowed].join(', ')}`));
const count = (value, name) => (Number.isInteger(value) && value >= 0 && value <= MAX_COUNT ? value : fail(`${name} is not a count`));
const some = (value, name) => (count(value, name) > 0 ? value : fail(`${name} counts nothing`));
// A process's exit status: an exit code or a signal (-N), or on Windows the exception code a fault ended it
// with (an NTSTATUS error, 0xC0000000 and up).
const exitStatus = value => Number.isInteger(value) && (Math.abs(value) < 512 || (value >= 0xC0000000 && value <= 0xFFFFFFFF));
export const matches = (value, pattern, name) => (typeof value === 'string' && pattern.test(value) ? value : fail(`${name} is not one`));
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
// How long a run of the plugin's install, or one app of it, took (whole seconds), and how many apps a run found.
const installSeconds = (value, name) =>
  (Number.isInteger(value) && value >= 0 && value <= MAX_INSTALL_SECONDS ? value : fail(`${name} is not whole seconds`));
const installApps = (value, name) =>
  (Number.isInteger(value) && value >= 0 && value <= MAX_INSTALL_APPS ? value : fail(`${name} is not a number of apps`));
export const only = (object, keys, name) => {
  for (const key of Object.keys(object)) if (!keys.includes(key)) fail(`${name} has an unknown field ${key}`);
};
// An event's fields, every one of them there and no other.
const exactly = (event, fields, name) => {
  only(event, ['name', ...fields], name);
  for (const field of fields) if (event[field] === undefined) fail(`${name} has no ${field}`);
};

// Each event as a schema sends it: its key in the batch (one event per key), and its row's fields. A format is
// one of the schema's own (`schema.kinds`), and so is a failure's reason.
const READERS = {
  tool(event, at) {
    only(event, ['name', 'tool', 'calls', 'errors'], at);
    const tool = typeof event.tool === 'string' && TOOL.test(event.tool) ? event.tool : fail(`${at}.tool is not a tool`);
    const calls = some(event.calls, `${at}.calls`);
    const errors = event.errors === undefined ? 0 : count(event.errors, `${at}.errors`);
    if (errors > calls) fail(`${at} counts more errors than calls`);
    return { key: `tool ${tool}`, fields: { tool, calls, errors } };
  },
  tool_failure(event, at, { toolFailures = FAILURES }) {
    exactly(event, FIELDS.tool_failure, at);
    const tool = matches(event.tool, TOOL, `${at}.tool`);
    const reason = oneOf(event.reason, toolFailures, `${at}.reason`);
    return { key: `tool_failure ${tool} ${reason}`, fields: { tool, reason, count: some(event.count, `${at}.count`) } };
  },
  view(event, at) {
    only(event, ['name', 'calls'], at);
    return { key: 'view', fields: { calls: some(event.calls, `${at}.calls`) } };
  },
  file(event, at, { kinds }) {
    only(event, ['name', 'file', 'kind'], at);
    const file = typeof event.file === 'string' && FILE_CODE.test(event.file) ? event.file : fail(`${at}.file is not a file code`);
    return { key: `file ${file}`, event: 'files', fields: { kind: oneOf(event.kind, kinds, `${at}.kind`), count: 1 } };
  },
  files(event, at, { kinds }) {
    exactly(event, FIELDS.files, at);
    const kind = oneOf(event.kind, kinds, `${at}.kind`);
    return { key: `files ${kind}`, fields: { kind, count: some(event.count, `${at}.count`) } };
  },
  build(event, at, { kinds }) {
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
  build_failure(event, at, { kinds, buildFailures = BUILD_FAILURES }) {
    exactly(event, FIELDS.build_failure, at);
    const kind = oneOf(event.kind, kinds, `${at}.kind`);
    const via = oneOf(event.via, VIAS, `${at}.via`);
    const reason = oneOf(event.reason, buildFailures, `${at}.reason`);
    return { key: `build_failure ${kind} ${via} ${reason}`, fields: { kind, via, reason, count: some(event.count, `${at}.count`) } };
  },
  snapshot_failure(event, at, { kinds, parts, snapshotFailures = SNAPSHOT_FAILURES }) {
    exactly(event, parts ? FIELDS.snapshot_failure : FIELDS.snapshot_failure.filter(field => field !== 'part'), at);
    const kind = oneOf(event.kind, kinds, `${at}.kind`);
    const reason = oneOf(event.reason, snapshotFailures, `${at}.reason`);
    const count = some(event.count, `${at}.count`);
    // Before schema 9 a failure names no part, and its row's key is as it ever was (a batch sent again keeps its ids).
    if (!parts) return { key: `snapshot_failure ${kind} ${reason}`, fields: { kind, reason, count } };
    // A refusal names the part of the request it refused; any other failure, none.
    const part = reason === 'bad_request' ? oneOf(event.part, SNAPSHOT_PARTS, `${at}.part`)
      : (event.part === 'none' ? 'none' : fail(`${at}.part is none: only a refusal names a part`));
    return { key: `snapshot_failure ${kind} ${reason} ${part}`, fields: { kind, reason, part, count } };
  },
  snapshot(event, at, { kinds }) {
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
  exception(event, at, { causes = false }) {
    only(event, ['name', ...FIELDS.exception, ...(causes ? ['cause'] : [])], at);
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
    // Schema 10's: which failure left the engine no kernel process, on that crash alone; a crash without one is
    // keyed as ever.
    if (event.cause !== undefined) {
      if (fields.type !== KERNEL_UNAVAILABLE) fail(`${at}: only ${KERNEL_UNAVAILABLE} names a cause`);
      fields.cause = oneOf(event.cause, KERNEL_CAUSES, `${at}.cause`);
      crash.push(fields.cause);
    }
    return { key: `exception ${JSON.stringify(crash)}`, fields };
  },
  // A reason only with `failed`, attempts only for a hand-over: each where it applies and nowhere else.
  arrival(event, at) {
    only(event, ['name', ...FIELDS.arrival], at);
    const step = typeof event.step === 'string' && Object.hasOwn(ARRIVAL_OUTCOMES, event.step)
      ? event.step : fail(`${at}.step is not one of ${Object.keys(ARRIVAL_OUTCOMES).join(', ')}`);
    const route = oneOf(event.route, ROUTES, `${at}.route`);
    const from = matches(event.from, EARLIER, `${at}.from`);
    const outcome = oneOf(event.outcome, ARRIVAL_OUTCOMES[step], `${at}.outcome`);
    const reason = outcome === 'failed' ? oneOf(event.reason, ARRIVAL_FAILURES[step], `${at}.reason`)
      : (event.reason === undefined ? null : fail(`${at}.reason: only a failed step names one`));
    const attempts = step === 'handover'
      ? (Number.isInteger(event.attempts) && event.attempts >= 0 && event.attempts <= MAX_ATTEMPTS
        ? event.attempts : fail(`${at}.attempts is not a hand-over's attempts`))
      : (event.attempts === undefined ? null : fail(`${at}.attempts: only a hand-over counts them`));
    const count = some(event.count, `${at}.count`);
    return { key: `arrival ${JSON.stringify([step, route, from, outcome, reason, attempts])}`,
      fields: { step, route, from, outcome, reason, attempts, count } };
  },
  // A reason only with a failure (`failed`, `restored`), the install command's run only for a newer cad installed.
  update(event, at) {
    only(event, ['name', ...FIELDS.update], at);
    const from = matches(event.from, EARLIER, `${at}.from`);
    const outcome = oneOf(event.outcome, UPDATE_OUTCOMES, `${at}.outcome`);
    const reason = Object.hasOwn(UPDATE_FAILURES, outcome) ? oneOf(event.reason, UPDATE_FAILURES[outcome], `${at}.reason`)
      : (event.reason === undefined ? null : fail(`${at}.reason: only a failed update names one`));
    const tries = Number.isInteger(event.tries) && event.tries >= 1 && event.tries <= MAX_ATTEMPTS
      ? event.tries : fail(`${at}.tries is not an update's tries`);
    const installer = oneOf(event.installer, UPDATE_INSTALLERS, `${at}.installer`);
    if (typeof event.asked !== 'boolean') fail(`${at}.asked is not true or false`);
    const plugin = oneOf(event.plugin, UPDATE_PLUGIN, `${at}.plugin`);
    if (plugin !== 'none' && outcome !== 'installed') fail(`${at}.plugin: only an update that installed a newer cad ran it`);
    const count = some(event.count, `${at}.count`);
    return { key: `update ${JSON.stringify([from, outcome, reason, tries, installer, event.asked, plugin])}`,
      fields: { from, outcome, reason, tries, installer, asked: event.asked, plugin, count } };
  },
  // A run failed where every app it found failed, and nowhere else; one that found the lock held looked for none.
  install(event, at) {
    exactly(event, FIELDS.install, at);
    const by = oneOf(event.by, INSTALL_BY, `${at}.by`);
    const outcome = oneOf(event.outcome, INSTALL_OUTCOMES, `${at}.outcome`);
    const logo = oneOf(event.logo, INSTALL_LOGOS, `${at}.logo`);
    const colour = oneOf(event.colour, INSTALL_COLOURS, `${at}.colour`);
    const took = installSeconds(event.seconds, `${at}.seconds`);
    const [found, failed] = ['found', 'failed'].map(name => installApps(event[name], `${at}.${name}`));
    if (failed > found) fail(`${at} counts more failures than apps found`);
    if (outcome === 'busy' && found) fail(`${at}.found: a busy run looked for no app`);
    if (outcome !== 'busy' && (outcome === 'failed') !== (found > 0 && failed === found)) {
      fail(`${at}.outcome: a run failed where every app found failed, and nowhere else`);
    }
    const count = some(event.count, `${at}.count`);
    return { key: `install ${JSON.stringify([by, outcome, logo, colour, took, found, failed])}`,
      fields: { by, outcome, logo, colour, seconds: took, found, failed, count } };
  },
  // The app by the install's own key for it, never the batch's `app`; a reason only with `failed`.
  install_app(event, at) {
    only(event, ['name', 'app', 'status', 'reason', 'seconds', 'count'], at);
    const app = matches(event.app, APP, `${at}.app`);
    const status = oneOf(event.status, INSTALL_STATUSES, `${at}.status`);
    const reason = status === 'failed' ? oneOf(event.reason, INSTALL_FAILURES, `${at}.reason`)
      : (event.reason === undefined ? null : fail(`${at}.reason: only a failed app names one`));
    const took = installSeconds(event.seconds, `${at}.seconds`);
    const count = some(event.count, `${at}.count`);
    return { key: `install_app ${JSON.stringify([app, status, reason, took])}`,
      fields: { plugin_app: app, status, reason, seconds: took, count } };
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
  // Which part of a snapshot's request a refusal named, and the machine's two reasons more: no OpenGL context, no
  // kernel process.
  [9, { fields: ['channel', 'process', 'batch', 'at'], events: new Set([...NAMED_EVENTS, 'control']), kinds: KINDS_8,
    origin: byProcess(PROCESSES_6), named: true, maxEvents: MAX_EVENTS_7, parts: true,
    snapshotFailures: SNAPSHOT_FAILURES_9, buildFailures: BUILD_FAILURES_9 }],
  // And the machine's reason a CAD tool's call failed: no kernel process, and on its crash which failure it was;
  // and a build's reason the server is older than the library (`outdated`).
  [10, { fields: ['channel', 'process', 'batch', 'at'], events: new Set([...NAMED_EVENTS, 'control']), kinds: KINDS_8,
    origin: byProcess(PROCESSES_6), named: true, maxEvents: MAX_EVENTS_7, parts: true,
    snapshotFailures: SNAPSHOT_FAILURES_9, buildFailures: BUILD_FAILURES_10, toolFailures: FAILURES_10, causes: true }],
  // Schema 10 with the install described by the agent app alone, checked by its shape, and no channel: a row of it
  // carries none (`null`, which no store is sent). Every earlier schema's batch is translated (`translated`). And how a
  // computer got to the version, and how each of cad's own updates went.
  [11, { fields: ['app', 'process', 'batch', 'at'], events: new Set([...NAMED_EVENTS, 'control', 'arrival', 'update']), kinds: KINDS_8,
    origin: batch => ({ channel: null, app: matches(batch.app, APP, 'app'),
      legacy_channel: null, source: null, process: oneOf(batch.process, PROCESSES_6, 'process') }),
    current: true, named: true, maxEvents: MAX_EVENTS_7, parts: true,
    snapshotFailures: SNAPSHOT_FAILURES_9, buildFailures: BUILD_FAILURES_10, toolFailures: FAILURES_10, causes: true }],
  // Schema 11 with the plugin's install in the agent apps, which cad runs itself: each run of it, and each app of one.
  [12, { fields: ['app', 'process', 'batch', 'at'], events: new Set([...NAMED_EVENTS, 'control', 'arrival', 'update', 'install', 'install_app']), kinds: KINDS_8,
    origin: batch => ({ channel: null, app: matches(batch.app, APP, 'app'),
      legacy_channel: null, source: null, process: oneOf(batch.process, PROCESSES_6, 'process') }),
    current: true, named: true, maxEvents: MAX_EVENTS_7, parts: true,
    snapshotFailures: SNAPSHOT_FAILURES_9, buildFailures: BUILD_FAILURES_10, toolFailures: FAILURES_10, causes: true }],
]);
const NEWEST = Math.max(...SCHEMAS.keys()); // a later schema is a newer release's (`Later`), never a refusal

/**
 * The app an MCP client's name stands for (`AGENT_APPS`), else the name itself made a token: lower case, a run of
 * anything else one `-`, at most 40 characters. `null` where it names nothing.
 */
export function appOfClient(name) {
  if (typeof name !== 'string') return null;
  const lowered = name.trim().toLowerCase();
  if (Object.hasOwn(AGENT_APPS, lowered)) return AGENT_APPS[lowered];
  if (NO_APP.has(lowered)) return null;
  return lowered.replace(/[^a-z0-9._-]+/g, '-').replace(/^[^a-z0-9]+/, '').slice(0, 40) || null;
}

/**
 * A schema 10 or earlier batch's install, as schema 11 describes it: the delivery channel its old channel was, the
 * app its MCP client names (else the one the old channel names, else `unknown`), and the old channel as sent.
 */
export function translated(legacy, client) {
  return {
    channel: LEGACY_CHANNELS[legacy] ?? 'default',
    app: appOfClient(client) ?? LEGACY_APPS.find(([prefix]) => prefix.test(legacy))?.[1] ?? 'unknown',
    legacy_channel: legacy,
  };
}

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
  if (Number.isInteger(batch.schema) && batch.schema > NEWEST) throw new Later(`schema ${batch.schema} is newer than ${NEWEST}`);
  const schema = SCHEMAS.get(batch.schema) ?? fail(`schema is not one of ${[...SCHEMAS.keys()].join(', ')}`);
  for (const key of Object.keys(batch)) if (!schema.fields.includes(key) && !SHARED.has(key)) fail(`unknown field ${key}`);
  if (!isUuid(batch.install)) fail('install is not a uuid');
  if (!isUuid(batch.session)) fail('session is not a uuid');
  const client = batch.client ?? {};
  if (typeof client !== 'object' || Array.isArray(client)) fail('client is an object');
  only(client, ['name', 'version'], 'client');
  const clientName = client.name === undefined ? null : token(client.name, 'client.name');
  const origin = schema.origin(batch);
  const context = {
    install_id: batch.install,
    session_id: batch.session,
    version: token(batch.version, 'version', 32),
    ...origin,
    // Before schema 11 the channel said where the copy came from and, often, which app: read as the two it was.
    ...(schema.current ? {} : translated(origin.channel, clientName)),
    platform: oneOf(batch.platform, PLATFORMS, 'platform'),
    arch: batch.arch === undefined ? null : token(batch.arch, 'arch', 16),
    client: clientName,
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
    const { key, event: name = event.name, fields } = READERS[event.name](event, at, schema);
    if (seen.has(key)) fail(`${at} is already in the batch`);
    seen.add(key);
    // A file by its code (schemas 1 and 2) is one more of its format's.
    const same = name === 'files' ? rows.find(row => row.event === 'files' && row.kind === fields.kind) : undefined;
    if (same) same.count += fields.count;
    else rows.push({ ...context, ...(named ? { id: idOf(named.batch, key), at: named.at } : {}), event: name, ...fields });
  });
  return rows;
}
