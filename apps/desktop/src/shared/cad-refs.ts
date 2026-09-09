/**
 * The CAD reference grammar, as far as this app reads it.
 *
 * A reference is `<file>#<selectors>`, either half optional:
 * `models/bracket.step#o1.2`, `bracket.step#label.f45`, `#o1`, or a bare
 * `models/bracket.step`. The selector half mirrors `cadRefs.js` in
 * `packages/cadgen-js` (and `cad_ref_syntax.py` in cadgen), which are the
 * two authorities; this module accepts what they emit and never invents a
 * form of its own. It is pure — the transcript's links and the composer's
 * chips both read it, and a unit test can too.
 *
 *   occurrence   o1, o1.2, o1.2.f45        an assembly occurrence, or an entity of one
 *   entity       s1, f45, e3, v7           shape, face, edge, vertex of the whole file
 *   mate         m1
 *   label        bracket, bracket.f45      a labelled occurrence, or an entity of one
 *
 * and a comma-separated list of those.
 */

/** The extensions the CAD Viewer's file surface renders — the files a selector can point into. */
export const CAD_EXTENSIONS = ["step", "stp", "glb", "stl", "3mf", "dxf", "urdf", "srdf", "sdf"] as const;

const ENTITY = "[sfev]\\d+";
const OCCURRENCE = `o\\d+(?:\\.\\d+)*(?:\\.${ENTITY})?`;
const MATE = "m\\d+";
const LABEL = `[A-Za-z_][A-Za-z0-9_:]*(?:\\.${ENTITY})?`;
const SELECTOR = `(?:${OCCURRENCE}|${ENTITY}|${MATE}|${LABEL})`;

/** One selector, or a comma-separated list; the source of every regex below. */
export const SELECTOR_LIST_SOURCE = `${SELECTOR}(?:,${SELECTOR})*`;
const SELECTOR_LIST_RE = new RegExp(`^${SELECTOR_LIST_SOURCE}$`);

/** Is this the selector half of a reference — what follows the `#`? */
export function isSelectorList(candidate: string): boolean {
  return SELECTOR_LIST_RE.test(candidate);
}

/** Lowercase extension without the dot, `""` when there is none. */
export function extensionOf(file: string): string {
  const name = file.split("/").pop() ?? file;
  const dot = name.lastIndexOf(".");
  return dot > 0 ? name.slice(dot + 1).toLowerCase() : "";
}

export function isCadFile(file: string): boolean {
  return (CAD_EXTENSIONS as readonly string[]).includes(extensionOf(file));
}

export type CadReference = {
  /** Root-relative path, `""` for a bare selector. */
  file: string;
  /** The selector list without its `#`, `""` for a bare file. */
  selector: string;
  /** Optional display name from the viewer; never changes the prompt token. */
  label?: string;
};

/**
 * Split `file#selector` into its halves. Null when the text is not a
 * reference: a `#` with something other than a selector list after it, or
 * nothing on either side.
 */
export function splitReference(text: string): CadReference | null {
  const hash = text.indexOf("#");
  if (hash < 0) {
    return text ? { file: text, selector: "" } : null;
  }
  const file = text.slice(0, hash);
  const selector = text.slice(hash + 1);
  if (!isSelectorList(selector) || text.indexOf("#", hash + 1) >= 0) {
    return null;
  }
  return { file, selector };
}

/** The plain text form: `file#selector`, `#selector`, or `file`. */
export function referenceText(reference: CadReference): string {
  return reference.selector ? `${reference.file}#${reference.selector}` : reference.file;
}
