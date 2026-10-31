// Two kinds of ref. Every document the engine draws -- an `.xbf`, a STEP (`.step`, `.stp`), a
// document the engine holds by its id -- is named in the engine's own grammar, at the end of this
// module ("The engine's grammar"), the one `cadgen inspect` and `select` read. Any other file the
// viewer draws (a robot description, a mesh, a drawing) names what is picked by its renderer's own
// name for it, a plain label a selector (`robot.urdf#upper_arm`, `bracket.dxf#h2F`, `part.glb#glb:3`).
//
// `<file>#<selectors>`, file half optional, the selectors a comma list; a file's token stops at a
// blank. The prefix sits LEFT of the '#' so it can never collide with the selectors on the right.
// JSON-quote paths containing whitespace or delimiters: `"my robot.urdf"#base_link`.
const CAD_TOKEN_RE = /^\s*("(?:[^"\\\r\n]|\\.)*"|[^#"\s]*)#([^\s]*)/;
// A label: what a robot, mesh or drawing renderer names a pick by.
const LABEL_SELECTOR_RE = /^[A-Za-z_][A-Za-z0-9_:]*$/;

// An element's name, in the engine's grammar: its kind (`f:`, `e:`, `v:`) and its derivation from
// the features that made it -- an atom (the n-th element of its kind a feature made,
// `dial.make_box1.6`, or a derivation folded to a feature and a digest, `dial.cut3~5d1e0c2f9a3b`)
// and a step per feature that made it out of another (`;M:dial.cut1` modified, `;Gf:` generated
// from a face, `;U2:`, `;L:`, `;D2` ...): `f:dial.make_box1.6;M:dial.cut1`. A feature the author
// labelled goes by the label (`f:lid.2`); an element no construction names (an imported file's) by
// its geometric token, 12 hex (`f:9d2e8c1b5a70`). A name is an opaque string the grammar admits:
// nothing here reads a derivation. Its cases are cadRefs.parity.json's `elementNameCases`, which
// cad/engine/kernel/trace.py's `ELEMENT_NAME` reads too.
//
// A feature is a label or `function.operationN`; segments start with a letter and numbers with a
// digit, so the two never read as one another, and a geometric token holds no dot.
const SEGMENT_SOURCE = "[A-Za-z_][A-Za-z0-9_]*";
const NUMBER_SOURCE = "[1-9][0-9]*";
const HEX12_SOURCE = "[0-9a-f]{12}";
const FEATURE_NAME_SOURCE = `${SEGMENT_SOURCE}(?:\\.${SEGMENT_SOURCE})?`;
const ATOM_SOURCE = `${FEATURE_NAME_SOURCE}(?:\\.${NUMBER_SOURCE}|~${HEX12_SOURCE})`;
const STEP_SOURCE =
  `;(?:(?:(?:M|MG[fev]|G[fev]|U)(?:${NUMBER_SOURCE})?|L):${FEATURE_NAME_SOURCE}(?:\\+[fev]:${ATOM_SOURCE})*` +
  `|D${NUMBER_SOURCE})`;
const ELEMENT_NAME_SOURCE = `[fev]:(?:${HEX12_SOURCE}|${ATOM_SOURCE}(?:${STEP_SOURCE})*)`;
const ELEMENT_SELECTOR_RE = new RegExp(`^(${ELEMENT_NAME_SOURCE})$`);

// An occurrence token (`o:` + 12 hex), as an older GLB names the nodes it places.
const OCCURRENCE_TOKEN_RE = /^o:[0-9a-f]{12}$/;

/** Whether `value` is an occurrence token (`o:` + 12 hex): a GLB node's name for what it places. */
export function isOccurrenceToken(value) {
  return OCCURRENCE_TOKEN_RE.test(String(value || "").trim());
}

/**
 * Whether `selector` is a selector of a file the engine does not draw: a label (`upper_arm`, `h2F`,
 * `glb:3`), as its renderer names a pick.
 */
export function isLabelSelector(selector) {
  return typeof selector === "string" && LABEL_SELECTOR_RE.test(selector);
}

// A file's selectors as a token writes them: trimmed, once each, in order.
function labelSelectorList(selectors) {
  const list = [];
  for (const selector of selectors) {
    for (const each of String(selector ?? "").split(",").map(text => text.trim())) {
      if (each && !list.includes(each)) list.push(each);
    }
  }
  return list;
}

