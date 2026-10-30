/**
 * The views a prompt carries: how the viewer stood when each part of the annotation was drawn. A view is said in a snapshot job's own words (`camera`,
 * `display.mode` and `display.grid`, `display.clip` and `display.exploded`, `display.hidden` and
 * `display.isolated`, `display.pmi`, `kinematics` or `jointValues`, `animation`, `selection.hide` and
 * `selection.focus`, and the picture's `width` and `height`), so the prompt's views file is a job
 * `cadgen snapshot --annotation PACKET --camera authored` draws as it was.
 *
 * @typedef {{
 *   camera: { position: number[], target: number[], up: number[], orthographicHalfHeight: number },
 *   display?: { camera?: { projection: string, focalLength?: number }, mode?: string, grid?: boolean, clip?: object, exploded?: object,
 *     hidden?: string[], isolated?: string[], pmi?: false }, kinematics?: Record<string, unknown>,
 *   jointValues?: Record<string, number>, animation?: { clip: string, time: number },
 *   selection?: { hide?: string[], focus?: string[] },
 *   width: number, height: number
 * }} PromptView
 * @typedef {PromptView & { label: string }} LabelledView  A view ink was drawn in, by its label ("view 1"…).
 */

// The job reserves this resolution for an optional later snapshot, preserving the viewport's shape.
export const PROMPT_VIEW_LONG_EDGE_PX = 1600;
const filled = value => Boolean(value) && typeof value === "object" && Object.keys(value).length > 0;

/**
 * The view on screen as a prompt carries it: the viewport's camera and shape (`ShellViewport`'s
 * `promptCamera`), its display mode and Grid switch (`display.mode`, `display.grid`: a mode is a look
 * at its own defaults, so the two say how the view looked), and of the viewer's state what places the
 * parts or hides them — Clip when it is on, the one motion on screen (Explode, the pose, or a
 * routine's kept frame: `{clip, time}`), the parts hidden and isolated. A renderer whose parts are
 * named by refs (an engine document's: as Copy Prompt copies them) gives them as `hidden` and
 * `isolated`, which the view's display says as `cadgen snapshot --display` takes them; one whose
 * parts are not gives `hide` and `focus`, its `selection`. A document's PMI turned off (`pmi`
 * false) is off in the view too (`display.pmi`), as a snapshot draws it otherwise.
 *
 * @param {{ camera: PromptView["camera"], display?: PromptView["display"], width: number, height: number } | null} viewport
 * @param {{ display?: { mode?: string, grid?: boolean, clip?: { enabled?: boolean }, exploded?: { enabled?: boolean } },
 *   state?: { kinematics?: object, jointValues?: object, animation?: { clip: string, time: number } | null,
 *     hidden?: readonly string[], isolated?: readonly string[], hide?: readonly string[], focus?: readonly string[], pmi?: boolean } | null }} [viewer]
 * @returns {PromptView | null}
 */
export function promptView(viewport, { display = {}, state = null } = {}) {
  if (!viewport?.camera || !(viewport.width > 0) || !(viewport.height > 0)) return null;
  const scale = PROMPT_VIEW_LONG_EDGE_PX / Math.max(viewport.width, viewport.height);
  const view = { camera: viewport.camera, width: Math.round(viewport.width * scale), height: Math.round(viewport.height * scale) };
  const placed = {};
  // A view with a mode (a 3D view; a drawing has none) says it, and whether the grid is on.
  if (display?.mode) Object.assign(placed, { mode: display.mode, grid: display.grid === true });
  if (viewport.display?.camera) placed.camera = viewport.display.camera;
  if (display?.clip?.enabled) placed.clip = display.clip;
  // Explode only where it spreads the parts: on at no amount is the model as it stands.
  if (display?.exploded?.enabled && Number(display.exploded.amount) > 0) placed.exploded = display.exploded;
  // The parts left out of the view, and the ones it alone shows, by their refs.
  if (state?.hidden?.length) placed.hidden = [...state.hidden];
  if (state?.isolated?.length) placed.isolated = [...state.isolated];
  if (state?.pmi === false) placed.pmi = false;
  if (filled(placed)) view.display = placed;
  if (filled(state?.kinematics)) view.kinematics = state.kinematics;
  if (filled(state?.jointValues)) view.jointValues = state.jointValues;
  if (state?.animation?.clip) view.animation = { clip: state.animation.clip, time: Number(state.animation.time) || 0 };
  // A snapshot takes one or the other: the parts isolated (it ghosts the rest) when there are any,
  // else the parts hidden.
  const selection = {};
  if (state?.focus?.length) selection.focus = [...state.focus];
  else if (state?.hide?.length) selection.hide = [...state.hide];
  if (filled(selection)) view.selection = selection;
  return view;
}

// A camera moved less than this is the view it was: a nudge mid-annotation is not a new view.
const SAME_TURN_DEGREES = 2;
const SAME_SCALE = 0.05;

const direction = camera => {
  const d = camera.target.map((value, index) => value - camera.position[index]);
  const length = Math.hypot(...d) || 1;
  return d.map(value => value / length);
};
const key = value => JSON.stringify(value ?? null);

/**
 * Whether two views show the same: everything but the camera equal, and the camera turned less
 * than 2°, zoomed less than 5% and panned less than 5% of what it frames.
 * @param {PromptView} a
 * @param {PromptView} b
 */
export function sameView(a, b) {
  if (!a || !b) return false;
  for (const field of ["display", "kinematics", "jointValues", "animation", "selection"]) if (key(a[field]) !== key(b[field])) return false;
  const [da, db] = [direction(a.camera), direction(b.camera)];
  const cos = Math.min(1, Math.max(-1, da.reduce((sum, value, index) => sum + value * db[index], 0)));
  if (Math.acos(cos) * 180 / Math.PI >= SAME_TURN_DEGREES) return false;
  const [ua, ub] = [a.camera.up, b.camera.up];
  const upCos = ua.reduce((sum, value, index) => sum + value * ub[index], 0) / ((Math.hypot(...ua) * Math.hypot(...ub)) || 1);
  if (Math.acos(Math.min(1, Math.max(-1, upCos))) * 180 / Math.PI >= SAME_TURN_DEGREES) return false;
  const [ha, hb] = [a.camera.orthographicHalfHeight, b.camera.orthographicHalfHeight];
  if (Math.abs(ha - hb) / Math.max(ha, hb) >= SAME_SCALE) return false;
  const pan = Math.hypot(...a.camera.target.map((value, index) => value - b.camera.target[index]));
  return pan / (2 * Math.max(ha, hb)) < SAME_SCALE;
}

/**
 * Every prompt captures the current view plus the views that still have ink.
 * An equivalent recorded view keeps its label but uses the exact current framing in this export.
 * @param {PromptView | null} current
 * @param {readonly LabelledView[]} drawn
 * @param {readonly { view?: string }[]} items
 * @returns {LabelledView[]}
 */
export function promptViews(current, drawn, items) {
  const used = new Set(items.map(item => item.view).filter(Boolean));
  const views = drawn.filter(view => used.has(view.label));
  if (!current) return views;
  const matching = views.findLastIndex(view => sameView(view, current));
  if (matching >= 0) return views.map((view, index) => index === matching ? { ...current, label: view.label } : view);
  return [...views, { ...current, label: "current view" }];
}
