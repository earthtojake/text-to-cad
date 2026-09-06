/**
 * Shared leak-check helper for session-lifecycle consumers.
 *
 * Guards the one drift vector shared chassis code cannot prevent: an incomplete
 * `evictSteps` list. Each runtime suite creates a session, evicts it, and asserts
 * that none of its per-key containers still holds the key.
 *
 * Not a test file itself (no `.test.` suffix) — Vitest will not collect it.
 */

export type LeakCheckContainer = {
  /** Appears in the failure message. */
  name: string;
  has: (key: string) => boolean;
};

/** Adapts a Map keyed by session key into a leak-check container. */
export function mapContainer(name: string, map: ReadonlyMap<string, unknown>): LeakCheckContainer {
  return { name, has: (key) => map.has(key) };
}

/** Adapts a Record-shaped published list into a leak-check container. */
export function recordContainer(
  name: string,
  read: () => Record<string, unknown>
): LeakCheckContainer {
  return { name, has: (key) => key in read() };
}

/**
 * Throws when any container still holds the key after eviction, naming the
 * leaking containers.
 */
export function expectNoSessionResidue(key: string, containers: LeakCheckContainer[]): void {
  const leaking = containers.filter((container) => container.has(key));
  if (leaking.length === 0) return;
  throw new Error(
    `session '${key}' is still held after eviction by: ` +
      leaking.map((container) => container.name).join(', ')
  );
}
