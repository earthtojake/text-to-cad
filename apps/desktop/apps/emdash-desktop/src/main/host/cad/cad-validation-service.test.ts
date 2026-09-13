import { createHash } from 'node:crypto';
import { realpathSync } from 'node:fs';
import { chmod, mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join, relative, resolve } from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  cadArtifactOperationKey,
  cadArtifactIdentity,
  cadInspectionToolPlan,
  cadSourceRebuildToolPlan,
  cadToolEnvironment,
  cadValidationModelPath,
  cadValidationInputRevision,
  resolveCadArtifactTarget,
  validateCadModel,
} from './cad-validation-service';

vi.mock('electron', () => ({ app: { getPath: () => '/tmp/hardcore-test-user-data' } }));

const temporaryDirectories: string[] = [];
const originalCadgenCacheDir = process.env.CADGEN_CACHE_DIR;
const originalCadPython = process.env.HARDCORE_CAD_PYTHON;
const originalCadTestLog = process.env.HARDCORE_CAD_TEST_LOG;

afterEach(async () => {
  await Promise.all(temporaryDirectories.splice(0).map((path) => rm(path, { recursive: true })));
  restoreEnvironment('CADGEN_CACHE_DIR', originalCadgenCacheDir);
  restoreEnvironment('HARDCORE_CAD_PYTHON', originalCadPython);
  restoreEnvironment('HARDCORE_CAD_TEST_LOG', originalCadTestLog);
});

