import type { PluginFs } from '#primitives/plugin-fs/api';

export type ConfigLayer<T> = {
  root: string;
  content: string | null;
  parsed: T | null;
};

/**
 * Read the same relative config path from each root in order.
 * Roots should be ordered from most-specific (workspace) to least-specific (global).
 * Returns one entry per root; `content` is null when the file does not exist.
 */
export async function readHierarchical(
  fs: PluginFs,
  relativePath: string,
  roots: string[]
): Promise<Array<{ root: string; content: string | null }>> {
  return Promise.all(
    roots.map(async (root) => ({
      root,
      content: await fs.read(`${root}/${relativePath}`),
    }))
  );
}

/**
 * Parse each layer and merge them from least-specific to most-specific
 * so that workspace settings override global settings.
 *
 * Layers should be ordered from most-specific to least-specific
 * (same as the output of readHierarchical).
 */
export function readMergedConfig<T>(
  layers: Array<{ root: string; content: string | null }>,
  parse: (content: string) => T,
  merge: (base: T, override: T) => T,
  defaultValue: T
): T {
  // Reverse so we fold from least-specific (last) to most-specific (first)
  const reversed = [...layers].reverse();
  return reversed.reduce<T>((acc, layer) => {
    if (layer.content === null) return acc;
    try {
      return merge(acc, parse(layer.content));
    } catch {
      return acc;
    }
  }, defaultValue);
}
