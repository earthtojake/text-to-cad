// Two ref grammars. An engine document's (`.xbf`) is the engine's own, at the end of this module
// ("The engine's grammar"). A STEP's is the one described here, until the engine's carries over.
//
// A STEP's ref grammar, which the CAD Viewer copies for a STEP whichever renderer draws it. A ref names an
// occurrence by its token (`o:` + 12 hex, minted from its place in the tree) and an element by the
// occurrence's token, a slash and the element's name: its kind (`f:`, `e:`, `v:`) and its
// derivation from the features that made it -- an atom (the n-th element of its kind a feature
// made, `dial.make_box1.6`, or a derivation folded to a feature and a digest,
// `dial.cut3~5d1e0c2f9a3b`) and a step per feature that made it out of another (`;M:dial.cut1`
// modified, `;Gf:` generated from a face, `;U2:`, `;L:`, `;D2` ...):
// `#o:4b1f9e2a7c03/f:dial.make_box1.6;M:dial.cut1`. A feature the author labelled goes by the label
// (`f:lid.2`). An element no construction names (an imported file's) is named by its geometric
// token, 12 hex (`f:9d2e8c1b5a70`). A part label stands in for an occurrence token (`#base`,
// `#base/f:dial.make_box1.6`); a bare element name resolves in a document with one leaf. A name is
// an opaque string this grammar admits: nothing here reads a derivation. Its cases are
// cadRefs.parity.json's `selectorCases`, `inheritanceCases` and `tokenCases`.
//
// `<file>#<selectors>`, file half optional.
// The prefix sits LEFT of the '#' so it can never collide with the selector grammar on the right.
// JSON-quote paths containing whitespace or delimiters: `"my part.step"#o:4b1f9e2a7c03`.
const CAD_TOKEN_RE = /^\s*("(?:[^"\\\r\n]|\\.)*"|[^#"\s]*)#([^\s]*)/;
const OCCURRENCE_TOKEN_SOURCE = "o:[0-9a-f]{12}";
// A feature is a label or `function.operationN`; segments start with a
// letter and numbers with a digit, so the two never read as one another, and a geometric token
// holds no dot.
const SEGMENT_SOURCE = "[A-Za-z_][A-Za-z0-9_]*";
const NUMBER_SOURCE = "[1-9][0-9]*";
const HEX12_SOURCE = "[0-9a-f]{12}";
const FEATURE_NAME_SOURCE = `${SEGMENT_SOURCE}(?:\\.${SEGMENT_SOURCE})?`;
const ATOM_SOURCE = `${FEATURE_NAME_SOURCE}(?:\\.${NUMBER_SOURCE}|~${HEX12_SOURCE})`;
const STEP_SOURCE =
  `;(?:(?:(?:M|MG[fev]|G[fev]|U)(?:${NUMBER_SOURCE})?|L):${FEATURE_NAME_SOURCE}(?:\\+[fev]:${ATOM_SOURCE})*` +
  `|D${NUMBER_SOURCE})`;
const ELEMENT_NAME_SOURCE = `[fev]:(?:${HEX12_SOURCE}|${ATOM_SOURCE}(?:${STEP_SOURCE})*)`;
const OCCURRENCE_SELECTOR_RE = new RegExp(`^(${OCCURRENCE_TOKEN_SOURCE})$`);
const OCCURRENCE_ELEMENT_SELECTOR_RE = new RegExp(`^(${OCCURRENCE_TOKEN_SOURCE})/(${ELEMENT_NAME_SOURCE})$`);
const ELEMENT_SELECTOR_RE = new RegExp(`^(${ELEMENT_NAME_SOURCE})$`);
const MATE_SELECTOR_RE = /^m\d+$/i;

// A part label.
const LABEL_SOURCE = "[A-Za-z_][A-Za-z0-9_:]*";
const LABEL_SELECTOR_RE = new RegExp(`^(${LABEL_SOURCE})$`);
const LABEL_ELEMENT_SELECTOR_RE = new RegExp(`^(${LABEL_SOURCE})/(${ELEMENT_NAME_SOURCE})$`);
const OCCURRENCE_TOKEN_RE = new RegExp(`^${OCCURRENCE_TOKEN_SOURCE}$`);

/**
 * Whether `candidate` is a ref in the grammar itself -- an occurrence token, an occurrence/element
 * pair, a bare element name or a mate -- rather than a label or an opaque string.
 */
