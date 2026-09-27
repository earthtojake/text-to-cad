// What a STEP calls a product or an occurrence, as a person should read it.
//
// A STEP names every product and every assembly usage. Where the writer had no name for one,
// OCCT's XCAF writes the document address of the label instead — its entry, `0:1:1:2`, or, for
// a reference to another label, `=>[0:1:1:2]` — and a reader hands that back as the name. A
// cadgen single-part STEP is one such file: its part sits under a root product named
// `=>[0:1:1:2]` beside the real `l_bracket`. An entry is an address, not a name somebody gave,
// so it reads as no name at all and whatever names the thing otherwise (the file, the
// occurrence) takes its place.

const XCAF_ENTRY = /^(?:=>\s*)?(?:\[\s*\d+(?::\d+)+\s*\]|\d+(?::\d+)+)$/;

/** True for an XCAF label entry (`0:1:1:2`, `[0:1:1:2]`, `=>[0:1:1:2]`) standing where a name belongs. */
export function isXcafEntryLabel(value) {
  return XCAF_ENTRY.test(String(value ?? "").trim());
}

/** A product or occurrence name as written, or "" where there is none (blank, or an XCAF entry). */
export function stepProductName(value) {
  const name = String(value ?? "").trim();
  return isXcafEntryLabel(name) ? "" : name;
}

/** A single-part file's part, named after the file: `parts/l_bracket.step` is `l_bracket`. */
export function stepPartNameFromFile(file) {
  const base = String(file ?? "").trim().split(/[\\/]/).filter(Boolean).pop() || "";
  return base.replace(/\.(?:step|stp)$/i, "");
}
