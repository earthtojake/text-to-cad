/**
 * Puts the CAD interpreter's directory first on PATH so `python`, `pip`, and
 * `cadgen` resolve to the runtime that carries cadgen. An entry already present
 * moves to the front instead of being duplicated; a missing PATH is created.
 * Windows keeps whatever spelling of the key the environment already uses.
 */
export function prependPathEntries(
  env: Record<string, string>,
  entries: readonly string[],
  platform: NodeJS.Platform = process.platform
): Record<string, string> {
  const wanted = entries.filter(
    (entry, index) => entry.length > 0 && entries.indexOf(entry) === index
  );
  if (wanted.length === 0) return env;
  const key = Object.keys(env).find((candidate) => candidate.toUpperCase() === 'PATH') ?? 'PATH';
  const separator = platform === 'win32' ? ';' : ':';
  const rest = (env[key] ?? '')
    .split(separator)
    .filter((entry) => entry.length > 0 && !wanted.includes(entry));
  return { ...env, [key]: [...wanted, ...rest].join(separator) };
}
