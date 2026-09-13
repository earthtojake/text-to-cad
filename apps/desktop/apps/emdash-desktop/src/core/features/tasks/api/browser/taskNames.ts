export const MAX_TASK_NAME_LENGTH = 64;

type TaskNameTransformOptions = {
  preserveCapitalization?: boolean;
};

const applyCapitalization = (input: string, options?: TaskNameTransformOptions): string =>
  options?.preserveCapitalization ? input : input.toLowerCase();

export const liveTransformTaskName = (input: string, options?: TaskNameTransformOptions): string =>
  applyCapitalization(input, options)
    .replace(/\s+/g, '-')
    .replace(/[^a-zA-Z0-9-]/g, '')
    .replace(/-+/g, '-')
    .slice(0, MAX_TASK_NAME_LENGTH);

export const normalizeTaskName = (input: string, options?: TaskNameTransformOptions): string =>
  applyCapitalization(input, options)
    .trim()
    .replace(/\s+/g, '-')
    .replace(/[^a-zA-Z0-9-]/g, '')
    .replace(/-+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, MAX_TASK_NAME_LENGTH);

export const taskNameCollisionKey = (input: string): string =>
  normalizeTaskName(input).toLowerCase();

export const ensureUniqueTaskName = (
  baseName: string,
  existingNames: Iterable<string>,
  maxAttempts = 6,
  options?: TaskNameTransformOptions
): string => {
  const normalizedExisting = new Set(
    Array.from(existingNames, (name) => taskNameCollisionKey(name)).filter(Boolean)
  );
  const base = normalizeTaskName(baseName, options);
  if (base && !normalizedExisting.has(taskNameCollisionKey(base))) return base;

  for (let i = 2; i < 2 + maxAttempts; i++) {
    const candidate = normalizeTaskName(`${baseName}-${i}`, options);
    if (candidate && !normalizedExisting.has(taskNameCollisionKey(candidate))) {
      return candidate;
    }
  }

  const fallback = normalizeTaskName(`${baseName}-${Date.now().toString(36)}`, options);
  return fallback || base;
};
