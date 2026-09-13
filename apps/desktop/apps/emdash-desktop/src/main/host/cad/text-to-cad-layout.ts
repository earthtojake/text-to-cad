import { existsSync, readFileSync } from 'node:fs';
import { dirname, join, parse, resolve } from 'node:path';

/**
 * Where the desktop finds the canonical Text-to-CAD resources it runs on.
 *
 * The desktop lives at apps/desktop inside earthtojake/text-to-cad, so in a
 * checkout the root is the monorepo root: cadgen comes from packages/cadgen,
 * the CAD Viewer from apps/viewer, and the agent skills from skills/. A
 * packaged app carries a materialized copy under resources/text-to-cad laid
 * out like the cadgen distribution: the server is cadgen.viewer and the built
 * client is packaged inside cadgen/_runtime/viewer.
 *
 * Nothing here is inferred from cache directories or adjacent metadata: a root
 * counts only when every marker file is present.
 */
export type TextToCadLayoutKind = 'repository' | 'bundle';

export interface TextToCadLayout {
  kind: TextToCadLayoutKind;
  root: string;
  version: string;
  cadgenSource: string;
  skillsRoot: string;
  viewer: {
    root: string;
    /** The installed module launched with `python -m cadgen.viewer`. */
    launcher: string;
    /** The built client the launcher serves; `dist/index.html` must exist. */
    dist: string;
  };
  plugin: {
    codexManifest: string;
    claudeManifest: string;
  };
}

export const TEXT_TO_CAD_ROOT_ENV = 'HARDCORE_TEXT_TO_CAD_ROOT';
export const PACKAGED_TEXT_TO_CAD_DIRECTORY = 'text-to-cad';
export const PACKAGED_DESKTOP_TOOLING_DIRECTORY = 'text-to-cad-desktop';

const ROOT_MARKERS = [
  'VERSION',
  join('packages', 'cadgen', 'pyproject.toml'),
  join('skills', 'cad', 'SKILL.md'),
  join('skills', 'cad-viewer', 'SKILL.md'),
  join('.codex-plugin', 'plugin.json'),
  join('.claude-plugin', 'plugin.json'),
] as const;

export function resolveTextToCadLayout(root: string): TextToCadLayout | null {
  const resolvedRoot = resolve(root);
  if (!ROOT_MARKERS.every((marker) => existsSync(join(resolvedRoot, marker)))) return null;
  const viewer = resolveViewerRuntime(resolvedRoot);
  if (!viewer) return null;
  const version = readTextToCadVersion(resolvedRoot);
  if (!version) return null;
  return {
    kind: viewer.kind,
    root: resolvedRoot,
    version,
    cadgenSource: join(resolvedRoot, 'packages', 'cadgen'),
    skillsRoot: join(resolvedRoot, 'skills'),
    viewer: { root: viewer.root, launcher: viewer.launcher, dist: viewer.dist },
    plugin: {
      codexManifest: join(resolvedRoot, '.codex-plugin', 'plugin.json'),
      claudeManifest: join(resolvedRoot, '.claude-plugin', 'plugin.json'),
    },
  };
}

/**
 * Locate the Text-to-CAD root for this process: an explicit override, the
 * packaged bundle beside the app, or the monorepo checkout above the desktop.
 */
export function findTextToCadLayout(input: {
  env?: NodeJS.ProcessEnv;
  resourcesPath?: string | null;
  startDirectories?: readonly string[];
}): TextToCadLayout | null {
  const env = input.env ?? process.env;
  const configured = env[TEXT_TO_CAD_ROOT_ENV]?.trim();
  if (configured) return resolveTextToCadLayout(configured);
  if (input.resourcesPath) {
    const bundled = resolveTextToCadLayout(
      join(input.resourcesPath, PACKAGED_TEXT_TO_CAD_DIRECTORY)
    );
    if (bundled) return bundled;
  }
  for (const start of input.startDirectories ?? []) {
    let current = resolve(start);
    const root = parse(current).root;
    while (true) {
      const layout = resolveTextToCadLayout(current);
      if (layout) return layout;
      if (current === root) break;
      current = dirname(current);
    }
  }
  return null;
}

export function viewerClientIsBuilt(layout: Pick<TextToCadLayout, 'viewer'>): boolean {
  return existsSync(join(layout.viewer.dist, 'index.html'));
}

export function readTextToCadVersion(root: string): string | null {
  try {
    const version = readFileSync(join(root, 'VERSION'), 'utf8').trim();
    return /^\d+\.\d+\.\d+/.test(version) ? version : null;
  } catch {
    return null;
  }
}

function resolveViewerRuntime(
  root: string
): { kind: TextToCadLayoutKind; root: string; launcher: string; dist: string } | null {
  if (!existsSync(join(root, 'packages', 'cadgen', 'src', 'cadgen', 'viewer', '__main__.py')))
    return null;
  const client = join(root, 'apps', 'viewer');
  if (existsSync(join(client, 'package.json'))) {
    return {
      kind: 'repository',
      root: client,
      launcher: 'cadgen.viewer',
      dist: join(client, 'dist'),
    };
  }
  const dist = join(root, 'packages', 'cadgen', 'src', 'cadgen', '_runtime', 'viewer');
  return existsSync(join(dist, 'index.html'))
    ? { kind: 'bundle', root: dist, launcher: 'cadgen.viewer', dist }
    : null;
}
