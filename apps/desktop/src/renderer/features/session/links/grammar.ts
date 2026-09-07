import { SELECTOR_LIST_SOURCE, splitReference } from "@shared/cad-refs";

/**
 * What in an agent's prose might be a file (plan §8: "reference files by
 * workspace-relative path; they become links").
 *
 * A token is a candidate when it *looks* like a relative path — it has a
 * `/` in it, or an extension with a letter in it, or ends in `/` — and is
 * not a URL, not absolute, and not a home path. `models/bracket.step`,
 * `README.md`, `src/`, `bracket.step#o1.2` are candidates; `0.5.0`, `e.g`,
 * `https://x.y/z`, `/etc/hosts` and `~/x` are not. Whether a candidate is
 * a *link* is answered later, by asking the root whether it exists
 * (`state/path-links.ts`): the grammar over-approximates on purpose, and
 * the lookup is what keeps a sentence like "run make.sh" from lighting up
 * when there is no such file.
 *
 * A trailing selector (`#o1.2`, `#label.f45`, `#o1,o2`) is kept on the
 * token when it parses as one (`@shared/cad-refs`); the file half is what
 * gets looked up.
 */
export type PathToken = {
  /** Offsets into the text, `end` exclusive. */
  start: number;
  end: number;
  /** The token as written, selector included. */
  raw: string;
  /** The file half, normalised (`./` stripped). */
  path: string;
  /** The selector half without `#`, or `""`. */
  selector: string;
};

/** Characters that end a token; they are never part of a path in prose. */
const TOKEN_RE = new RegExp(`[^\\s()\\[\\]<>"'\`,;]+(?:#${SELECTOR_LIST_SOURCE})?`, "g");
/** Punctuation a sentence hangs on the end of a path. */
const TRAILING_RE = /[.,;:!?)\]'">`]+$/;
const LEADING_RE = /^[([<'"`]+/;
const EXTENSION_RE = /\.([A-Za-z0-9]{1,10})$/;

/** The ASCII path characters a token may be made of; anything else is prose. */
const PATH_CHARS_RE = /^[A-Za-z0-9._\-/+@~%:]+$/;

/** Is this stripped token shaped like a relative path? */
export function looksLikePath(candidate: string): boolean {
  if (!candidate || candidate.includes("://") || /^[A-Za-z]:[\\/]/.test(candidate)) {
    return false;
  }
  if (candidate.startsWith("/") || candidate.startsWith("~") || candidate.startsWith("\\")) {
    return false;
  }
  if (!PATH_CHARS_RE.test(candidate) || candidate.includes("..") || candidate.includes("//")) {
    return false;
  }
  // `foo:` is a label or a drive, not a path; `a:b/c` is neither.
  if (candidate.includes(":")) {
    return false;
  }
  if (candidate.endsWith("/")) {
    return candidate.length > 1;
  }
  const last = candidate.split("/").pop() ?? candidate;
  if (candidate.includes("/")) {
    // A path with a folder in it needs nothing more — `src/main` is a path.
    return last !== "" && last !== ".";
  }
  const extension = EXTENSION_RE.exec(last)?.[1];
  // A bare word is a file only with an extension that has a letter in it:
  // `README.md`, `part.step`, `Makefile.in` — not `0.5.0`, not `3.14`.
  return extension !== undefined && /[A-Za-z]/.test(extension) && last.length > extension.length + 1;
}

/** Every path-shaped token in `text`, in order. */
export function findPathTokens(text: string): PathToken[] {
  const tokens: PathToken[] = [];
  TOKEN_RE.lastIndex = 0;
  for (let match = TOKEN_RE.exec(text); match; match = TOKEN_RE.exec(text)) {
    const token = tokenFrom(match[0], match.index);
    if (token) {
      tokens.push(token);
    }
  }
  return tokens;
}

/** The whole string as one token, or null — for a code span that is a path. */
export function pathToken(text: string): PathToken | null {
  const token = tokenFrom(text, 0);
  return token && token.start === 0 && token.end === text.length ? token : null;
}

function tokenFrom(raw: string, at: number): PathToken | null {
  const leading = LEADING_RE.exec(raw)?.[0].length ?? 0;
  let body = raw.slice(leading);
  // A selector is read first, whole; failing that, the prose punctuation a
  // sentence hangs on the end (`see README.md.`, `at bracket.step#o1.2,`) is
  // shed and the token read again.
  let split = splitReference(body);
  if (!split || !split.selector) {
    body = body.replace(TRAILING_RE, "");
    split = splitReference(body);
  }
  if (!split && body.includes("#")) {
    // `#` followed by something that is no selector: the file before it may
    // still be one (`bracket.step#9x`, a markdown heading anchor).
    body = body.slice(0, body.indexOf("#")).replace(TRAILING_RE, "");
    split = splitReference(body);
  }
  if (!split) {
    return null;
  }
  let { selector } = split;
  const normalised = split.file.startsWith("./") ? split.file.slice(2) : split.file;
  if (!looksLikePath(normalised)) {
    return null;
  }
  // A selector on a file that cannot carry one is not a reference.
  if (selector && !isSelectorHost(normalised)) {
    selector = "";
    body = split.file;
  }
  const start = at + leading;
  return { start, end: start + body.length, raw: body, path: normalised.replace(/\/+$/, ""), selector };
}

/** Selectors point into CAD files, and into the generators that make them. */
function isSelectorHost(file: string): boolean {
  return /\.(step|stp|glb|stl|3mf|dxf|urdf|srdf|sdf)(\.py)?$/i.test(file);
}