describe('CAD validation service path boundary', () => {
  it('rejects a CAD target outside its model workspace', async () => {
    const workspacePath = await mkdtemp(join(tmpdir(), 'hardcore-cad-validation-'));
    temporaryDirectories.push(workspacePath);

    const result = await validateCadModel({
      workspacePath,
      filePath: join(tmpdir(), 'outside.step'),
    });

    expect(result).toEqual({
      success: false,
      error: 'CAD files must be inside the active model workspace.',
    });
  });

  it('reports a missing CAD file before starting the runtime', async () => {
    const workspacePath = await mkdtemp(join(tmpdir(), 'hardcore-cad-validation-'));
    temporaryDirectories.push(workspacePath);
    const filePath = join(workspacePath, 'missing.step.py');

    const result = await validateCadModel({ workspacePath, filePath });

    expect(result).toEqual({
      success: false,
      error: `Canonical CAD artifact does not exist: ${join(workspacePath, 'missing.step')}. Rebuild its source explicitly to create it.`,
    });
  });

  it('resolves relative CAD paths against the active workspace', async () => {
    const workspacePath = await mkdtemp(join(tmpdir(), 'hardcore-cad-validation-'));
    temporaryDirectories.push(workspacePath);
    await mkdir(join(workspacePath, 'models'));
    await writeFile(join(workspacePath, 'models', 'car.step'), 'accepted-step');

    expect(resolveCadArtifactTarget({ workspacePath, filePath: 'models/car.step' })).toEqual({
      success: true,
      workspacePath,
      relativeModelPath: 'models/car.step',
    });
    expect(cadArtifactOperationKey({ workspacePath, filePath: 'models/car.step' })).toBe(
      cadArtifactOperationKey({
        workspacePath,
        filePath: join(workspacePath, 'models', 'car.step'),
      })
    );
  });

  it('derives the canonical revision from the accepted artifact bytes', async () => {
    const workspacePath = await mkdtemp(join(tmpdir(), 'hardcore-cad-validation-'));
    temporaryDirectories.push(workspacePath);
    await writeFile(join(workspacePath, 'car.py'), 'source-v2');
    await writeFile(join(workspacePath, 'car.step'), 'step-v2');

    const sourceHash = createHash('sha256').update('source-v2').digest('hex');
    const modelHash = createHash('sha256').update('step-v2').digest('hex');
    expect(cadArtifactIdentity(workspacePath, 'car.step', 'car.py')).toEqual({
      revisionId: `sha256:${modelHash}`,
      modelPath: 'car.step',
      modelHash,
      sourcePath: 'car.py',
      sourceHash,
    });
  });

  it('distinguishes same-path validation requests by current source bytes', async () => {
    const workspacePath = await mkdtemp(join(tmpdir(), 'hardcore-cad-validation-'));
    temporaryDirectories.push(workspacePath);
    const filePath = join(workspacePath, 'car.py');
    await writeFile(filePath, 'OVERALL_LENGTH = 4200');
    await writeFile(join(workspacePath, 'car.step'), 'step-v1');
    const initial = cadValidationInputRevision({ workspacePath, filePath });

    await writeFile(filePath, 'OVERALL_LENGTH = 4300');

    expect(cadValidationInputRevision({ workspacePath, filePath })).not.toBe(initial);
  });

  it("follows cadgen's provenance record from a STEP back to its recipe", async () => {
    const workspacePath = await mkdtemp(join(tmpdir(), 'hardcore-cad-validation-'));
    temporaryDirectories.push(workspacePath);
    const sourcePath = join(workspacePath, 'models', 'car.py');
    const stepPath = join(workspacePath, 'models', 'car.step');
    await mkdir(dirname(stepPath), { recursive: true });
    await writeFile(
      sourcePath,
      'from cadgen import build123d as bd\nfrom cadgen import step\n\n@step()\ndef car():\n    return bd.Box(10, 10, 10)\n'
    );
    await writeFile(stepPath, 'step-v1');
    await writeProvenanceRecord(workspacePath, stepPath, {
      sourceKind: 'python',
      sourcePath: 'car.py',
    });
    const initial = cadValidationInputRevision({ workspacePath, filePath: stepPath });

    expect(resolveCadArtifactTarget({ workspacePath, filePath: stepPath })).toEqual({
      success: true,
      workspacePath,
      relativeModelPath: 'models/car.step',
      relativeSourcePath: 'models/car.py',
    });

    await writeFile(
      sourcePath,
      'from cadgen import build123d as bd\nfrom cadgen import step\n\n@step()\ndef car():\n    return bd.Box(10, 10, 10)\n'.replace(
        '10, 10, 10',
        '12, 10, 10'
      )
    );

    expect(cadValidationInputRevision({ workspacePath, filePath: stepPath })).not.toBe(initial);
  });

  it('keeps stale linked source bytes from redefining the accepted STEP revision', async () => {
    const workspacePath = await mkdtemp(join(tmpdir(), 'hardcore-cad-validation-'));
    temporaryDirectories.push(workspacePath);
    const sourcePath = join(workspacePath, 'car.py');
    await writeFile(sourcePath, 'OVERALL_LENGTH = 4200');
    await writeFile(join(workspacePath, 'car.step'), 'accepted-step');
    const accepted = cadArtifactIdentity(workspacePath, 'car.step', 'car.py');

    await writeFile(sourcePath, 'OVERALL_LENGTH = 4300');
    const reopened = cadArtifactIdentity(workspacePath, 'car.step', 'car.py');

    expect(reopened.revisionId).toBe(accepted.revisionId);
    expect(reopened.modelHash).toBe(accepted.modelHash);
    expect(reopened.sourceHash).not.toBe(accepted.sourceHash);
    expect(resolveCadArtifactTarget({ workspacePath, filePath: sourcePath })).toMatchObject({
      success: true,
      relativeModelPath: 'car.step',
      relativeSourcePath: 'car.py',
    });
  });

  it('accepts a valid STEP when the recipe its record names is missing', async () => {
    const workspacePath = await mkdtemp(join(tmpdir(), 'hardcore-cad-validation-'));
    temporaryDirectories.push(workspacePath);
    const stepPath = join(workspacePath, 'models', 'car.step');
    await mkdir(dirname(stepPath), { recursive: true });
    await writeFile(stepPath, 'accepted-step');
    await writeProvenanceRecord(workspacePath, stepPath, {
      sourceKind: 'python',
      sourcePath: 'car.py',
    });

    const target = resolveCadArtifactTarget({ workspacePath, filePath: stepPath });
    expect(target).toEqual({
      success: true,
      workspacePath,
      relativeModelPath: 'models/car.step',
    });
    expect(cadArtifactIdentity(workspacePath, 'models/car.step')).toEqual({
      revisionId: `sha256:${createHash('sha256').update('accepted-step').digest('hex')}`,
      modelPath: 'models/car.step',
      modelHash: createHash('sha256').update('accepted-step').digest('hex'),
    });
  });

  it('does not guess that a same-stem Python file owns an imported STEP', async () => {
    const workspacePath = await mkdtemp(join(tmpdir(), 'hardcore-cad-validation-'));
    temporaryDirectories.push(workspacePath);
    const stepPath = join(workspacePath, 'vendor.step');
    await writeFile(stepPath, 'imported-step');
    await writeFile(join(workspacePath, 'vendor.py'), 'UNRELATED_HELPER = True');

    expect(resolveCadArtifactTarget({ workspacePath, filePath: stepPath })).toEqual({
      success: true,
      workspacePath,
      relativeModelPath: 'vendor.step',
    });
  });

  it('rejects record provenance that escapes the model workspace', async () => {
    const workspacePath = await mkdtemp(join(tmpdir(), 'hardcore-cad-validation-'));
    const outsidePath = await mkdtemp(join(tmpdir(), 'hardcore-cad-outside-'));
    temporaryDirectories.push(workspacePath, outsidePath);
    const stepPath = join(workspacePath, 'models', 'car.step');
    const outsideSource = join(outsidePath, 'car.py');
    await mkdir(dirname(stepPath), { recursive: true });
    await writeFile(stepPath, 'step-v1');
    await writeFile(
      outsideSource,
      'from cadgen import build123d as bd\nfrom cadgen import step\n\n@step()\ndef car():\n    return bd.Box(10, 10, 10)\n'
    );
    await writeProvenanceRecord(workspacePath, stepPath, {
      sourceKind: 'python',
      sourcePath: relative(dirname(stepPath), outsideSource),
    });
    const initial = cadValidationInputRevision({ workspacePath, filePath: stepPath });

    await writeFile(
      outsideSource,
      'from cadgen import build123d as bd\nfrom cadgen import step\n\n@step()\ndef car():\n    return bd.Box(10, 10, 10)\n'.replace(
        '10, 10, 10',
        '12, 10, 10'
      )
    );

    expect(cadValidationInputRevision({ workspacePath, filePath: stepPath })).toBe(initial);
  });

  it('runs a recipe only through the explicit source rebuild path, never with --force', () => {
    expect(cadSourceRebuildToolPlan('car.py')).toEqual({
      tool: 'model',
      args: ['car.py', '--json'],
    });
  });

  it('serializes source rebuilds and read-only inspection by canonical STEP', () => {
    const workspacePath = join(tmpdir(), 'hardcore-operation-key');

    expect(
      cadArtifactOperationKey({ workspacePath, filePath: join(workspacePath, 'car.py') })
    ).toBe(cadArtifactOperationKey({ workspacePath, filePath: join(workspacePath, 'car.step') }));
  });

  it('serializes a custom @step(out=...) recipe with its canonical STEP', async () => {
    const workspacePath = await mkdtemp(join(tmpdir(), 'hardcore-custom-operation-key-'));
    temporaryDirectories.push(workspacePath);
    const sourcePath = join(workspacePath, 'src', 'STEP', 'plate.py');
    const modelPath = join(workspacePath, 'STEP', 'plate.step');
    await mkdir(dirname(sourcePath), { recursive: true });
    await writeFile(
      sourcePath,
      [
        'from cadgen import step',
        '',
        '@step(out="../../STEP/plate.step")',
        'def plate():',
        '    return None',
      ].join('\n')
    );

    expect(cadArtifactOperationKey({ workspacePath, filePath: sourcePath })).toBe(
      cadArtifactOperationKey({ workspacePath, filePath: modelPath })
    );
  });

  it('serializes a 0.5 @step(out=...) project recipe with its format-folder STEP', async () => {
    const workspacePath = await mkdtemp(join(tmpdir(), 'hardcore-current-operation-key-'));
    temporaryDirectories.push(workspacePath);
    const sourcePath = join(workspacePath, 'src', 'plate.py');
    const modelPath = join(workspacePath, 'STEP', 'plate.step');
    await mkdir(dirname(sourcePath), { recursive: true });
    await writeFile(
      sourcePath,
      [
        'from cadgen import step',
        '',
        '@step(out="../STEP/plate.step")',
        'def plate():',
        '    return None',
      ].join('\n')
    );
    await mkdir(dirname(modelPath), { recursive: true });
    await writeFile(modelPath, 'accepted-step');

    expect(cadArtifactOperationKey({ workspacePath, filePath: sourcePath })).toBe(
      cadArtifactOperationKey({ workspacePath, filePath: modelPath })
    );
    expect(resolveCadArtifactTarget({ workspacePath, filePath: sourcePath })).toEqual({
      success: true,
      workspacePath,
      relativeModelPath: join('STEP', 'plate.step'),
      relativeSourcePath: join('src', 'plate.py'),
    });
  });

  it('prefers persisted model/source provenance over removed render-package metadata', async () => {
    const workspacePath = await mkdtemp(join(tmpdir(), 'hardcore-explicit-cad-link-'));
    temporaryDirectories.push(workspacePath);
    const sourcePath = join(workspacePath, 'src', 'car.py');
    const stepPath = join(workspacePath, 'STEP', 'car.step');
    await mkdir(dirname(sourcePath), { recursive: true });
    await mkdir(dirname(stepPath), { recursive: true });
    await writeFile(sourcePath, 'from cadgen import step\n@step()\ndef car(): ...\n');
    await writeFile(stepPath, 'accepted-step');

    expect(
      resolveCadArtifactTarget({
        workspacePath,
        filePath: stepPath,
        sourcePath: join('src', 'car.py'),
      })
    ).toEqual({
      success: true,
      workspacePath,
      relativeModelPath: join('STEP', 'car.step'),
      relativeSourcePath: join('src', 'car.py'),
    });
  });

  it('does not invent source provenance from an unestablished .step.json file', async () => {
    const workspacePath = await mkdtemp(join(tmpdir(), 'hardcore-untrusted-cad-link-'));
    temporaryDirectories.push(workspacePath);
    const stepPath = join(workspacePath, 'STEP', 'arm.step');
    await mkdir(dirname(stepPath), { recursive: true });
    await writeFile(stepPath, 'accepted-step');
    await writeFile(
      `${stepPath}.json`,
      JSON.stringify({ sourcePath: '../src/arm.py', sourceHash: 'untrusted' })
    );

    expect(resolveCadArtifactTarget({ workspacePath, filePath: stepPath })).toEqual({
      success: true,
      workspacePath,
      relativeModelPath: join('STEP', 'arm.step'),
    });
  });

  it('recognizes aliased multiline custom STEP output declarations', async () => {
    const workspacePath = await mkdtemp(join(tmpdir(), 'hardcore-custom-operation-key-'));
    temporaryDirectories.push(workspacePath);
    const sourcePath = join(workspacePath, 'recipes', 'plate.py');
    const modelPath = join(workspacePath, 'artifacts', 'plate.stp');
    await mkdir(dirname(sourcePath), { recursive: true });
    await writeFile(
      sourcePath,
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
    );

    expect(cadArtifactOperationKey({ workspacePath, filePath: sourcePath })).toBe(
      cadArtifactOperationKey({ workspacePath, filePath: modelPath })
    );
  });

  it('does not borrow out= from a different decorator on the same function', async () => {
    const workspacePath = await mkdtemp(join(tmpdir(), 'hardcore-custom-operation-key-'));
    temporaryDirectories.push(workspacePath);
    const sourcePath = join(workspacePath, 'plate.py');
    await writeFile(
      sourcePath,
      [
        'from cadgen import step',
        '',
        '@step',
        '@metadata(out="elsewhere/plate.step")',
        'def plate():',
        '    return None',
      ].join('\n')
    );

    expect(cadArtifactOperationKey({ workspacePath, filePath: sourcePath })).toBe(
      cadArtifactOperationKey({ workspacePath, filePath: join(workspacePath, 'plate.step') })
    );
  });

  it('opens a canonical STEP using only read-only inspection commands', () => {
    const plan = cadInspectionToolPlan('vendor.step');
    expect(plan).toEqual([
      {
        tool: 'cadgen',
        args: ['step', 'inspect', 'refs', 'vendor.step', '--facts', '--planes', '--positioning'],
      },
      { tool: 'cadgen', args: ['step', 'inspect', 'validate', 'vendor.step'] },
    ]);
    expect(plan.flatMap((command) => command.args)).not.toContain('import');
    expect(plan.flatMap((command) => command.args)).not.toContain('--force');
  });

  it('never executes or imports a linked recipe during open validation', async () => {
    const workspacePath = await mkdtemp(join(tmpdir(), 'hardcore-cad-read-only-'));
    temporaryDirectories.push(workspacePath);
    const sourcePath = join(workspacePath, 'car.py');
    const stepPath = join(workspacePath, 'car.step');
    const commandLog = join(workspacePath, 'commands.log');
    const fakePython = join(workspacePath, 'fake-python');
    await writeFile(
      fakePython,
      '#!/bin/sh\nprintf "%s\\n" "$*" >> "$HARDCORE_CAD_TEST_LOG"\ncase "$*" in\n  *"inspect refs"*) printf "%s\\n" \'{"ok":true,"tokens":[]}\' ;;\n  *) printf "%s\\n" \'{"ok":true}\' ;;\nesac\n'
    );
    await chmod(fakePython, 0o755);
    await writeFile(sourcePath, 'raise RuntimeError("must never run on open")\n');
    await writeFile(stepPath, 'accepted-step');
    process.env.HARDCORE_CAD_PYTHON = fakePython;
    process.env.HARDCORE_CAD_TEST_LOG = commandLog;

    const result = await validateCadModel({ workspacePath, filePath: sourcePath });

    expect(result).toMatchObject({
      success: true,
      artifact: { modelPath: 'car.step', sourcePath: 'car.py' },
    });
    expect(await readFile(stepPath, 'utf8')).toBe('accepted-step');
    const commands = await readFile(commandLog, 'utf8');
    expect(commands).toContain('step inspect refs car.step');
    expect(commands).toContain('step inspect validate car.step');
    expect(commands).not.toContain('import');
    expect(commands).not.toContain('--force');
    expect(commands).not.toContain('car.py');
  });

  it('resolves cadgen CAD references to the accepted STEP artifact', async () => {
    const workspacePath = await mkdtemp(join(tmpdir(), 'hardcore-cad-validation-'));
    temporaryDirectories.push(workspacePath);

    expect(
      cadValidationModelPath(workspacePath, 'emdash-smoke.py', {
        ok: true,
        sourceRef: 'emdash-smoke.py',
        document: 'emdash-smoke',
        kind: 'part',
        outcome: 'built',
        packagePath: '/home/amy/.cache/cadgen/packages/abc-v17',
      })
    ).toBe('emdash-smoke.step');
  });

  it('keeps an unchanged legacy source viewable through its accepted STEP', async () => {
    const workspacePath = await mkdtemp(join(tmpdir(), 'hardcore-cad-validation-'));
    temporaryDirectories.push(workspacePath);
    const source = 'from build123d import Box\n\ndef gen_step():\n    return Box(10, 10, 10)\n';
    const sourceHash = createHash('sha256').update(source).digest('hex');
    await writeFile(join(workspacePath, 'legacy.step.py'), source);
    await writeFile(
      join(workspacePath, 'legacy.step'),
      `ISO-10303-21;\nDESCRIPTIVE_REPRESENTATION_ITEM('cadgen:sourceHash','${sourceHash}');\nEND-ISO-10303-21;\n`
    );

    expect(
      resolveCadArtifactTarget({
        workspacePath,
        filePath: join(workspacePath, 'legacy.step.py'),
      })
    ).toEqual({
      success: true,
      workspacePath,
      relativeModelPath: 'legacy.step',
      relativeSourcePath: 'legacy.step.py',
    });
  });

  it('does not trust a plain sibling when both naming conventions exist without a marker', async () => {
    const workspacePath = await mkdtemp(join(tmpdir(), 'hardcore-cad-validation-'));
    temporaryDirectories.push(workspacePath);
    const legacyPath = join(workspacePath, 'bracket.step.py');
    const plainPath = join(workspacePath, 'bracket.py');
    const stepPath = join(workspacePath, 'bracket.step');
    const packagePath = join(workspacePath, '__cadgen__', 'models', 'bracket.step');
    await mkdir(packagePath, { recursive: true });
    await writeFile(legacyPath, 'LEGACY = 1');
    await writeFile(plainPath, 'WIDTH = 20');
    await writeFile(stepPath, 'step-v1');
    await writeFile(
      join(packagePath, 'assembly.json'),
      JSON.stringify({ sourceKind: 'python', sourcePath: 'bracket.step.py' })
    );
    expect(resolveCadArtifactTarget({ workspacePath, filePath: stepPath })).toEqual({
      success: true,
      workspacePath,
      relativeModelPath: 'bracket.step',
      relativeSourcePath: 'bracket.step.py',
    });
  });

  it('runs generators without reusing same-second Python bytecode', () => {
    const environment = cadToolEnvironment({ PATH: '/usr/bin' });

    expect(environment).toMatchObject({
      PATH: '/usr/bin',
      PYTHONDONTWRITEBYTECODE: '1',
    });
    expect(environment.PYTHONPYCACHEPREFIX).toContain('hardcore-cad-no-bytecode-');
  });
});

async function writeProvenanceRecord(
  workspacePath: string,
  stepPath: string,
  payload: Record<string, unknown>
): Promise<void> {
  const cacheRoot = join(workspacePath, '.cadgen-cache');
  process.env.CADGEN_CACHE_DIR = cacheRoot;
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

function restoreEnvironment(name: string, value: string | undefined): void {
  if (value === undefined) {
    delete process.env[name];
  } else {
    process.env[name] = value;
  }
}
