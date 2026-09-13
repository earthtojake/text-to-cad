import { existsSync } from 'node:fs';
import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { afterEach, expect, it, vi } from 'vitest';
import {
  rebuildCadModel,
  resolveCadArtifactTarget,
  validateCadModel,
} from './cad-validation-service';

vi.mock('electron', () => ({ app: { getPath: () => '/tmp/hardcore-runtime-test' } }));

const repository = resolve(dirname(fileURLToPath(import.meta.url)), '../../../../../../../..');
const python = join(
  repository,
  '.venv',
  process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python'
);
const scratchDirectories: string[] = [];

afterEach(async () => {
  vi.unstubAllEnvs();
  await Promise.all(
    scratchDirectories.splice(0).map((path) => rm(path, { recursive: true, force: true }))
  );
});

it.skipIf(!existsSync(python))(
  'builds, links, validates and restores documents against the current cadgen',
  async () => {
    const root = await mkdtemp(join(repository, 'models', 'hardcore-runtime-test-'));
    scratchDirectories.push(root);
    vi.stubEnv('HARDCORE_CAD_PYTHON', python);
    vi.stubEnv('CADGEN_CACHE_DIR', join(root, '.cache'));
    vi.stubEnv('CADGEN_DAEMON', '0');
    await mkdir(join(root, 'src'));
    await mkdir(join(root, 'STEP'));
    const source = join(root, 'src', 'plate.py');
    const artifact = join(root, 'STEP', 'plate.stp');
    const recipe = (width: number) => `from cadgen import build123d as bd, step
WIDTH = ${width}
@step(out="../STEP/plate.stp")
def plate():
    return bd.Box(WIDTH, 12, 4)
if __name__ == "__main__":
    plate()
`;
    await writeFile(source, recipe(30));
    const built = await rebuildCadModel({ workspacePath: root, filePath: source });
    expect(built.success, JSON.stringify(built)).toBe(true);
    if (!built.success) return;
    expect(built.artifact.modelPath).toBe(join('STEP', 'plate.stp'));
    expect(built.facts.size?.[0]).toBeCloseTo(30);
    expect(resolveCadArtifactTarget({ workspacePath: root, filePath: artifact })).toMatchObject({
      relativeSourcePath: join('src', 'plate.py'),
    });
    const accepted = await readFile(artifact);

    // Opening a document never executes even a broken source program.
    await writeFile(source, 'raise RuntimeError("opening must not execute this")\n');
    const opened = await validateCadModel({ workspacePath: root, filePath: artifact });
    expect(opened.success, JSON.stringify(opened)).toBe(true);
    expect(await readFile(artifact)).toEqual(accepted);

    await writeFile(source, recipe(42));
    const edited = await rebuildCadModel({ workspacePath: root, filePath: source });
    expect(edited.success, JSON.stringify(edited)).toBe(true);
    if (!edited.success) return;
    expect(edited.facts.size?.[0]).toBeCloseTo(42);
    expect(edited.artifact.modelHash).not.toBe(built.artifact.modelHash);

    // Leave the record describing 42 mm; the restored bytes still render as 30 mm.
    await writeFile(artifact, accepted);
    const restored = await validateCadModel({ workspacePath: root, filePath: artifact });
    expect(restored.success, JSON.stringify(restored)).toBe(true);
    if (!restored.success) return;
    expect(restored.artifact.modelHash).toBe(built.artifact.modelHash);
    expect(restored.facts.size?.[0]).toBeCloseTo(30);

    // A pre-0.5 decorator-only recipe must not silently accept an old output.
    await writeFile(source, recipe(54).split('if __name__')[0]);
    const missingEntryPoint = await rebuildCadModel({ workspacePath: root, filePath: source });
    expect(missingEntryPoint).toMatchObject({ success: false });
    expect(await readFile(artifact)).toEqual(accepted);
  },
  120_000
);
