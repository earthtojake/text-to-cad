export function toFiniteNumber(value, fallback = 0) {
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue : fallback;
}

// A geometry refresh can validate the same selection many times. Keep its
// identity when every ID survives so React does not publish another UI state.
export function filterPreservingIdentity(values, predicate) {
  const filtered = values.filter(predicate);
  return filtered.length === values.length ? values : filtered;
}
