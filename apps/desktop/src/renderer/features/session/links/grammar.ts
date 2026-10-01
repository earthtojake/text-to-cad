import { SELECTOR_LIST_SOURCE, splitReference } from "@shared/cad-refs";

/**
 * What in an agent's prose might be a file (plan §8: "reference files by
 * workspace-relative path; they become links").
 *
 * A token is a candidate when it *looks* like a relative path — it has a
 * `/` in it, or an extension with a letter in it, or ends in `/` — and is
 * not a URL, not absolute, and not a home path. `models/bracket.step`,
 * `README.md`, `src/`, `bracket.step#o1.2` are candidates; `0.5.0`, `e.g`,
 * `https://x.y/z` and `~/x` are not. An absolute path (`/Users/me/p/a.step`) is a candidate too;
 * `PathLink` links it when it lies inside the thread's root. Whether a candidate is
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

/** What `remarkPathLinks` ends an absolute path's URL with, before any `#selector`; `pathTarget` reads it. */
export const ABSOLUTE_MARK = "?abs";

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
  if (candidate.startsWith("~") || candidate.startsWith("\\")) {
    return false;
  }
  // An absolute POSIX path (`/Users/me/proj/a.step`) is a candidate: whether it is a link is the
  // scope's call (`PathLink`: inside the root it opens, outside it is words). A lone `/word`
  // is a slash command, not a path, and `//` is no path.
  if (candidate.startsWith("/") && (candidate.startsWith("//") || (!candidate.slice(1).includes("/") && !EXTENSION_RE.test(candidate)))) {
    return false;
  }
  // A `..` segment climbs out of the workspace; `v1..v2.txt` is only a name.
  if (!PATH_CHARS_RE.test(candidate) || candidate.split("/").includes("..") || candidate.includes("//")) {
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

/**
 * Tokens that begin with the thread's own root, for a root the ordinary token
 * grammar cannot hold (`/Users/me/My Project`: a space splits a token, and
 * `PATH_CHARS_RE` would refuse an accented name). The root's characters are
 * taken as they are; what follows it is read as any other path.
 */
function rootedTokens(text: string, rootPath: string | null | undefined): PathToken[] {
  const root = rootPath?.replace(/\/+$/, "");
  if (!root || !root.startsWith("/") || PATH_CHARS_RE.test(root)) {
    return [];
  }
  const tokens: PathToken[] = [];
  const tail = new RegExp(`[^\\s()\\[\\]<>"'\`,;]*(?:#${SELECTOR_LIST_SOURCE})?`, "y");
  for (let at = text.indexOf(`${root}/`); at >= 0; at = text.indexOf(`${root}/`, at + 1)) {
    if (at > 0 && !/[\s()[\]<>"'`,;]/.test(text[at - 1]!)) {
      continue;
    }
    tail.lastIndex = at + root.length;
    const rest = tail.exec(text)?.[0] ?? "";
    // Read the part after the root as the path it is, under a stand-in the grammar accepts.
    const token = tokenFrom(`/r${rest}`, 0);
    if (!token) {
      continue;
    }
    tokens.push({
      start: at,
      end: at + root.length + token.end - 2,
      raw: `${root}${token.raw.slice(2)}`,
      path: `${root}${token.path.slice(2)}`,
      selector: token.selector,
    });
  }
  return tokens;
}

/** Every path-shaped token in `text`, in order. */
export function findPathTokens(text: string, rootPath?: string | null): PathToken[] {
  const rooted = rootedTokens(text, rootPath);
  const tokens: PathToken[] = [...rooted];
  TOKEN_RE.lastIndex = 0;
  for (let match = TOKEN_RE.exec(text); match; match = TOKEN_RE.exec(text)) {
    const token = tokenFrom(match[0], match.index);
    if (token && !rooted.some((other) => token.start < other.end && other.start < token.end)) {
      tokens.push(token);
    }
  }
  return tokens.sort((left, right) => left.start - right.start);
}

/** The whole string as one token, or null — for a code span that is a path. */
export function pathToken(text: string, rootPath?: string | null): PathToken | null {
  const token = rootedTokens(text, rootPath)[0] ?? tokenFrom(text, 0);
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
