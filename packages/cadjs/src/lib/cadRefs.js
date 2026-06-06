const CAD_TOKEN_RE = /^\s*#([^\s]*)/;
const OCCURRENCE_SELECTOR_RE = /^o((?:\d+)(?:\.\d+)*)$/;
const OCCURRENCE_ENTITY_SELECTOR_RE = /^o((?:\d+)(?:\.\d+)*)\.([sfev])(\d+)$/;
const ENTITY_SELECTOR_RE = /^([sfev])(\d+)$/;

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

function parseStructuredSelector(rawSelector, { inheritedOccurrenceId = "" } = {}) {
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
    return {
      selectorType: selectorTypeForKind(kind),
      occurrenceId: "",
      ordinal,
      kind,
      canonical: `${kind}${ordinal}`
    };
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

  for (const rawSelector of rawSelectors) {
    const parsedSelector = parseStructuredSelector(rawSelector, { inheritedOccurrenceId });
    if (!parsedSelector) {
      continue;
    }
    normalizedSelectors.push(parsedSelector.canonical);
    if (parsedSelector.occurrenceId) {
      inheritedOccurrenceId = parsedSelector.occurrenceId;
    }
  }

  return normalizedSelectors;
}

export function sortCadRefSelectors(selectors) {
  const normalizedSelectors = normalizeCadRefSelectors(selectors);
  const uniqueSelectors = [...new Set(normalizedSelectors.filter(Boolean))];
  const rank = {
    occurrence: 1,
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

export function parseCadRefToken(copyText) {
  const match = String(copyText || "").trim().match(CAD_TOKEN_RE);
  if (!match) {
    return null;
  }
  const selectorText = String(match[1] || "").trim();
  return {
    token: match[0],
    cadPath: "",
    selectors: normalizeCadRefSelectors(selectorText)
  };
}

export function buildCadRefToken({ cadPath = "", selector = "", selectors } = {}) {
  void cadPath;
  const selectorList = selectors !== undefined ? sortCadRefSelectors(selectors) : sortCadRefSelectors(selector ? [selector] : []);
  if (!selectorList.length) {
    return "#";
  }
  return `#${selectorList.join(",")}`;
}
