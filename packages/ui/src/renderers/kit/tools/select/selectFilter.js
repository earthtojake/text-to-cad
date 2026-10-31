// What a picking tool takes, as the person chooses it from the dropdown on its chevron
// (`SelectFilterMenu.jsx`): ONE choice of what a click on the model takes, as a CAD tool's selection
// priority is (Fusion's Select > Face Priority, Blender's vertex, edge and face modes) — All,
// the default, or one kind alone. Each choice is a mode: its id, its label and the kinds it picks
// (`kinds`), and the filter the tool reads is the kinds of the mode chosen.
//
// Importing this module has no environmental effects.

const sameKinds = (left, right) => left.length === right.length && left.every(id => right.includes(id));

/** The mode `filter` is (the one whose kinds it picks), else the first: All. */
export function pickModeOf(filter, modes) {
  return modes.find(mode => sameKinds(mode.kinds, filter)) || modes[0] || null;
}

/** Whether `filter` picks `id`'s kind. */
export const selects = (filter, id) => filter.includes(id);
