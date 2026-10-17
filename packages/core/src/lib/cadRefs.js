// The ref grammar: one language, shared with cadgen (cadgen/cad_ref_syntax.py). A ref names an
// occurrence by its token (`o:` + 12 hex, minted from its place in the tree) and an element by the
// occurrence's token, a slash and the element's name: its kind (`f:`, `e:`, `v:`) and its lineage,
// the feature that made it and its number among what that feature made --
// `#o:4b1f9e2a7c03/f:dial.extrude1.3`. A piece of an element a later feature split takes its
// number among the pieces after a further dot (`f:dial.extrude1.3.2`), and a feature the author
// labelled goes by the label (`f:lid.2`). An element no construction names (an imported file's) is
// named by its geometric token, 12 hex (`f:9d2e8c1b5a70`). A part label stands in for an occurrence
// token (`#base`, `#base/f:dial.extrude1.3`); a bare element name resolves in a document with one
// leaf. The cases of cadRefs.parity.json are asserted by both languages.
//
// `<file>#<selectors>`, file half optional. Mirrors QUOTED_PREFIX_RE in cadgen/cad_ref_syntax.py.
// The prefix sits LEFT of the '#' so it can never collide with the selector grammar on the right.
// JSON-quote paths containing whitespace or delimiters: `"my part.step"#o:4b1f9e2a7c03`.
const CAD_TOKEN_RE = /^\s*("(?:[^"\\\r\n]|\\.)*"|[^#"\s]*)#([^\s]*)/;
const OCCURRENCE_TOKEN_SOURCE = "o:[0-9a-f]{12}";
// Mirrors FEATURE_NAME_PATTERN and ELEMENT_NAME_PATTERN in cadgen/cad_ref_syntax.py: a feature is
// a label or `function.operationN`; segments start with a letter and numbers with a digit, so the
// two never read as one another, and a geometric token holds no dot.
const SEGMENT_SOURCE = "[A-Za-z_][A-Za-z0-9_]*";
const NUMBER_SOURCE = "[1-9][0-9]*";
const FEATURE_NAME_SOURCE = `${SEGMENT_SOURCE}(?:\\.${SEGMENT_SOURCE})?`;
const ELEMENT_NAME_SOURCE = `[fev]:(?:[0-9a-f]{12}|${FEATURE_NAME_SOURCE}\\.${NUMBER_SOURCE}(?:\\.${NUMBER_SOURCE})?)`;
const OCCURRENCE_SELECTOR_RE = new RegExp(`^(${OCCURRENCE_TOKEN_SOURCE})$`);
const OCCURRENCE_ELEMENT_SELECTOR_RE = new RegExp(`^(${OCCURRENCE_TOKEN_SOURCE})/(${ELEMENT_NAME_SOURCE})$`);
const ELEMENT_SELECTOR_RE = new RegExp(`^(${ELEMENT_NAME_SOURCE})$`);
const MATE_SELECTOR_RE = /^m\d+$/i;

// Mirrors LABEL_PATTERN in cadgen/cad_ref_syntax.py. Kept in step by cadRefs.parity.json,
// which both this module's tests and the Python tests assert against.
const LABEL_SOURCE = "[A-Za-z_][A-Za-z0-9_:]*";
const LABEL_SELECTOR_RE = new RegExp(`^(${LABEL_SOURCE})$`);
const LABEL_ELEMENT_SELECTOR_RE = new RegExp(`^(${LABEL_SOURCE})/(${ELEMENT_NAME_SOURCE})$`);
const OCCURRENCE_TOKEN_RE = new RegExp(`^${OCCURRENCE_TOKEN_SOURCE}$`);

/**
 * Whether `candidate` is a ref in the grammar itself -- an occurrence token, an occurrence/element
 * pair, a bare element name or a mate -- rather than a label or an opaque string. Mirrors
 * `is_native_selector` in cadgen/cad_ref_syntax.py.
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
  const selectorList = selectors !== undefined ? sortCadRefSelectors(selectors) : sortCadRefSelectors(selector ? [selector] : []);
  // `<prefix>#` with no selectors is meaningful -- it names a whole file.
  const encodedPrefix = /[\s#"\\]/.test(prefix) ? JSON.stringify(prefix) : prefix;
  return `${encodedPrefix}#${selectorList.join(",")}`;
}
