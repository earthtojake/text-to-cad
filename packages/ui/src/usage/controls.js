import { createContext, createElement, useContext, useEffect, useRef, useState } from 'react';

/**
 * Which of a CAD view's controls a person used: the host's telemetry (`ViewerHost.usage.controls`), so
 * the tools and settings that matter can be told from the ones nobody touches. Counted once, here, for
 * every host: the CAD app's views and the browser viewer send the same names, and the batch's process
 * tells them apart.
 *
 * What a report says is a name of `CONTROLS` and two whole numbers: how many times a person used it
 * since the last report, and for a control that stays on (`active`: the tool in hand, Preview) the
 * seconds it was on while the page was shown. Never a value typed, a setting's value (unless the value
 * is itself a name here: a render mode, an axis), a file's or a part's name, or when.
 *
 * Three ways to count, each a person's own act (never a renderer's, a host command's or an agent's):
 *
 *  - `used(name)`: a press — a menu item, a button, a tool's mode chosen.
 *  - `changed(name)`: a setting moved. A burst of changes, each under a second after the last (a slider
 *    dragged, a colour picked by dragging), is one change.
 *  - `active(name, on)`: a control that stays on. Each turn on is a use; its seconds run while it is on
 *    and the page is shown.
 *
 * The page reports at most every minute it has something to say, as it is hidden, and as the view goes;
 * the host's server adds the reports up into its own batch, and sends nothing without the person's yes.
 * The same names are the receiver's and cadgen's (`apps/api/src/events.mjs`, `cad_server/analytics.py`:
 * `CONTROLS`), which refuse any other.
 */
export const CONTROLS = Object.freeze(/** @type {const} */ ([
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
  'explorer', 'explorer_filter', 'file_copy_path', 'file_copy_link', 'file_reveal', 'file_open_app', 'home',
  'theme_system', 'theme_light', 'theme_dark', 'language', 'feedback',
  // Export, by format.
  'export_step', 'export_stl', 'export_threemf', 'export_glb', 'export_dxf', 'export_xbf', 'export_original',
  // The home.
  'home_search', 'home_filter_all', 'home_filter_models', 'home_filter_files', 'home_layout_grid', 'home_layout_list',
  'home_open', 'home_pick', 'home_copy_path', 'home_copy_link', 'home_reveal', 'home_pin', 'home_unpin', 'home_delete', 'home_delete_cancel',
]));

/**
 * @typedef {(typeof CONTROLS)[number]} Control
 * @typedef {{ control: Control, count: number, seconds: number }} ControlCount  One control in a report: a name of
 *   `CONTROLS`, its uses since the last report, and its whole seconds on.
 * @typedef {object} ControlUsage
 * @property {(control: string) => void} used  A press: a menu item, a button, a mode chosen.
 * @property {(control: string) => void} changed  A setting moved: a burst of moves under `BURST_MS` apart is one.
 * @property {(control: string, on: boolean, options?: { counted?: boolean }) => void} active  A control that stays
 *   on, turned on (a use, unless `counted` is false) or off; its seconds run while it is on.
 */

/** @type {ReadonlySet<string>} */
const KNOWN = new Set(CONTROLS);
/** A report at most this often while the page has something to say. */
export const REPORT_MS = 60_000;
/** Moves of one setting this close together are one change. */
export const BURST_MS = 1_000;

/**
 * The counter. It starts nothing until it counts something; `stop` reports what it holds and ends its
 * timer and its listeners, and counting again starts them again.
 *
 * @param {{ report(counts: ControlCount[]): void, now?: () => number, interval?: number,
 *   page?: { document: Document, window: Window } | null }} options  `page`: the page it counts in, for its
 *   visibility and its timer; absent (no page), it reports only when asked.
 */
