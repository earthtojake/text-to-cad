import type { ModelOption } from '../../api/models/config';

/**
 * Maps the model id a conversation persisted (the desktop's own catalog id,
 * for example `claude-fable-5`) onto the value the agent actually advertises
 * for its model config option (`claude-fable-5-1`, `opus[1m]`, ...).
 *
 * Providers own their option values, so the desktop id rarely matches
 * verbatim. Resolution order: exact id, exact name, the advertised id that
 * extends the requested one (`claude-fable-5` -> `claude-fable-5-1`), then the
 * model family word shared by both (`claude-opus-4-8` -> `opus[1m]`). Returns
 * null when nothing matches; callers then leave the agent's default in place.
 */
export function resolveModelOptionValue(
  available: readonly ModelOption[],
  requested: string
): string | null {
  const wanted = requested.trim();
  if (!wanted) return null;
  const lower = wanted.toLowerCase();

  const exact = available.find((option) => option.id === wanted);
  if (exact) return exact.id;

  const byName = available.find((option) => option.name.trim().toLowerCase() === lower);
  if (byName) return byName.id;

  const extended = available
    .filter((option) => option.id.toLowerCase().startsWith(`${lower}-`))
    .sort((a, b) => a.id.length - b.id.length);
  if (extended[0]) return extended[0].id;

  const family = modelFamily(lower);
  if (!family) return null;
  const sameFamily = available.filter(
    (option) =>
      modelFamily(option.id.toLowerCase()) === family ||
      modelFamily(option.name.toLowerCase()) === family
  );
  return sameFamily[0]?.id ?? null;
}

const FAMILY_WORDS = ['fable', 'opus', 'sonnet', 'haiku', 'mythos'] as const;

function modelFamily(value: string): string | null {
  return FAMILY_WORDS.find((word) => value.includes(word)) ?? null;
}
