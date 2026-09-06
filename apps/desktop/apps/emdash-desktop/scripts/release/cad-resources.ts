import { existsSync, readdirSync } from 'node:fs';
import { basename, dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

/** One electron-builder extraResources entry. */
export interface CadExtraResource {
  from: string;
  to: string;
  filter?: string[];
}

/** apps/desktop — the self-contained desktop workspace inside text-to-cad. */
export const HARDCORE_REPOSITORY_ROOT = resolve(
  dirname(fileURLToPath(import.meta.url)),
  '../../../..'
);

/** Packaged resource directories. */
export const PACKAGED_TEXT_TO_CAD_DIRECTORY = 'text-to-cad';
export const PACKAGED_DESKTOP_TOOLING_DIRECTORY = 'text-to-cad-desktop';
export const TEXT_TO_CAD_ROOT_ENV = 'HARDCORE_TEXT_TO_CAD_ROOT';

/**
 * The canonical Text-to-CAD tree the desktop packages from: the monorepo root
 * two levels above apps/desktop, unless a build points elsewhere.
 */
export function resolveTextToCadRoot(
  desktopRoot = HARDCORE_REPOSITORY_ROOT,
  environment: NodeJS.ProcessEnv = process.env
): string {
  const configured = environment[TEXT_TO_CAD_ROOT_ENV]?.trim();
  return configured ? resolve(configured) : resolve(desktopRoot, '..', '..');
}

/** What the source tree must provide before the packaged copy can be made. */
const TEXT_TO_CAD_SOURCE_FILES = [
  'VERSION',
  'LICENSE',
  '.codex-plugin/plugin.json',
  '.claude-plugin/plugin.json',
  '.claude-plugin/marketplace.json',
  'skills/cad/SKILL.md',
  'skills/cad-viewer/SKILL.md',
  'packages/cadgen/src/cadgen/viewer/__main__.py',
  'apps/viewer/dist/index.html',
  'apps/viewer/package.json',
  'packages/cadgen/pyproject.toml',
  'packages/cadgen/src/cadgen/__init__.py',
  'packages/cadgen/src/cadgen/_runtime/browser',
  'packages/cadgen/src/cadgen/_runtime/node',
] as const;

const DESKTOP_SOURCE_FILES = [
  'tooling/scripts/setup-cad.mjs',
  'tooling/cad-runtime-constraints.txt',
] as const;

/**
 * What ships under Contents/Resources: the desktop's CAD tooling beside a
 * Text-to-CAD bundle whose cadgen package carries both the Python server and
 * the built client.
 */
export const PACKAGED_CAD_FILES = [
  `${PACKAGED_DESKTOP_TOOLING_DIRECTORY}/tooling/scripts/setup-cad.mjs`,
  `${PACKAGED_DESKTOP_TOOLING_DIRECTORY}/tooling/cad-runtime-constraints.txt`,
  `${PACKAGED_DESKTOP_TOOLING_DIRECTORY}/skills/cad-desktop/SKILL.md`,
  `${PACKAGED_TEXT_TO_CAD_DIRECTORY}/VERSION`,
  `${PACKAGED_TEXT_TO_CAD_DIRECTORY}/LICENSE`,
  `${PACKAGED_TEXT_TO_CAD_DIRECTORY}/.codex-plugin/plugin.json`,
  `${PACKAGED_TEXT_TO_CAD_DIRECTORY}/.claude-plugin/plugin.json`,
  `${PACKAGED_TEXT_TO_CAD_DIRECTORY}/.claude-plugin/marketplace.json`,
  `${PACKAGED_TEXT_TO_CAD_DIRECTORY}/skills/cad/SKILL.md`,
  `${PACKAGED_TEXT_TO_CAD_DIRECTORY}/skills/cad-viewer/SKILL.md`,
  `${PACKAGED_TEXT_TO_CAD_DIRECTORY}/packages/cadgen/src/cadgen/viewer/__main__.py`,
  `${PACKAGED_TEXT_TO_CAD_DIRECTORY}/packages/cadgen/src/cadgen/_runtime/viewer/index.html`,
  `${PACKAGED_TEXT_TO_CAD_DIRECTORY}/packages/cadgen/pyproject.toml`,
  `${PACKAGED_TEXT_TO_CAD_DIRECTORY}/packages/cadgen/src/cadgen/__init__.py`,
  `${PACKAGED_TEXT_TO_CAD_DIRECTORY}/packages/cadgen/src/cadgen/_runtime/browser`,
  `${PACKAGED_TEXT_TO_CAD_DIRECTORY}/packages/cadgen/src/cadgen/_runtime/node`,
] as const;

export function assertCadBundleSource(
  textToCadRoot = resolveTextToCadRoot(),
  desktopRoot = HARDCORE_REPOSITORY_ROOT
): void {
  assertFiles(
    textToCadRoot,
    TEXT_TO_CAD_SOURCE_FILES,
    `The Text-to-CAD tree at ${textToCadRoot} is incomplete. Run pnpm cad:setup from apps/desktop (it builds apps/viewer) before packaging.`
  );
  assertFiles(
    desktopRoot,
    DESKTOP_SOURCE_FILES,
    'The CAD environment installer or dependency lock is missing from apps/desktop.'
  );
}

export function assertPackagedCadResources(appOutDir: string): void {
  const resourcesRoot = packagedResourcesRoot(appOutDir);
  if (!resourcesRoot) {
    throw new Error(`Packaged app resources were not found under ${appOutDir}.`);
  }
  assertFiles(
    resourcesRoot,
    PACKAGED_CAD_FILES,
    'The packaged app is missing its Text-to-CAD runtime, viewer, or skills.'
  );
}

/**
 * electron-builder extraResources for the CAD bundle. The client build is
 * placed inside cadgen/_runtime/viewer, exactly where the installed wheel
 * resolves it. Skills carry instructions only.
 */
export function cadExtraResources(
  textToCadRoot = resolveTextToCadRoot(),
  desktopRoot = HARDCORE_REPOSITORY_ROOT
): CadExtraResource[] {
  const bundle = PACKAGED_TEXT_TO_CAD_DIRECTORY;
  const viewerRuntime = `${bundle}/packages/cadgen/src/cadgen/_runtime/viewer`;
  const pythonFilter = ['**/*', '!**/__pycache__/**', '!**/*.pyc'];
  return [
    {
      from: join(desktopRoot, 'tooling', 'scripts', 'setup-cad.mjs'),
      to: `${PACKAGED_DESKTOP_TOOLING_DIRECTORY}/tooling/scripts/setup-cad.mjs`,
    },
    {
      from: join(desktopRoot, 'tooling', 'cad-runtime-constraints.txt'),
      to: `${PACKAGED_DESKTOP_TOOLING_DIRECTORY}/tooling/cad-runtime-constraints.txt`,
    },
    // Skills that exist only inside the desktop; setup-cad.mjs stages them on top of the plugin.
    {
      from: join(desktopRoot, 'skills'),
      to: `${PACKAGED_DESKTOP_TOOLING_DIRECTORY}/skills`,
    },
    { from: join(textToCadRoot, 'VERSION'), to: `${bundle}/VERSION` },
    { from: join(textToCadRoot, 'LICENSE'), to: `${bundle}/LICENSE` },
    { from: join(textToCadRoot, '.codex-plugin'), to: `${bundle}/.codex-plugin` },
    { from: join(textToCadRoot, '.claude-plugin'), to: `${bundle}/.claude-plugin` },
    {
      from: join(textToCadRoot, 'skills'),
      to: `${bundle}/skills`,
      filter: [
        '**/*',
        '!**/node_modules/**',
        '!**/.venv/**',
        '!**/__pycache__/**',
        '!**/*.pyc',
        '!cad-viewer/scripts/viewer',
        '!cad-viewer/scripts/viewer/**',
      ],
    },
    {
      from: join(textToCadRoot, 'packages', 'cadgen'),
      to: `${bundle}/packages/cadgen`,
      filter: [...pythonFilter, '!build/**', '!**/*.egg-info/**', '!src/cadgen/_runtime/viewer/**'],
    },
    { from: join(textToCadRoot, 'apps', 'viewer', 'dist'), to: viewerRuntime },
  ];
}

export function packagedResourcesRoot(appOutDir: string): string | null {
  const direct = join(appOutDir, 'resources');
  if (existsSync(direct)) return direct;

  const ownMacResources = basename(appOutDir).endsWith('.app')
    ? join(appOutDir, 'Contents', 'Resources')
    : null;
  if (ownMacResources && existsSync(ownMacResources)) return ownMacResources;

  if (!existsSync(appOutDir)) return null;
  const appBundle = readdirSync(appOutDir, { withFileTypes: true }).find(
    (entry) => entry.isDirectory() && entry.name.endsWith('.app')
  );
  const nestedMacResources = appBundle
    ? join(appOutDir, appBundle.name, 'Contents', 'Resources')
    : null;
  return nestedMacResources && existsSync(nestedMacResources) ? nestedMacResources : null;
}

/** Every unpacked app's Resources directory that carries the CAD bundle. */
export function findPackagedCadResourceRoots(releaseDir: string): string[] {
  if (!existsSync(releaseDir)) return [];

  const candidates = [
    releaseDir,
    ...readdirSync(releaseDir, { withFileTypes: true })
      .filter((entry) => entry.isDirectory())
      .map((entry) => join(releaseDir, entry.name)),
  ];
  const roots = new Set<string>();
  for (const candidate of candidates) {
    const resources = packagedResourcesRoot(candidate);
    if (!resources) continue;
    const setup = join(
      resources,
      PACKAGED_DESKTOP_TOOLING_DIRECTORY,
      'tooling',
      'scripts',
      'setup-cad.mjs'
    );
    if (existsSync(setup)) roots.add(resolve(resources));
  }
  return [...roots].sort();
}

function assertFiles(root: string, relativePaths: readonly string[], message: string): void {
  const missing = relativePaths.filter((path) => !existsSync(join(root, path)));
  if (missing.length === 0) return;
  throw new Error(`${message}\nMissing:\n${missing.map((path) => `- ${path}`).join('\n')}`);
}