export function createControlUsage({ report, now = () => Date.now(), interval = REPORT_MS,
  page = typeof window === 'undefined' ? null : { document, window } }) {
  /** @type {Map<Control, { count: number, ms: number }>} */
  const counts = new Map();
  /** @type {Map<Control, number | null>} a control that is on -> since when (null: the page is hidden) */
  const on = new Map();
  /** @type {Map<Control, number>} */
  const lastChange = new Map();
  /** @type {number | null} */
  let timer = null;
  /** @type {(name: string) => name is Control} */
  const known = name => KNOWN.has(name);
  const shown = () => !page || page.document.visibilityState !== 'hidden';
  /** @param {Control} name */
  const entry = name => {
    let found = counts.get(name);
    if (!found) counts.set(name, found = { count: 0, ms: 0 });
    return found;
  };
  // The time each control that is on has been on since it was last added up, added up now.
  /** @param {number} at */
  const accrue = at => {
    for (const [name, since] of on) {
      if (since === null) continue;
      entry(name).ms += Math.max(0, at - since);
      on.set(name, at);
    }
  };
  /** Report what was counted since the last report: whole seconds, the rest kept for the next. */
  const flush = () => {
    accrue(now());
    /** @type {ControlCount[]} */
    const sending = [];
    for (const [control, found] of counts) {
      const seconds = Math.floor(found.ms / 1000);
      if (!found.count && !seconds) continue;
      sending.push({ control, count: found.count, seconds });
      found.count = 0;
      found.ms -= seconds * 1000;
    }
    for (const [control, found] of counts) if (!found.count && !found.ms && !on.has(control)) counts.delete(control);
    if (!sending.length) return;
    try { report(sending); } catch { /* counting never fails what was counted */ }
  };
  // Hidden, a control that is on stops running, and what is held is reported (the page may not come back).
  const visibility = () => {
    const at = now();
    if (shown()) { for (const name of on.keys()) on.set(name, at); return; }
    accrue(at);
    for (const name of on.keys()) on.set(name, null);
    flush();
  };
  const start = () => {
    if (timer !== null || !page) return;
    timer = page.window.setInterval(flush, interval);
    page.document.addEventListener('visibilitychange', visibility);
    page.window.addEventListener('pagehide', flush);
  };
  const usage = {
    /** @param {string} name */
    used(name) {
      if (!known(name)) return;
      entry(name).count += 1;
      start();
    },
    /** @param {string} name */
    changed(name) {
      if (!known(name)) return;
      const at = now();
      const last = lastChange.get(name);
      lastChange.set(name, at);
      if (last === undefined || at - last >= BURST_MS) usage.used(name);
    },
    /** @param {string} name @param {boolean} turnedOn @param {{ counted?: boolean }} [options] */
    active(name, turnedOn, { counted = true } = {}) {
      if (!known(name)) return;
      if (turnedOn) {
        if (on.has(name)) return;
        on.set(name, shown() ? now() : null);
        if (counted) entry(name).count += 1;
        start();
        return;
      }
      if (!on.has(name)) return;
      const since = on.get(name);
      if (typeof since === 'number') entry(name).ms += Math.max(0, now() - since);
      on.delete(name);
    },
    flush,
    /** Report what it holds and stop: no timer and no listener until it counts again. A control on stays on. */
    stop() {
      flush();
      if (timer === null || !page) return;
      page.window.clearInterval(timer);
      timer = null;
      page.document.removeEventListener('visibilitychange', visibility);
      page.window.removeEventListener('pagehide', flush);
    },
  };
  return usage;
}

/** @type {ControlUsage} */
const NOTHING = Object.freeze({ used() {}, changed() {}, active() {} });
const ControlUsageContext = createContext(NOTHING);

/** The view's counter: one that counts nothing outside a host that counts (a picture drawn out of sight, a test). */
/** @returns {ControlUsage} */
export function useControlUsage() {
  return useContext(ControlUsageContext);
}

/**
 * Counts what a person does in the views under it, for `report` (the host's `usage.controls`); with none,
 * nothing is counted. One counter for as long as it is mounted, whatever `report` the host hands it next.
 *
 * @param {{ report?: ((counts: ControlCount[]) => void) | null, children?: import('react').ReactNode }} props
 */
export function ControlUsageProvider({ report, children }) {
  const latest = useRef(report);
  latest.current = report;
  const [usage] = useState(() => createControlUsage({ report: counts => latest.current?.(counts) }));
  useEffect(() => () => usage.stop(), [usage]);
  return createElement(ControlUsageContext.Provider, { value: report ? usage : NOTHING }, children);
}

/**
 * The tool in hand, by its mode id (null: none, as in Preview), on while it is: a use each time a person
 * takes up another, and its seconds while it is up. The tool a view opens with is not the person's choice,
 * and neither is the tool coming back as Preview closes: a use only when it differs from the last one on.
 *
 * @param {string | null} mode
 */
export function useToolControl(mode) {
  const name = mode || null;
  const usage = useControlUsage();
  /** @type {import('react').MutableRefObject<string | null>} */
  const last = useRef(null);
  useEffect(() => {
    if (!name) return undefined;
    usage.active(name, true, { counted: last.current !== null && last.current !== name });
    last.current = name;
    return () => usage.active(name, false);
  }, [usage, name]);
}
