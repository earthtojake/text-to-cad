import { parseCadRefSelector, parseCadRefToken } from "cadgen-js/lib/cadRefs.js";

function featureSelectors(definition) {
  return (Array.isArray(definition?.features) ? definition.features : [])
    .flatMap((feature) => parseCadRefToken(feature?.ref)?.selectors || []);
}

// Occurrence and label targets resolve from display parts. Shape, face, edge,
// vertex and opaque selector targets need the complete selector runtime.
export function stepModuleRequiresTopology(definition) {
  return featureSelectors(definition).some((selector) => {
    const parsed = parseCadRefSelector(selector);
    return !["occurrence", "label"].includes(parsed?.selectorType || "opaque");
  });
}

// An assembly can load just the component occurrences a module addresses.
// Bare entity selectors have no occurrence scope, so the caller retains its
// existing whole-part behavior for those.
export function stepModuleTopologyOccurrenceIds(definition) {
  return [...new Set(featureSelectors(definition)
    .map((selector) => parseCadRefSelector(selector))
    .filter((parsed) => parsed && !["occurrence", "label"].includes(parsed.selectorType))
    .map((parsed) => String(parsed.occurrenceId || "").trim())
    .filter(Boolean))];
}
