/**
 * The fields a static result carries, by the attribute that holds them (lower-cased, as GLTFLoader
 * names it): the word Show and the colour bar call each by. Pure data: no three.js, no React.
 */

// The fields in plain words, short enough for the panel's one width, in Show and on the colour bar.
export const FIELD_WORDS = Object.freeze({
  _von_mises: "Stress",
  _displacement: "Displacement",
});

/** A field in plain words ("Stress", "Displacement"), else the name the file gives it. */
export function fieldWord(field) {
  return FIELD_WORDS[String(field.attribute || "").toLowerCase()] || field.name;
}
