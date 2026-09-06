import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { afterEach, describe, expect, it } from 'vitest';
import {
  findTextToCadLayout,
  resolveTextToCadLayout,
  viewerClientIsBuilt,
} from './text-to-cad-layout';

const temporaryDirectories: string[] = [];

afterEach(async () => {
  await Promise.all(temporaryDirectories.splice(0).map((path) => rm(path, { recursive: true })));
});

const MARKERS = [
  'VERSION',
  'packages/cadgen/pyproject.toml',
  'packages/cadgen/src/cadgen/viewer/__main__.py',
  'skills/cad/SKILL.md',
  'skills/cad-viewer/SKILL.md',
  '.codex-plugin/plugin.json',
  '.claude-plugin/plugin.json',
];

describe('Text-to-CAD layout', () => {
  it('recognizes this monorepo checkout as the canonical root', () => {
    const repositoryRoot = resolve(
      dirname(fileURLToPath(import.meta.url)),
      '../../../../../../../..'
    );
    const layout = resolveTextToCadLayout(repositoryRoot);
    expect(layout).toMatchObject({
      kind: 'repository',
      root: repositoryRoot,
      cadgenSource: join(repositoryRoot, 'packages', 'cadgen'),
      skillsRoot: join(repositoryRoot, 'skills'),
      viewer: {
        root: join(repositoryRoot, 'apps', 'viewer'),
        launcher: 'cadgen.viewer',
      },
    });
    expect(layout?.version).toMatch(/^\d+\.\d+\.\d+/);
  });

  it('walks up from the desktop app to the monorepo root', async () => {
    const root = await temporaryRoot();
    await createFiles(root, [...MARKERS, 'apps/viewer/package.json']);
    await writeFile(join(root, 'VERSION'), '0.4.28\n');
    const nested = join(root, 'apps', 'desktop', 'apps', 'emdash-desktop');
    await mkdir(nested, { recursive: true });

    expect(findTextToCadLayout({ env: {}, startDirectories: [nested] })).toMatchObject({
      kind: 'repository',
      root,
      version: '0.4.28',
    });
  });

  it('prefers an explicit root and rejects one that lacks a marker', async () => {
    const root = await temporaryRoot();
    await createFiles(root, [...MARKERS, 'apps/viewer/package.json']);
    await writeFile(join(root, 'VERSION'), '0.4.28\n');
    const incomplete = await temporaryRoot();
    await createFiles(incomplete, MARKERS.slice(1));

    expect(
      findTextToCadLayout({
        env: { HARDCORE_TEXT_TO_CAD_ROOT: root },
        startDirectories: [incomplete],
      })?.root
    ).toBe(root);
    expect(
      findTextToCadLayout({
        env: { HARDCORE_TEXT_TO_CAD_ROOT: incomplete },
        startDirectories: [root],
      })
    ).toBeNull();
    expect(resolveTextToCadLayout(incomplete)).toBeNull();
  });

  it('uses the bundled cadgen viewer beside a packaged app', async () => {
    const resources = await temporaryRoot();
    const bundle = join(resources, 'text-to-cad');
    await createFiles(bundle, [
      ...MARKERS,
      'packages/cadgen/src/cadgen/viewer/__main__.py',
      'packages/cadgen/src/cadgen/_runtime/viewer/index.html',
    ]);
    await writeFile(join(bundle, 'VERSION'), '0.5.0\n');

    const layout = findTextToCadLayout({ env: {}, resourcesPath: resources });
    expect(layout).toMatchObject({
      kind: 'bundle',
      root: bundle,
      version: '0.5.0',
      viewer: {
        launcher: 'cadgen.viewer',
      },
    });
    expect(layout && viewerClientIsBuilt(layout)).toBe(true);
  });

  it('reports an unbuilt viewer client instead of guessing', async () => {
    const root = await temporaryRoot();
    await createFiles(root, [...MARKERS, 'apps/viewer/package.json']);
    await writeFile(join(root, 'VERSION'), '0.4.28\n');
    const layout = resolveTextToCadLayout(root);
    expect(layout && viewerClientIsBuilt(layout)).toBe(false);
  });

  it('does not infer a root from a viewer directory alone', async () => {
    const root = await temporaryRoot();
    await createFiles(root, ['apps/viewer/package.json', 'VERSION']);
    expect(resolveTextToCadLayout(root)).toBeNull();
  });
});

async function temporaryRoot(): Promise<string> {
  const root = await mkdtemp(join(tmpdir(), 'hardcore-text-to-cad-layout-'));
  temporaryDirectories.push(root);
  return root;
}

async function createFiles(root: string, paths: readonly string[]): Promise<void> {
  await Promise.all(
    paths.map(async (path) => {
      const target = join(root, path);
      await mkdir(dirname(target), { recursive: true });
      await writeFile(target, path === 'VERSION' ? '0.4.28\n' : 'fixture');
    })
  );
}
