import { annotationsInBox, withGroups } from "../../../../annotation/geometry.js";

/**
 * What a box under Select takes, the same in every viewer (`useBoxSelectGesture.js`'s box): of each
 * kind, what the box touches, even in part, as Select's filter would take it with a click. With Shift (`additive`)
 * it is added to what is picked of that kind; otherwise it replaces it, a kind the box missed let go
 * too, so parts, measurements and ink one box takes stay picked together and nothing else does.
 */

/** A kind's picks after a box: `taken` added (`additive`) or in place of `current`; `current` itself when that is no change. */
export function boxedSelection(current, taken, additive) {
  const next = [...new Set(additive ? [...current, ...taken] : taken)];
  return next.length === current.length && next.every(id => current.includes(id)) ? current : next;
}

/** The annotation's ink a box takes (`touched`, ids), with what was drawn with it, into the session's selection. */
export function takeInkInBox(session, touched, additive) {
  const next = withGroups(boxedSelection(session.selected, touched, additive), session.items);
  if (next.length !== session.selected.length || next.some(id => !session.selected.includes(id))) session.select(next);
}

/**
 * A flat view's box (a board, a schematic, a drawing): the ink it takes (`inks`, the marks on the
 * screen, in the canvas's pixels, as `annotationsInBox` judges them), the measurements
 * (`measure`, `measureSelectHandlers`' `box`) and the picture's own (`picked`, what the renderer's
 * index found it touching, under its filter) into `selection` (`useSceneSelection`'s). How many things it
 * took, of every kind: a board names the area of a box that took none.
 *
 * @param {{ local: { left: number, top: number, right: number, bottom: number }, additive: boolean }} box
 * @param {{ annotation: { items: readonly object[], selected: readonly string[], select(ids: string[]): void },
 *   inks: readonly object[], measure: { box(box: object): string[] }, selection: { take(ids: string[], options: { additive: boolean }): void },
 *   picked: readonly string[] }} options
 */
export function takeFlatBox(box, { annotation, inks, measure, selection, picked }) {
  const touched = inks.length ? annotationsInBox(box.local, inks).map(ink => ink.id) : [];
  takeInkInBox(annotation, touched, box.additive);
  const measured = measure.box(box);
  selection.take(picked, { additive: box.additive });
  return touched.length + measured.length + picked.length;
}
