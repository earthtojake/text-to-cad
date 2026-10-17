// What a single-part STEP file's part is called where it has no name of its own: the file's.
// Every name a STEP gives its products and occurrences is cadgen's to read (an address OCCT
// wrote where nobody named a thing reads as no name there); the page draws the names it is given.

/** A single-part file's part, named after the file: `parts/l_bracket.step` is `l_bracket`. */
export function stepPartNameFromFile(file) {
  const base = String(file ?? "").trim().split(/[\\/]/).filter(Boolean).pop() || "";
  return base.replace(/\.(?:step|stp)$/i, "");
}
