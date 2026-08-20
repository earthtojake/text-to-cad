// `<file>#<selectors>`, file half optional. Mirrors CAD_TOKEN_RE in cadgen/cad_ref_syntax.py;
// the tokenCases in cadRefs.parity.json are asserted by both languages. The prefix sits LEFT of
// the '#' so it can never collide with the selector grammar on the right.
const CAD_TOKEN_RE = /^\s*([^#\s]*)#([^\s]*)/;
const OCCURRENCE_SELECTOR_RE = /^o((?:\d+)(?:\.\d+)*)$/;
const OCCURRENCE_ENTITY_SELECTOR_RE = /^o((?:\d+)(?:\.\d+)*)\.([sfev])(\d+)$/;
const ENTITY_SELECTOR_RE = /^([sfev])(\d+)$/;
const MATE_SELECTOR_RE = /^m\d+$/i;

// Mirrors LABEL_PATTERN in cadgen/cad_ref_syntax.py. Kept in step by cadRefs.parity.json,
// which both this module's tests and the Python tests assert against.
const LABEL_SOURCE = "[A-Za-z_][A-Za-z0-9_:]*";
const LABEL_SELECTOR_RE = new RegExp(`^(${LABEL_SOURCE})$`);
const LABEL_ENTITY_SELECTOR_RE = new RegExp(`^(${LABEL_SOURCE})\\.([sfev])(\\d+)$`);

// The union of every selector form the viewer treats as a real CAD selector rather than an
// opaque string. It lives here, beside the grammar it mirrors, because it was previously
// copy-pasted into two viewer modules that had no test keeping them in step.
const NATIVE_CAD_SELECTOR_RE = /^(?:o\d+(?:\.\d+)*(?:\.[sfev]\d+)?|[sfev]\d+|m\d+)$/i;

export function isNativeCadSelector(candidate) {
  return NATIVE_CAD_SELECTOR_RE.test(String(candidate || "").trim());
}

function selectorTypeForKind(kind) {
  if (kind === "s") {
    return "shape";
  }
  if (kind === "f") {
    return "face";
  }
  if (kind === "e") {
    return "edge";
  }
  return "vertex";
}

export function normalizeCadPath(rawCadPath) {
  let normalized = String(rawCadPath || "").replace(/\\/g, "/").trim().replace(/^\/+|\/+$/g, "");
  if (!normalized) {
    return "";
  }
  if (normalized.split("/").some((part) => !part || part === "." || part === "..")) {
    return "";
  }
  return normalized;
}

function parseStructuredSelector(rawSelector, { inheritedOccurrenceId = "", inheritedLabel = "" } = {}) {
  const selector = String(rawSelector || "").trim().replace(/^#/, "");
  if (!selector) {
    return null;
  }

  const occurrenceEntityMatch = selector.match(OCCURRENCE_ENTITY_SELECTOR_RE);
  if (occurrenceEntityMatch) {
    const occurrenceId = `o${occurrenceEntityMatch[1]}`;
    const kind = occurrenceEntityMatch[2];
    const ordinal = Number(occurrenceEntityMatch[3]);
    return {
      selectorType: selectorTypeForKind(kind),
      occurrenceId,
      ordinal,
      kind,
      canonical: `${occurrenceId}.${kind}${ordinal}`
    };
  }

  const occurrenceMatch = selector.match(OCCURRENCE_SELECTOR_RE);
  if (occurrenceMatch) {
    return {
      selectorType: "occurrence",
      occurrenceId: `o${occurrenceMatch[1]}`,
      ordinal: null,
      kind: "",
      canonical: `o${occurrenceMatch[1]}`
    };
  }

  const entityMatch = selector.match(ENTITY_SELECTOR_RE);
  if (entityMatch) {
    const kind = entityMatch[1];
    const ordinal = Number(entityMatch[2]);
    if (inheritedOccurrenceId) {
      return {
        selectorType: selectorTypeForKind(kind),
        occurrenceId: inheritedOccurrenceId,
        ordinal,
        kind,
        canonical: `${inheritedOccurrenceId}.${kind}${ordinal}`
      };
    }
    // An inherited label carries forward exactly like an inherited occurrence id.
    if (inheritedLabel) {
      return {
        selectorType: selectorTypeForKind(kind),
        occurrenceId: "",
        ordinal,
        kind,
        label: inheritedLabel,
        canonical: `${inheritedLabel}.${kind}${ordinal}`
      };
    }
    return {
      selectorType: selectorTypeForKind(kind),
      occurrenceId: "",
      ordinal,
      kind,
      canonical: `${kind}${ordinal}`
    };
  }

  // Label forms are tried only after every numeric form, so an existing ref can never change
  // meaning. Mates look like labels and are excluded explicitly.
  if (!MATE_SELECTOR_RE.test(selector)) {
    const labelEntityMatch = selector.match(LABEL_ENTITY_SELECTOR_RE);
    if (labelEntityMatch) {
      const label = labelEntityMatch[1];
      const kind = labelEntityMatch[2];
      const ordinal = Number(labelEntityMatch[3]);
      return {
        selectorType: selectorTypeForKind(kind),
        occurrenceId: "",
        ordinal,
        kind,
        label,
        canonical: `${label}.${kind}${ordinal}`
      };
    }

    const labelMatch = selector.match(LABEL_SELECTOR_RE);
    if (labelMatch) {
      const label = labelMatch[1];
      return {
        selectorType: "label",
        occurrenceId: "",
        ordinal: null,
        kind: "",
        label,
        canonical: label
      };
    }
  }

  return {
    selectorType: "opaque",
    occurrenceId: "",
    ordinal: null,
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
    // Whichever naming scheme was used becomes the context for following bare entities,
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
    shape: 2,
    face: 3,
    edge: 4,
    vertex: 5,
    opaque: 6
  };
  return uniqueSelectors
    .map((selector, index) => ({ selector, index, parsed: parseStructuredSelector(selector) }))
    .sort((left, right) => {
      const leftOccurrence = left.parsed?.occurrenceId || "";
      const rightOccurrence = right.parsed?.occurrenceId || "";
      if (leftOccurrence !== rightOccurrence) {
        return leftOccurrence.localeCompare(rightOccurrence);
      }
      const leftRank = rank[left.parsed?.selectorType] ?? 99;
      const rightRank = rank[right.parsed?.selectorType] ?? 99;
      if (leftRank !== rightRank) {
        return leftRank - rightRank;
      }
      const leftOrdinal = Number(left.parsed?.ordinal || 0);
      const rightOrdinal = Number(right.parsed?.ordinal || 0);
      if (leftOrdinal !== rightOrdinal) {
        return leftOrdinal - rightOrdinal;
      }
      if (left.selector !== right.selector) {
        return left.selector.localeCompare(right.selector);
      }
      return left.index - right.index;
    })
    .map((item) => item.selector);
}

function occurrenceSortKey(occurrenceId) {
  const body = String(occurrenceId || "").replace(/^o/i, "");
  const parts = [];
  for (const chunk of body.split(".")) {
    const value = Number(chunk);
    if (!Number.isInteger(value)) {
      return [1 << 30];
    }
    parts.push(value);
  }
  return parts;
}

function compareOccurrenceIds(left, right) {
  const a = occurrenceSortKey(left);
  const b = occurrenceSortKey(right);
  for (let index = 0; index < Math.max(a.length, b.length); index += 1) {
    const diff = (a[index] ?? -1) - (b[index] ?? -1);
    if (diff !== 0) {
      return diff;
    }
  }
  return 0;
}

function labelCandidate(name) {
  const text = String(name || "").trim();
  if (!text) {
    return "";
  }
  const parsed = parseStructuredSelector(text);
  // parseStructuredSelector claims numeric forms first, so names like "f12", "o1" or "m2"
  // come back as something other than a label and must not be aliased.
  return parsed && parsed.selectorType === "label" && parsed.label === text ? text : "";
}

/**
 * Map label aliases to occurrence ids. Mirrors cadgen.label_refs.build_label_aliases; the
 * aliasCases in cadRefs.parity.json are asserted by both implementations.
 *
 * Duplicated labels are legitimate (two wheels, one rim label), so each gets a numbered alias
 * in occurrence-tree order and the bare shared label resolves to nothing.
 */
export function buildLabelAliasMap(rows) {
  const ordered = [];
  for (const row of Array.isArray(rows) ? rows : []) {
    const occurrenceId = String(row?.id || row?.occurrenceId || "").trim();
    if (!occurrenceId) {
      continue;
    }
    const candidate = labelCandidate(row?.name);
    if (candidate) {
      ordered.push({ occurrenceId, candidate });
    }
  }
  ordered.sort((left, right) => compareOccurrenceIds(left.occurrenceId, right.occurrenceId));

  const grouped = new Map();
  for (const { occurrenceId, candidate } of ordered) {
    if (!grouped.has(candidate)) {
      grouped.set(candidate, []);
    }
    grouped.get(candidate).push(occurrenceId);
  }

  const authored = new Set(grouped.keys());
  const aliases = {};
  const ambiguous = {};

  for (const [candidate, occurrenceIds] of grouped) {
    if (occurrenceIds.length === 1) {
      aliases[candidate] = occurrenceIds[0];
      continue;
    }
    const numbered = [];
    let nextIndex = 1;
    for (const occurrenceId of occurrenceIds) {
      let alias = "";
      for (;;) {
        alias = `${candidate}_${nextIndex}`;
        nextIndex += 1;
        if (!authored.has(alias) && !(alias in aliases)) {
          break;
        }
      }
      aliases[alias] = occurrenceId;
      numbered.push(alias);
    }
    ambiguous[candidate] = numbered;
  }

  return { aliases, ambiguous };
}

/** The `#alias` to paste for an occurrence, or "" when it has none. */
export function labelRefForOccurrence(aliasMap, occurrenceId) {
  const aliases = aliasMap?.aliases || {};
  const target = String(occurrenceId || "").trim();
  for (const [alias, mapped] of Object.entries(aliases)) {
    if (mapped === target) {
      return `#${alias}`;
    }
  }
  return "";
}

/**
 * Resolve a label selector to its numeric equivalent. Returns "" when the label is unknown or
 * ambiguous -- callers treat that the same way they treat any selector they cannot use.
 */
export function resolveLabelSelector(selector, aliasMap) {
  const parsed = parseStructuredSelector(selector);
  if (!parsed || !parsed.label) {
    return String(selector || "").trim();
  }
  const occurrenceId = aliasMap?.aliases?.[parsed.label] || "";
  if (!occurrenceId) {
    return "";
  }
  if (parsed.selectorType === "label") {
    return occurrenceId;
  }
  return `${occurrenceId}.${parsed.kind}${parsed.ordinal}`;
}

export function parseCadRefToken(copyText) {
  const match = String(copyText || "").trim().match(CAD_TOKEN_RE);
  if (!match) {
    return null;
  }
  // The prefix is kept RAW: the agent that resolves it back to a file does a literal suffix
  // match against project paths, so normalizing (which would strip `.step.py`) breaks it.
  const cadPath = String(match[1] || "").trim();
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
  return `${prefix}#${selectorList.join(",")}`;
}