export function parseCadRefToken(copyText) {
  const engine = engineRefToken(copyText);
  if (engine !== undefined) {
    return engine;
  }
  const match = String(copyText || "").trim().match(CAD_TOKEN_RE);
  if (!match) {
    return null;
  }
  // The prefix is kept RAW: a resolver matches it as a segment-aligned suffix of the document's
  // own path, so normalizing it (dropping its extension, say) breaks that.
  let cadPath = String(match[1] || "").trim();
  if (cadPath.startsWith('"')) {
    try { cadPath = JSON.parse(cadPath); } catch { return null; }
  }
  return {
    token: match[0],
    cadPath,
    selectors: labelSelectorList([match[2] || ""])
  };
}

export function buildCadRefToken({ cadPath = "", selector = "", selectors } = {}) {
  const prefix = String(cadPath || "").trim();
  const given = selectors !== undefined ? selectors : selector ? [selector] : [];
  // An engine document's selectors keep their order (`select` answers one shape per selector, in
  // order), and a comma inside a quoted label never splits one.
  const selectorList = isEngineRefFile(prefix) ? engineSelectorList(given) : labelSelectorList(given);
  // `<prefix>#` with no selectors is meaningful -- it names a whole file.
  const encodedPrefix = /[\s#"\\]/.test(prefix) ? JSON.stringify(prefix) : prefix;
  return `${encodedPrefix}#${selectorList.join(",")}`;
}

// ---- The engine's grammar -----------------------------------------------------------------------
//
// A document the engine draws (an `.xbf`, a STEP, a document by its id) is named as the engine names
// it, in the grammar `cadgen inspect` and `select` read: cad/engine/refs.py's `parse`, mirrored
// here case for case. The `refCases` of cadRefs.parity.json are asserted against both parsers, and
// its `spellingCases` against `spellEngineRefs` here and the resolution `cadgen inspect` runs there.
//   REF      = [FILE "#"] SELECTOR ("," SELECTOR)*     a bare ELEMENT after an owner is that owner's
//   SELECTOR = OWNER | [OWNER "/"] ELEMENT              no OWNER: the document's root
//   OWNER    = SEGMENT ("/" SEGMENT)*                   an occurrence's path, or its last segments
//   SEGMENT  = LABEL | LABEL "." N | "QUOTED" ["." N]   N: the N-th of the siblings so labelled
//   ELEMENT  = NAME | face N | edge N | vertex N        NAME: an element name (ELEMENT_NAME_SOURCE)
//
// `hand/finger.2/face 7` is face 7 of the second component labelled `finger` of `hand`; a label its
// siblings do not share needs no number, and one that names a single occurrence in the document
// needs no path (`palm/f:palm.body.3`). A label holding `/`, `,` or a quote, or one a plain segment
// would misread, is JSON-quoted (`"M3/M4 screw"`). A space is part of a label and of an element
// (`face 7`), so a copied ref runs to the end of its line. Whitespace is Python's, as the engine
// strips it.
const PY_SPACE = "\\t\\n\\v\\f\\r\\x1c-\\x1f \\x85\\xa0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000";
const PY_STRIP_RE = new RegExp(`^[${PY_SPACE}]+|[${PY_SPACE}]+$`, "g");
const ENGINE_ORDINAL_RE = new RegExp(`^(face|edge|vertex)[${PY_SPACE}]*([1-9][0-9]*)$`);
const ENGINE_INDEXED_RE = /^([\s\S]+)\.([1-9][0-9]*)$/;
const ENGINE_NUMBER_RE = /\.([1-9][0-9]*)/y;
const ENGINE_REF_FILE_RE = /\.(?:xbf|step|stp)$/i;

const pyStrip = text => text.replace(PY_STRIP_RE, "");
const isBlank = character => character === " " || character === "\t";

const DOCUMENT_ID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

/**
 * Whether `value` is a document's id (`cad.engine.ids`): a lower-case canonical UUID, as the
 * engine prints it -- a model's, or a file's. A ref's FILE may be one.
 */
export function isDocumentId(value) {
  return typeof value === "string" && DOCUMENT_ID_RE.test(value);
}

/**
 * Whether a file's refs are the engine's grammar: every document the engine draws -- an `.xbf`, its
 * own document; a STEP (`.step`, `.stp`), which it reads and serves as one; a document it holds by its
 * id (a model's).
 */
export function isEngineRefFile(path) {
  const text = String(path || "").trim();
  return isDocumentId(text) || ENGINE_REF_FILE_RE.test(text);
}

// A JSON string starting at `at` (a quote), read as Python's `raw_decode` reads one: its value and
// where it ends; null where it does not close or is no JSON string.
function jsonStringAt(text, at) {
  for (let end = at + 1; end < text.length; end += 1) {
    if (text[end] === "\\") {
      end += 1;
    } else if (text[end] === '"') {
      try {
        return { value: JSON.parse(text.slice(at, end + 1)), end: end + 1 };
      } catch {
        return null;
      }
    }
  }
  return null;
}

// FILE: everything before the first `#` (JSON-quoted when it holds one, or a quote); none where the
// text before it holds a quote, which only a quoted label may.
function engineFile(text) {
  if (text.startsWith("#")) {
    return [null, text.slice(1)];
  }
  if (text.startsWith('"')) {
    const quoted = jsonStringAt(text, 0);
    if (quoted && text[quoted.end] === "#") {
      return [quoted.value, text.slice(quoted.end + 1)];
    }
  }
  const at = text.indexOf("#");
  if (at > 0 && !text.slice(0, at).includes('"')) {
    return [pyStrip(text.slice(0, at)), text.slice(at + 1)];
  }
  return [null, text];
}

// The selectors of `text`, each its segments: `,` and `/` separate them outside a quoted segment.
// Null where the engine refuses it: an empty segment, a quote that does not close or is followed by
// more than its number, a separator at the end.
function engineSegments(text) {
  const selectors = [];
  let segments = [];
  let at = 0;
  const size = text.length;
  for (;;) {
    while (at < size && isBlank(text[at])) at += 1;
    if (at < size && text[at] === '"') {
      const quoted = jsonStringAt(text, at);
      if (!quoted) return null;
      let { end } = quoted;
      let index = null;
      ENGINE_NUMBER_RE.lastIndex = end;
      const number = ENGINE_NUMBER_RE.exec(text);
      if (number) {
        index = Number(number[1]);
        end = ENGINE_NUMBER_RE.lastIndex;
      }
      while (end < size && isBlank(text[end])) end += 1;
      if (end < size && text[end] !== "/" && text[end] !== ",") return null;
      segments.push({ text: quoted.value, quoted: true, index });
      at = end;
    } else {
      let end = at;
      while (end < size && text[end] !== "/" && text[end] !== ",") end += 1;
      const piece = pyStrip(text.slice(at, end));
      if (!piece) return null;
      segments.push({ text: piece, quoted: false, index: null });
      at = end;
    }
    if (at >= size) {
      selectors.push(segments);
      return selectors;
    }
    if (text[at] === ",") {
      selectors.push(segments);
      segments = [];
    }
    at += 1;
    if (at >= size) return null;
  }
}

// A selector's segments as its owner and its element: the last segment, unquoted, where it is an
// ordinal (`face 7`) or an element name.
function engineSelector(segments) {
  const last = segments[segments.length - 1];
  let element = null;
  if (!last.quoted) {
    const ordinal = ENGINE_ORDINAL_RE.exec(last.text);
    if (ordinal) {
      element = { kind: ordinal[1], ordinal: Number(ordinal[2]) };
    } else if (ELEMENT_SELECTOR_RE.test(last.text)) {
      element = last.text;
    }
  }
  const owner = element === null ? segments : segments.slice(0, -1);
  return { owner: owner.length ? owner : null, element };
}

/**
 * A ref in the engine's grammar as the engine parses it (`refs.parse`): its document (`file`, null
 * where it names none) and its selectors, each `{ owner, element }` -- `owner` its segments
 * (`{ text, quoted, index }`), null for the document's root; `element` a name, `{ kind, ordinal }`,
 * or null for the owner itself. Null for a ref the engine refuses.
 *
 * @param {string} ref
 * @returns {{ file: string | null, selectors: { owner: { text: string, quoted: boolean, index: number | null }[] | null,
 *   element: string | { kind: string, ordinal: number } | null }[] } | null}
 */
export function parseEngineRef(ref) {
  if (typeof ref !== "string") return null;
  const text = pyStrip(ref);
  if (!text) return null;
  const [file, after] = engineFile(text);
  const rest = pyStrip(after);
  const split = rest ? engineSegments(rest) : null;
  if (!split) return null;
  const selectors = [];
  let owner = null;
  for (const segments of split) {
    let found = engineSelector(segments);
    if (found.owner === null && found.element !== null && owner !== null && selectors.length) {
      found = { owner, element: found.element };  // a bare element after an owner is that owner's
    }
    selectors.push(found);
    owner = found.owner;
  }
  return { file, selectors };
}

// A segment as a ref writes it: a quoted one JSON-quoted, its number after.
function engineSegmentText(segment) {
  if (!segment.quoted) return segment.text;
  return JSON.stringify(segment.text) + (segment.index === null || segment.index === undefined ? "" : `.${segment.index}`);
}

/** One selector of a parsed engine ref, as a ref writes it (`refs.Selector`'s text). */
export function engineSelectorText(selector) {
  const owner = (selector.owner || []).map(engineSegmentText).join("/");
  const { element } = selector;
  const named = element === null || element === undefined ? "" : typeof element === "string" ? element : `${element.kind} ${element.ordinal}`;
  return [owner, named].filter(Boolean).join("/");
}

/** Whether `selector` is one selector of the engine's grammar, as a reference holds one. */
export function isEngineSelector(selector) {
  if (typeof selector !== "string" || !selector || selector !== pyStrip(selector)) return false;
  return parseEngineRef(`#${selector}`)?.selectors.length === 1;
}

// An engine document's selectors as a token writes them: each as the engine reads it (an entry may
// hold several, a bare element taking the owner before it), once each, in order.
function engineSelectorList(selectors) {
  const list = [];
  for (const selector of selectors) {
    const text = String(selector ?? "");
    const parsed = parseEngineRef(`#${text}`);
    for (const each of parsed ? parsed.selectors.map(engineSelectorText) : [pyStrip(text)]) {
      if (each && !list.includes(each)) list.push(each);
    }
  }
  return list;
}

// A copied line naming an engine document (`<file>#<ref>`): the whole line is the ref, as the engine
// reads it, for a label may hold a space. Null for one the engine refuses; undefined for a line that
// names no engine document.
function engineRefToken(copyText) {
  const line = pyStrip(pyStrip(String(copyText || "")).split(/\r\n|\r|\n/, 1)[0]);
  const [file] = engineFile(line);
  if (file === null || !isEngineRefFile(file)) return undefined;
  const parsed = parseEngineRef(line);
  return parsed ? { token: line, cadPath: file, selectors: parsed.selectors.map(engineSelectorText) } : null;
}

// ---- Spelling a served engine document's refs ---------------------------------------------------

// The occurrences of one sibling group a segment names: a label read whole first, and as `LABEL.N`
// only where no sibling bears it whole (`refs._group`).
function engineGroup(nodes, segment) {
  if (segment.quoted) {
    const named = nodes.filter(node => node.label === segment.text);
    return segment.index === null ? named : named.slice(segment.index - 1, segment.index);
  }
  const exact = nodes.filter(node => node.label === segment.text);
  if (exact.length) return exact;
  const numbered = ENGINE_INDEXED_RE.exec(segment.text);
  if (!numbered) return [];
  const index = Number(numbered[2]);
  return nodes.filter(node => node.label === numbered[1]).slice(index - 1, index);
}

// Whether a label reads back as itself, unquoted, as a segment that ends an owner (`refs._plain`).
function plainEngineLabel(label) {
  return Boolean(label) && label === pyStrip(label) && !/[/,"]/.test(label)
    && !ENGINE_ORDINAL_RE.test(label) && !ELEMENT_SELECTOR_RE.test(label);
}

// A canonical segment read back (`refs._as_segment`).
function engineSegmentOf(text) {
  if (!text.startsWith('"')) return { text, quoted: false, index: null };
  const quoted = jsonStringAt(text, 0);
  const number = /^\.([1-9][0-9]*)$/.exec(text.slice(quoted.end));
  return { text: quoted.value, quoted: true, index: number ? Number(number[1]) : null };
}

/**
 * The canonical refs of a served engine document's occurrences and elements, as `cadgen inspect`
 * answers them and `select` labels what it selects (`refs.owner_text`, `refs.path_text`): an
 * occurrence by its label where that names it alone in the document (`palm`), else by its path from
 * the root, each segment its label numbered among the siblings that share it (`hand/finger.2`); an
 * element by its name, else its kind and ordinal, under its part's -- under the document's name in a
 * document of one part. Each is worked out when first asked.
 *
 * @param {object | null} tree  The document's `structure.tree`: an assembly `{ name, children }`, a
 *   placed part `{ name, prototype, instance }`.
 * @returns {{ occurrence: (entry: object) => string, element: (entry: object, kind: string, ordinal: number, name?: string) => string }}
 *   Each takes an entry of `tree` ("" for one it does not hold); `element` the entry of a part.
 */
export function spellEngineRefs(tree) {
  const byEntry = new Map();
  const all = [];
  const visit = (entry, parent) => {
    const node = { label: String(entry?.name || ""), part: Boolean(entry) && Object.prototype.hasOwnProperty.call(entry, "prototype"),
      parent, children: [], segment: "" };
    byEntry.set(entry, node);
    all.push(node);
    node.children = (Array.isArray(entry?.children) ? entry.children : []).map(child => visit(child, node));
    return node;
  };
  const root = tree ? visit(tree, null) : null;
  const holders = all.filter(node => node.children.length);
  // Each node's segment: its label, numbered among the siblings that share it (`finger.2`),
  // JSON-quoted where that plain text would name another sibling or would not read back
  // (`refs._segments`). The plain text names the node alone unless a sibling bears `LABEL.N` whole
  // (a label read whole comes first): checked by label, so a wide assembly costs no more than its size.
  for (const group of root ? [[root], ...holders.map(node => node.children)] : []) {
    const counts = new Map();
    const seen = new Map();
    for (const node of group) counts.set(node.label, (counts.get(node.label) || 0) + 1);
    for (const node of group) {
      const n = (seen.get(node.label) || 0) + 1;
      seen.set(node.label, n);
      const shared = counts.get(node.label) > 1;
      const plain = plainEngineLabel(node.label) && !(shared && counts.has(`${node.label}.${n}`));
      node.segment = plain ? (shared ? `${node.label}.${n}` : node.label)
        : engineSegmentText({ text: node.label, quoted: true, index: shared ? n : null });
    }
  }
  const down = (start, segments) => segments.reduce((current, segment) => current.flatMap(node => engineGroup(node.children, segment)), start);
  // The occurrences an owner names: read from the root when its first segment names the root, else
  // those whose paths end with it (`refs.owners`).
  const owners = (segments) => {
    if (engineGroup([root], segments[0]).length) {
      const found = down([root], segments.slice(1));
      if (found.length) return found;
    }
    return holders.flatMap(node => down(engineGroup(node.children, segments[0]), segments.slice(1)));
  };
  const alone = (found, node) => found.length === 1 && found[0] === node;
  const paths = new Map();
  const pathText = (node) => {
    if (!paths.has(node)) {
      const steps = [];
      for (let step = node; step; step = step.parent) steps.unshift(step);
      let found = steps.map(step => step.segment).join("/");
      if (!root.label) {
        // An unlabelled root is left out where the rest names the occurrence alone.
        const tail = steps.slice(1);
        found = node === root ? "" : (alone(owners(tail.map(step => engineSegmentOf(step.segment))), node) ? tail : steps)
          .map(step => step.segment).join("/");
      }
      paths.set(node, found);
    }
    return paths.get(node);
  };
  const ownerTexts = new Map();
  const ownerText = (node) => {
    if (!ownerTexts.has(node)) {
      const segment = engineSegmentOf(node.segment);
      const unnumbered = segment.quoted ? segment.index === null : node.segment === node.label;
      ownerTexts.set(node, node === root ? (root.label ? node.segment : "")
        : unnumbered && alone(owners([segment]), node) ? node.segment : pathText(node));
    }
    return ownerTexts.get(node);
  };
  const onePart = all.filter(node => node.part).length === 1;
  return {
    occurrence: (entry) => {
      const node = byEntry.get(entry);
      return node ? ownerText(node) : "";
    },
    element: (entry, kind, ordinal, name = "") => {
      const node = byEntry.get(entry);
      if (!node) return "";
      const owner = ownerText(onePart ? root : node);
      const element = name || `${kind} ${ordinal}`;
      return owner ? `${owner}/${element}` : element;
    }
  };
}
