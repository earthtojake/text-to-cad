import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import {
  assertCadBundleSource,
  assertPackagedCadResources,
  cadExtraResources,
  findPackagedCadResourceRoots,
  packagedResourcesRoot,
  resolveTextToCadRoot,
} from './cad-resources';

const roots: string[] = [];

afterEach(async () => {
  await Promise.all(roots.splice(0).map((root) => rm(root, { force: true, recursive: true })));
});

const SOURCE_FILES = [
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
  'packages/cadgen/src/cadgen/_runtime/browser/render.html',
  'packages/cadgen/src/cadgen/_runtime/node/mesh-export.mjs',
];

const DESKTOP_FILES = [
  'tooling/scripts/setup-cad.mjs',
  'tooling/cad-runtime-constraints.txt',
  'skills/cad-desktop/SKILL.md',
];

describe('CAD release resources', () => {
  it('packages from the monorepo root above apps/desktop unless overridden', () => {
    expect(resolveTextToCadRoot('/repo/apps/desktop', {})).toBe('/repo');
    expect(
      resolveTextToCadRoot('/repo/apps/desktop', { HARDCORE_TEXT_TO_CAD_ROOT: '/elsewhere' })
    ).toBe('/elsewhere');
  });

  it('fails before packaging when the viewer is not built or the tree is incomplete', async () => {
    const textToCad = await temporaryRoot();
    const desktop = await temporaryRoot();
    await createFiles(desktop, DESKTOP_FILES);
    await createFiles(
      textToCad,
      SOURCE_FILES.filter((path) => path !== 'apps/viewer/dist/index.html')
    );
    expect(() => assertCadBundleSource(textToCad, desktop)).toThrow(
      /incomplete[\s\S]*apps\/viewer\/dist\/index\.html/
    );
  });

  it('accepts a complete Text-to-CAD tree and desktop tooling', async () => {
    const textToCad = await temporaryRoot();
    const desktop = await temporaryRoot();
    await createFiles(desktop, DESKTOP_FILES);
    await createFiles(textToCad, SOURCE_FILES);
    expect(() => assertCadBundleSource(textToCad, desktop)).not.toThrow();
  });

  it('ships the viewer client inside cadgen and no server runtime inside skills', () => {
    const resources = cadExtraResources('/repo', '/repo/apps/desktop');
    const targets = resources.map((entry) => entry.to);
    expect(targets).toContain('text-to-cad/packages/cadgen/src/cadgen/_runtime/viewer');
    expect(targets.some((target) => target.includes('skills/cad-viewer/scripts'))).toBe(false);
    expect(targets).toContain('text-to-cad/packages/cadgen');
    expect(targets).toContain('text-to-cad-desktop/tooling/scripts/setup-cad.mjs');
    const skills = resources.find((entry) => entry.to === 'text-to-cad/skills');
    expect(skills?.filter).toContain('!cad-viewer/scripts/viewer/**');
    const viewerDist = resources.find(
      (entry) => entry.to === 'text-to-cad/packages/cadgen/src/cadgen/_runtime/viewer'
    );
    expect(viewerDist?.from).toBe(join('/repo', 'apps', 'viewer', 'dist'));
  });

  it('finds and verifies macOS packaged resources', async () => {
    const root = await temporaryRoot();
    const appOutDir = join(root, 'mac-arm64');
    const resources = join(appOutDir, 'Hardcore.app', 'Contents', 'Resources');
    await createPackagedFiles(resources);
    expect(packagedResourcesRoot(appOutDir)).toBe(resources);
    expect(() => assertPackagedCadResources(appOutDir)).not.toThrow();
  });

  it('finds and verifies unpacked Linux and Windows resources', async () => {
    const root = await temporaryRoot();
    const appOutDir = join(root, 'linux-unpacked');
    const resources = join(appOutDir, 'resources');
    await createPackagedFiles(resources);
    expect(packagedResourcesRoot(appOutDir)).toBe(resources);
    expect(() => assertPackagedCadResources(appOutDir)).not.toThrow();
  });

  it('discovers each unpacked CAD bundle in a release directory', async () => {
    const root = await temporaryRoot();
    const linuxResources = join(root, 'release', 'linux-unpacked', 'resources');
    const macResources = join(
      root,
      'release',
      'mac-arm64',
      'Hardcore.app',
      'Contents',
      'Resources'
    );
    await createPackagedFiles(linuxResources);
    await createPackagedFiles(macResources);

    expect(findPackagedCadResourceRoots(join(root, 'release'))).toEqual(
      [linuxResources, macResources].sort()
    );
  });
});

async function temporaryRoot(): Promise<string> {
  const root = await mkdtemp(join(tmpdir(), 'hardcore-cad-release-'));
  roots.push(root);
  return root;
}

async function createPackagedFiles(resources: string): Promise<void> {
  await createFiles(resources, [
    'text-to-cad-desktop/tooling/scripts/setup-cad.mjs',
    'text-to-cad-desktop/tooling/cad-runtime-constraints.txt',
    'text-to-cad-desktop/skills/cad-desktop/SKILL.md',
    'text-to-cad/VERSION',
    'text-to-cad/LICENSE',
    'text-to-cad/.codex-plugin/plugin.json',
    'text-to-cad/.claude-plugin/plugin.json',
    'text-to-cad/.claude-plugin/marketplace.json',
    'text-to-cad/skills/cad/SKILL.md',
    'text-to-cad/skills/cad-viewer/SKILL.md',
    'text-to-cad/packages/cadgen/src/cadgen/viewer/__main__.py',
    'text-to-cad/packages/cadgen/src/cadgen/_runtime/viewer/index.html',
    'text-to-cad/packages/cadgen/pyproject.toml',
    'text-to-cad/packages/cadgen/src/cadgen/__init__.py',
    'text-to-cad/packages/cadgen/src/cadgen/_runtime/browser/render.html',
    'text-to-cad/packages/cadgen/src/cadgen/_runtime/node/mesh-export.mjs',
  ]);
}

async function createFiles(root: string, paths: readonly string[]): Promise<void> {
  await Promise.all(
    paths.map(async (path) => {
      const target = join(root, path);
      await mkdir(dirname(target), { recursive: true });
      await writeFile(target, 'fixture');
    })
  );
}