export function isNativeCadSelector(candidate) {
  const parsed = parseStructuredSelector(candidate);
  if (!parsed || parsed.label) {
    return false;
  }
  return parsed.selectorType !== "opaque" || MATE_SELECTOR_RE.test(parsed.canonical);
}

/** Whether `value` is an occurrence token (`o:` + 12 hex). */
export function isOccurrenceToken(value) {
  return OCCURRENCE_TOKEN_RE.test(String(value || "").trim());
}

/** Whether `value` is an element name (`f:`, `e:` or `v:` and its lineage or geometric token). */
export function isElementName(value) {
  return ELEMENT_SELECTOR_RE.test(String(value || "").trim());
}

function selectorTypeForKind(kind) {
  if (kind === "f") {
    return "face";
  }
  if (kind === "e") {
    return "edge";
  }
  return "vertex";
}

/** The one composition rule: `<occurrence token>/<element name>`. */
export function elementRef(occurrenceId, element) {
  return `${occurrenceId}/${element}`;
}

/** `{ owner, element }` of an element ref (`o:…/f:…`, `label/f:…`), or null for anything else. */
export function splitElementRef(selector) {
  const text = String(selector || "").trim().replace(/^#/, "");
  const slash = text.indexOf("/");
  if (slash <= 0) {
    return null;
  }
  const owner = text.slice(0, slash);
  const element = text.slice(slash + 1);
  return isElementName(element) ? { owner, element } : null;
}

function parseStructuredSelector(rawSelector, { inheritedOccurrenceId = "", inheritedLabel = "" } = {}) {
  const selector = String(rawSelector || "").trim().replace(/^#/, "");
  if (!selector) {
    return null;
  }

  const occurrenceElementMatch = selector.match(OCCURRENCE_ELEMENT_SELECTOR_RE);
  if (occurrenceElementMatch) {
    const occurrenceId = occurrenceElementMatch[1];
    const element = occurrenceElementMatch[2];
    return {
      selectorType: selectorTypeForKind(element[0]),
      occurrenceId,
      element,
      kind: element[0],
      canonical: elementRef(occurrenceId, element)
    };
  }

  const occurrenceMatch = selector.match(OCCURRENCE_SELECTOR_RE);
  if (occurrenceMatch) {
    return {
      selectorType: "occurrence",
      occurrenceId: occurrenceMatch[1],
      element: "",
      kind: "",
      canonical: occurrenceMatch[1]
    };
  }

  const elementMatch = selector.match(ELEMENT_SELECTOR_RE);
  if (elementMatch) {
    const element = elementMatch[1];
    const kind = element[0];
    if (inheritedOccurrenceId) {
      return {
        selectorType: selectorTypeForKind(kind),
        occurrenceId: inheritedOccurrenceId,
        element,
        kind,
        canonical: elementRef(inheritedOccurrenceId, element)
      };
    }
    // An inherited label carries forward exactly like an inherited occurrence token.
    if (inheritedLabel) {
      return {
        selectorType: selectorTypeForKind(kind),
        occurrenceId: "",
        element,
        kind,
        label: inheritedLabel,
        canonical: elementRef(inheritedLabel, element)
      };
    }
    return {
      selectorType: selectorTypeForKind(kind),
      occurrenceId: "",
      element,
      kind,
      canonical: element
    };
  }

  // Label forms are tried only after every token and name form, so neither is read as a label.
  // Mates look like labels and are excluded explicitly.
  if (!MATE_SELECTOR_RE.test(selector)) {
    const labelElementMatch = selector.match(LABEL_ELEMENT_SELECTOR_RE);
    if (labelElementMatch) {
      const label = labelElementMatch[1];
      const element = labelElementMatch[2];
      return {
        selectorType: selectorTypeForKind(element[0]),
        occurrenceId: "",
        element,
        kind: element[0],
        label,
        canonical: elementRef(label, element)
      };
    }

    const labelMatch = selector.match(LABEL_SELECTOR_RE);
    if (labelMatch) {
      const label = labelMatch[1];
      return {
        selectorType: "label",
        occurrenceId: "",
        element: "",
        kind: "",
        label,
        canonical: label
      };
    }
  }

  return {
    selectorType: "opaque",
    occurrenceId: "",
    element: "",
    kind: "",
    canonical: selector
  };
}

export function parseCadRefSelector(rawSelector, options = {}) {
  return parseStructuredSelector(rawSelector, options);
}

export function normalizeCadRefSelectors(selectors) {
  const rawSelectors = Array.isArray(selectors)
    ? selectors.flatMap((selector) => String(selector || "").split(","))
    : String(selectors || "").split(",");
  const normalizedSelectors = [];
  let inheritedOccurrenceId = "";
  let inheritedLabel = "";

  for (const rawSelector of rawSelectors) {
    const parsedSelector = parseStructuredSelector(rawSelector, { inheritedOccurrenceId, inheritedLabel });
    if (!parsedSelector) {
      continue;
    }
    normalizedSelectors.push(parsedSelector.canonical);
    // Whichever naming scheme was used becomes the context for following bare elements,
    // and clears the other one.
    if (parsedSelector.occurrenceId) {
      inheritedOccurrenceId = parsedSelector.occurrenceId;
      inheritedLabel = "";
    } else if (parsedSelector.label) {
      inheritedLabel = parsedSelector.label;
      inheritedOccurrenceId = "";
    }
  }

  return normalizedSelectors;
}

export function sortCadRefSelectors(selectors) {
  const normalizedSelectors = normalizeCadRefSelectors(selectors);
  const uniqueSelectors = [...new Set(normalizedSelectors.filter(Boolean))];
  const rank = {
    occurrence: 1,
    label: 1,
    face: 3,
    edge: 4,
    vertex: 5,
    opaque: 6
  };
  return uniqueSelectors
    .map((selector, index) => ({ selector, index, parsed: parseStructuredSelector(selector) }))
    .sort((left, right) => {
      const leftOccurrence = left.parsed?.occurrenceId || left.parsed?.label || "";
      const rightOccurrence = right.parsed?.occurrenceId || right.parsed?.label || "";
      if (leftOccurrence !== rightOccurrence) {
        return leftOccurrence.localeCompare(rightOccurrence);
      }
      const leftRank = rank[left.parsed?.selectorType] ?? 99;
      const rightRank = rank[right.parsed?.selectorType] ?? 99;
      if (leftRank !== rightRank) {
        return leftRank - rightRank;
      }
      if (left.selector !== right.selector) {
        return left.selector.localeCompare(right.selector);
      }
      return left.index - right.index;
    })
    .map((item) => item.selector);
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
  const selectorText = String(match[2] || "").trim();
  return {
    token: match[0],
    cadPath,
    selectors: normalizeCadRefSelectors(selectorText)
  };
}

export function buildCadRefToken({ cadPath = "", selector = "", selectors } = {}) {
  const prefix = String(cadPath || "").trim();
  const given = selectors !== undefined ? selectors : selector ? [selector] : [];
  // An engine document's selectors keep their order (`select` answers one shape per selector, in
  // order), and a comma inside a quoted label never splits one.
  const selectorList = isEngineRefFile(prefix) ? engineSelectorList(given) : sortCadRefSelectors(given);
  // `<prefix>#` with no selectors is meaningful -- it names a whole file.
  const encodedPrefix = /[\s#"\\]/.test(prefix) ? JSON.stringify(prefix) : prefix;
  return `${encodedPrefix}#${selectorList.join(",")}`;
}

// ---- The engine's grammar -----------------------------------------------------------------------
//
// An engine document (`.xbf`) is named as the engine names it, in the grammar `cadgen inspect` and
// `select` read: cadgen/engine/refs.py's `parse`, mirrored here case for case. The `refCases` of
// cadRefs.parity.json are asserted against both parsers, and its `spellingCases` against
// `spellEngineRefs` here and the resolution `cadgen inspect` runs there.
//
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
const ENGINE_REF_FILE_RE = /\.xbf$/i;

const pyStrip = text => text.replace(PY_STRIP_RE, "");
const isBlank = character => character === " " || character === "\t";

const DOCUMENT_ID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

/**
 * Whether `value` is a document's id (`cadgen.engine.ids`): a lower-case canonical UUID, as the
 * engine prints it -- a model's, or a file's. A ref's FILE may be one.
 */
export function isDocumentId(value) {
  return typeof value === "string" && DOCUMENT_ID_RE.test(value);
}

/**
 * Whether a file's refs are the engine's grammar: an `.xbf`, the engine's own document, or a document
 * the engine holds by its id (a model's). A STEP keeps its own grammar (above), whichever renderer
 * draws it.
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
