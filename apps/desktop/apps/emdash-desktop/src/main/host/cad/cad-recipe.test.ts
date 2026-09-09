import { createHash } from 'node:crypto';
import { realpathSync } from 'node:fs';
import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import {
  cadSourceRebuildToolPlan,
  cadStepOutputDeclaration,
  linkedSourceFromCadgenRecord,
  normalizeCadArtifactRelationship,
  readCadgenSourceProvenance,
  resolveCadBuildArtifactPath,
  resolveCadgenCacheRoot,
  resolveCadSourceArtifactRelationship,
} from './cad-recipe';

const temporaryDirectories: string[] = [];

afterEach(async () => {
  await Promise.all(temporaryDirectories.splice(0).map((path) => rm(path, { recursive: true })));
});

const RECIPE =
  'from cadgen import build123d as bd\nfrom cadgen import step\n\n@step()\ndef plate():\n    return bd.Box(10, 10, 2)\n';

describe('cadgen 0.5 recipes', () => {
  it('resolves out= project recipes from src into the STEP folder', async () => {
    const root = await temporaryDirectory('hardcore-cad-recipe-');
    const sourcePath = join(root, 'src', 'bracket.py');
    await mkdir(dirname(sourcePath), { recursive: true });
    await writeFile(
      sourcePath,
      'from cadgen import step\n\n@step(out="../STEP/bracket.step")\ndef bracket():\n    return None\n'
    );

    expect(resolveCadSourceArtifactRelationship({ workspacePath: root, sourcePath })).toEqual({
      workspacePath: root,
      relativeSourcePath: join('src', 'bracket.py'),
      relativeModelPath: join('STEP', 'bracket.step'),
      declaration: 'out',
    });
  });

  it('defaults a plain recipe to its sibling STEP', async () => {
    const root = await temporaryDirectory('hardcore-cad-recipe-');
    const sourcePath = join(root, 'plate.py');
    await writeFile(sourcePath, RECIPE);
    expect(resolveCadSourceArtifactRelationship({ workspacePath: root, sourcePath })).toMatchObject(
      { relativeModelPath: 'plate.step', declaration: 'sibling-default' }
    );
  });

  it('reads out= through module aliases and multiline decorators, and nothing else', () => {
    expect(
      cadStepOutputDeclaration(
        [
          'import cadgen as cg',
          '',
          '@cg.step(',
          '    kind="part",',
          '    out="../artifacts/plate.stp",',
          ')',
          'def plate():',
          '    return None',
        ].join('\n')
      )
    ).toEqual({ keyword: 'out', path: '../artifacts/plate.stp' });
    // write= was an intermediate 0.5 spelling; cadgen 0.5 rejects it, so it never resolves a path.
    expect(
      cadStepOutputDeclaration(
        'from cadgen import step\n\n@step(write="../STEP/plate.step")\ndef plate(): ...\n'
      )
    ).toBeNull();
    expect(
      cadStepOutputDeclaration(
        'from cadgen import step\n\n@step\n@metadata(out="elsewhere/plate.step")\ndef plate(): ...\n'
      )
    ).toBeNull();
    expect(
      cadStepOutputDeclaration('from build123d import Box\n\ndef gen_step(): ...\n')
    ).toBeNull();
  });

  it('keeps recipes and artifacts inside the workspace', async () => {
    const root = await temporaryDirectory('hardcore-cad-recipe-');
    const sourcePath = join(root, 'src', 'escape.py');
    await mkdir(dirname(sourcePath), { recursive: true });
    await writeFile(
      sourcePath,
      'from cadgen import step\n\n@step(out="../../outside.step")\ndef escape(): ...\n'
    );
    expect(resolveCadSourceArtifactRelationship({ workspacePath: root, sourcePath })).toBeNull();
    expect(
      normalizeCadArtifactRelationship({
        workspacePath: root,
        modelPath: 'STEP/a.step',
        sourcePath: '../elsewhere/a.py',
      })
    ).toBeNull();
    expect(
      normalizeCadArtifactRelationship({
        workspacePath: root,
        modelPath: 'STEP/a.step',
        sourcePath: 'src/a.py',
      })
    ).toMatchObject({
      relativeModelPath: join('STEP', 'a.step'),
      relativeSourcePath: join('src', 'a.py'),
      declaration: 'explicit',
    });
  });

  it('runs a recipe through the plain script door without --force', () => {
    expect(cadSourceRebuildToolPlan('src/plate.py')).toEqual({
      tool: 'model',
      args: ['src/plate.py', '--json'],
    });
    expect(cadSourceRebuildToolPlan('plate.step.py').args).toEqual(['plate.step.py', '--json']);
    expect(() => cadSourceRebuildToolPlan('plate.step')).toThrow(/Python @step model/);
  });

  it('maps the reported document back to the workspace STEP', () => {
    const workspacePath = '/workspace';
    expect(
      resolveCadBuildArtifactPath({
        workspacePath,
        relativeSourcePath: 'src/plate.py',
        build: { ok: true, sourceRef: 'src/plate.py', document: 'STEP/plate', outcome: 'built' },
      })
    ).toBe(join('STEP', 'plate.step'));
    expect(() =>
      resolveCadBuildArtifactPath({
        workspacePath,
        relativeSourcePath: 'src/plate.py',
        build: { ok: true, document: '../elsewhere/plate' },
      })
    ).toThrow(/inside the active model workspace/);
  });
});

