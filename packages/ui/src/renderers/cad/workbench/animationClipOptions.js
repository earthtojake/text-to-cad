// The Animation tab's Clip picker: the model's authored clips, and nothing else.
//
// The transport's idle state is not a list entry -- it is the section's gate
// switch. This list used to lead with a built-in "No clip" row standing in for
// that state, which read as an authored clip named after a state: a pose preset
// literally named `rest` (common in robot sidecars) then put two identically
// labelled entries in two tabs meaning different things. A state and a list of
// authored items are two kinds of thing, so they now live on two controls and
// cannot be read as one list. Poses never synthesise clips; nothing here
// changes which clip plays.
export function animationClipOptions(clips) {
  const authored = Array.isArray(clips) ? clips : [];
  return authored.map((clip) => ({ value: clip.id, label: clip.label }));
}
