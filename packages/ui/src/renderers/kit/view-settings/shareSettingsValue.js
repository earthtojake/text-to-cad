// Settings are small JSON trees. Preserve equal branches so editing a clipping
// plane does not look like a change to every material, light and camera too.
export function shareSettingsValue(previous, next) {
  if (Object.is(previous, next)) return previous;
  if (!previous || !next || typeof previous !== "object" || typeof next !== "object" ||
      Array.isArray(previous) !== Array.isArray(next)) return next;
  const keys = Object.keys(next);
  let equal = keys.length === Object.keys(previous).length;
  const result = Array.isArray(next) ? [] : {};
  for (const key of keys) {
    result[key] = shareSettingsValue(previous[key], next[key]);
    if (!Object.hasOwn(previous, key) || result[key] !== previous[key]) equal = false;
  }
  return equal ? previous : result;
}