describe('cadgen provenance records', () => {
  it("resolves the cache root by cadgen's rule", () => {
    expect(resolveCadgenCacheRoot({ CADGEN_CACHE_DIR: '/explicit' }, 'darwin', '/home/amy')).toBe(
      '/explicit'
    );
    expect(resolveCadgenCacheRoot({ XDG_CACHE_HOME: '/xdg' }, 'linux', '/home/amy')).toBe(
      join('/xdg', 'cadgen')
    );
    expect(resolveCadgenCacheRoot({}, 'darwin', '/home/amy')).toBe(
      join('/home/amy', '.cache', 'cadgen')
    );
    expect(
      resolveCadgenCacheRoot(
        { LOCALAPPDATA: 'C:\\Users\\amy\\AppData\\Local' },
        'win32',
        'C:\\Users\\amy'
      )
    ).toBe(join('C:\\Users\\amy\\AppData\\Local', 'cadgen'));
  });

  it('follows a python record to the recipe only when the recipe declares this STEP', async () => {
    const root = await temporaryDirectory('hardcore-cad-records-');
    const cacheRoot = join(root, 'cache');
    const stepPath = join(root, 'STEP', 'plate.step');
    const sourcePath = join(root, 'src', 'plate.py');
    await mkdir(dirname(stepPath), { recursive: true });
    await mkdir(dirname(sourcePath), { recursive: true });
    await writeFile(stepPath, 'step');
    await writeFile(
      sourcePath,
      'from cadgen import step\n\n@step(out="../STEP/plate.step")\ndef plate(): ...\n'
    );
    await writeRecord(cacheRoot, stepPath, {
      sourceKind: 'python',
      sourcePath: '../src/plate.py',
      sourceHash: 'abc',
    });

    expect(readCadgenSourceProvenance(stepPath, cacheRoot)).toEqual({
      sourceKind: 'python',
      sourcePath: realpathSync.native(sourcePath),
    });
    expect(
      linkedSourceFromCadgenRecord({ workspacePath: root, modelPath: stepPath, cacheRoot })
    ).toEqual({
      workspacePath: root,
      relativeSourcePath: join('src', 'plate.py'),
      relativeModelPath: join('STEP', 'plate.step'),
      declaration: 'record',
    });

    // The recipe now writes somewhere else: the stale record is not a link.
    await writeFile(
      sourcePath,
      'from cadgen import step\n\n@step(out="../STEP/other.step")\ndef plate(): ...\n'
    );
    expect(
      linkedSourceFromCadgenRecord({ workspacePath: root, modelPath: stepPath, cacheRoot })
    ).toBeNull();
  });

  it('ignores records that point outside the workspace, at legacy files, or at imports', async () => {
    const root = await temporaryDirectory('hardcore-cad-records-');
    const outside = await temporaryDirectory('hardcore-cad-outside-');
    const cacheRoot = join(root, 'cache');
    const stepPath = join(root, 'plate.step');
    await writeFile(stepPath, 'step');
    await writeFile(join(outside, 'plate.py'), RECIPE);
    await writeRecord(cacheRoot, stepPath, {
      sourceKind: 'python',
      sourcePath: join(outside, 'plate.py'),
    });
    expect(
      linkedSourceFromCadgenRecord({ workspacePath: root, modelPath: stepPath, cacheRoot })
    ).toBeNull();

    await writeFile(join(root, 'plate.step.py'), 'def gen_step(): ...\n');
    await writeRecord(cacheRoot, stepPath, { sourceKind: 'python', sourcePath: 'plate.step.py' });
    expect(
      linkedSourceFromCadgenRecord({ workspacePath: root, modelPath: stepPath, cacheRoot })
    ).toBeNull();

    await writeRecord(cacheRoot, stepPath, { sourceKind: 'step', sourceHash: 'deadbeef' });
    expect(
      linkedSourceFromCadgenRecord({ workspacePath: root, modelPath: stepPath, cacheRoot })
    ).toBeNull();

    expect(
      linkedSourceFromCadgenRecord({ workspacePath: root, modelPath: 'missing.step', cacheRoot })
    ).toBeNull();
  });
});

async function writeRecord(cacheRoot: string, stepPath: string, payload: Record<string, unknown>) {
  const artifact = realpathSync.native(stepPath);
  const source = resolve(dirname(artifact), String(payload.sourcePath ?? 'missing.py'));
  const model = `${source}::plate`;
  const hash = (value: string) => createHash('sha256').update(value).digest('hex');
  await mkdir(join(cacheRoot, 'index', 'output'), { recursive: true });
  await mkdir(join(cacheRoot, 'index', 'model'), { recursive: true });
  await writeFile(join(cacheRoot, 'index', 'output', hash(artifact)), JSON.stringify({ model }));
  await writeFile(
    join(cacheRoot, 'index', 'model', hash(model)),
    JSON.stringify({
      kind: 'record',
      model,
      script: source,
      sourceKind: payload.sourceKind,
      outputs: { [artifact]: { sha256: 'fixture' } },
    })
  );
}

async function temporaryDirectory(prefix: string): Promise<string> {
  const directory = await mkdtemp(join(tmpdir(), prefix));
  temporaryDirectories.push(directory);
  return directory;
}
