// One comparable form of a JSON value: its keys sorted at every depth, so equal data is one string
// whichever JSON spelled it. A rebuild's articulation is compared by it, a preview's finishes too,
// and a routine's keyframes are keyed by its digest.
const canonical = value => (Array.isArray(value) ? value.map(canonical)
  : value && typeof value === "object" ? Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])]))
    : value);

export function canonicalJson(value) {
  return JSON.stringify(canonical(value));
}

// FNV-1a over the canonical form, twice with distinct offsets: sixteen hex digits, short enough to
// hold in state and compare per render, and distinct for any two routines a model would ship.
const FNV_PRIME = 0x01000193;
export function jsonDigest(value) {
  const text = canonicalJson(value);
  let low = 0x811c9dc5;
  let high = 0xcbf29ce4;
  for (let index = 0; index < text.length; index += 1) {
    const code = text.charCodeAt(index);
    low = Math.imul(low ^ code, FNV_PRIME);
    high = Math.imul(high ^ (code + 1), FNV_PRIME);
  }
  return `${(low >>> 0).toString(16).padStart(8, "0")}${(high >>> 0).toString(16).padStart(8, "0")}`;
}
