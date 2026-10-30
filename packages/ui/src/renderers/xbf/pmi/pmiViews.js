import { pmiKey } from "@text-to-cad/core/lib/xbf/xbfPmi.js";
import { placeXbfDirection, placeXbfPoint } from "@text-to-cad/core/lib/xbf/xbfEntities.js";
import { invert } from "@text-to-cad/core/lib/xbf/xbfKinematics.js";
import { english } from "../../../i18n/core.js";
import { pmiShownOccurrence } from "./pmiRefs.js";

// A part's named view (`readXbfPmi`'s `views`) where the part stands: its camera and its section
// are served in the part's frame, and are seen from the first occurrence of the part that is shown,
// as its PMI is drawn there (`pmiRefs.js`). The camera turns with that occurrence's placement; the
// section is the Clip's own shape (one plane square to an axis, `{ axis, at, invert }`), so it is
// cut only where the placement keeps its axis a world axis. Turned off one (a part placed at an
// angle in an assembly), it is not cut along another, nearest axis: the view says it cannot be.
// A view made from the viewport ("View from here") is the same placement undone: the camera and
// the Clip taken back into the part's frame through that occurrence, refused where its placement
// turns the Clip's axis off the part's.

const AXES = Object.freeze(["x", "y", "z"]);
const IDENTITY = Object.freeze([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]);
// How near a world axis a placed section's normal must be: a placement's own rounding, no more.
const ON_AXIS = 1e-9;
// A coordinate free of the float noise a placement leaves (and of a negative zero).
const clean = value => Number(value.toPrecision(12)) + 0;
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const unit = (v) => {
  const length = Math.hypot(...v);
  return length > 1e-12 ? v.map(value => value / length) : null;
};

/** Why a section cannot be cut where its part stands, or made from the Clip there: one sentence, the row's and the form's (its key). */
export const PMI_SECTION_OFF = "pmi.view.sectionOff";

/**
 * A view's section (`{ axis, at, invert }`, its part's frame) where `matrix` places the part (4 x 4,
 * column-major): the Clip's settings in the scene's, or null where the placement turns its axis off
 * every world axis. Its plane keeps the side it kept: turned to point down a world axis, its
 * `invert` flips. The inverse placement takes the Clip back into the part's frame the same way.
 */
function placedSection(section, matrix) {
  const index = AXES.indexOf(section.axis);
  const along = [0, 0, 0];
  along[index] = 1;
  const normal = placeXbfDirection(matrix, along);
  const world = normal.findIndex(component => Math.abs(Math.abs(component) - 1) <= ON_AXIS);
  if (world < 0) return null;
  const point = [0, 0, 0];
  point[index] = section.at;
  return { axis: AXES[world], at: clean(placeXbfPoint(matrix, point)[world]), invert: normal[world] < 0 ? !section.invert : section.invert };
}

/**
 * Where a view is seen from: the first occurrence of its part shown (`instance`, the structure's
 * index), its camera's `direction` (from the part toward the eye) and `up` placed by that
 * occurrence, and its section as the Clip cuts it there (`section`), null where it has none or
 * where the placement turns its axis off a world axis (`sectionOff`). Null where no occurrence of
 * its part is shown, or the view is one the viewer cannot apply.
 *
 * @param {import("@text-to-cad/core/lib/xbf/xbfPmi.js").XbfPmiView} view
 * @param {readonly object[]} instances  The structure's.
 * @param {{ hidden?: readonly string[], isolated?: readonly string[] }} [shown]
 * @returns {{ instance: number, direction: number[], up: number[], section: { axis: string, at: number, invert: boolean } | null,
 *   sectionOff: boolean } | null}
 */
export function pmiViewAt(view, instances, shown = {}) {
  if (!view.supported || view.part === null) return null;
  const instance = pmiShownOccurrence(view.part, instances, shown);
  if (instance === undefined) return null;
  const matrix = instances[instance]?.matrix || IDENTITY;
  const section = view.section ? placedSection(view.section, matrix) : null;
  return { instance, direction: placeXbfDirection(matrix, view.camera.direction), up: placeXbfDirection(matrix, view.camera.up),
    section, sectionOff: Boolean(view.section) && !section };
}

/**
 * The view the viewport shows now, as its part's `view` call (`pmiCallText`'s input): seen
 * from the first occurrence of `part` that is shown, its camera the viewport's taken into the
 * part's frame through that occurrence's placement -- `direction` from the target toward the eye,
 * as a preset's, and `up` the screen's (the camera's up made square to it) -- and its section the
 * Clip's (`clip`, its settings with `at` where the plane stands, null while it is off), taken there
 * too. Refused (`problem`) where that placement turns the Clip's axis off the part's axes (it is no
 * section of the part, and is not made one along another axis), where no occurrence of the part is
 * shown, or where there is no camera to look from.
 *
 * @param {{ part: number, name: string, camera: { position: number[], target: number[], up: number[] } | null,
 *   clip: { axis: string, at: number, invert: boolean } | null, instances: readonly object[],
 *   shown?: { hidden?: readonly string[], isolated?: readonly string[] }, shows: string[], t?: (key: string, values?: object) => string }} options
 *   `shows`: the ids of the part's annotations and notes drawn now.
 * @returns {{ call: { kind: "view", name: string, camera: { direction: number[], up: number[] }, shows: string[],
 *   section: { axis: string, at: number, invert: boolean } | null } } | { problem: string }}
 */
export function pmiViewFromHere({ part, name, camera, clip, instances, shown = {}, shows, t = english }) {
  const toEye = camera ? unit(camera.position.map((value, axis) => value - camera.target[axis])) : null;
  if (!toEye) return { problem: t("pmi.view.noCamera") };
  const instance = pmiShownOccurrence(part, instances, shown);
  if (instance === undefined) return { problem: t("pmi.view.partHidden") };
  const toPart = invert(instances[instance]?.matrix || IDENTITY);
  // The screen's up: the camera's, less what of it runs along where it looks.
  const up = unit(camera.up.map((value, axis) => value - dot(camera.up, toEye) * toEye[axis]));
  if (!up) return { problem: t("pmi.view.upAlong") };
  const section = clip ? placedSection(clip, toPart) : null;
  if (clip && !section) return { problem: t(PMI_SECTION_OFF) };
  const inPart = vector => placeXbfDirection(toPart, vector).map(clean);
  return { call: { kind: "view", name, camera: { direction: inPart(toEye), up: inPart(up) }, shows: [...shows], section } };
}

/** Whether a view shows an annotation: one of its part it names, or any of its part where it names none. */
export function pmiViewShows(view, entry) {
  return entry.part === view.part && (view.shows === null || view.shows.includes(entry.id));
}

/** A view's own placements of what it shows, by each annotation's key (`pmiKey`), in its part's frame. */
export function pmiViewPlacements(view) {
  return new Map(Object.entries(view.place).map(([id, placement]) => [pmiKey(view.part, id), placement]));
}

/** What a view's row says it shows, in the language of `t`: how many it names, or all of its part's. */
export function pmiViewShowsText(view, t = english) {
  if (view.shows === null) return t("pmi.view.showsAll");
  return t(view.shows.length === 1 ? "pmi.view.showsOne" : "pmi.view.showsMany", { count: view.shows.length });
}
