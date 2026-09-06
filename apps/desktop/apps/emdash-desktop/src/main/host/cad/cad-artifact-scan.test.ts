import { mkdir, mkdtemp, rm, utimes, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { isRevealableCadArtifact, listCadArtifacts } from './cad-artifact-scan';

const temporaryDirectories: string[] = [];

afterEach(async () => {
  await Promise.all(temporaryDirectories.splice(0).map((path) => rm(path, { recursive: true })));
});

async function workspace(): Promise<string> {
  const path = await mkdtemp(join(tmpdir(), 'hardcore-cad-scan-'));
  temporaryDirectories.push(path);
  return path;
}

describe('isRevealableCadArtifact', () => {
  it('accepts viewer formats and rejects recipe sources', () => {
    expect(isRevealableCadArtifact('models/plate.STEP')).toBe(true);
    expect(isRevealableCadArtifact('exports/plate.glb')).toBe(true);
    expect(isRevealableCadArtifact('models/plate.py')).toBe(false);
    expect(isRevealableCadArtifact('models/plate.step.py')).toBe(false);
  });
});

describe('listCadArtifacts', () => {
  it('returns workspace-relative model artifacts written since the turn started', async () => {
    const root = await workspace();
    await mkdir(join(root, 'models', 'parts'), { recursive: true });
    await mkdir(join(root, 'node_modules', 'pkg'), { recursive: true });
    await writeFile(join(root, 'models', 'parts', 'bracket.step'), 'ISO-10303-21;');
    await writeFile(join(root, 'models', 'empty.step'), '');
    await writeFile(join(root, 'models', 'bracket.py'), 'from cadgen import step');
    await writeFile(join(root, 'node_modules', 'pkg', 'fixture.step'), 'ISO-10303-21;');
    const old = join(root, 'legacy.step');
    await writeFile(old, 'ISO-10303-21;');
    const past = new Date(Date.now() - 60 * 60 * 1000);
    await utimes(old, past, past);

    const result = await listCadArtifacts({ workspacePath: root, sinceMs: Date.now() - 5_000 });

    expect(result.success).toBe(true);
    if (!result.success) return;
    expect(result.truncated).toBe(false);
    expect(result.artifacts.map(({ path }) => path)).toEqual(['models/parts/bracket.step']);
  });

  it('reports a missing workspace instead of throwing', async () => {
    const result = await listCadArtifacts({
      workspacePath: '/nonexistent/hardcore-scan',
      sinceMs: 0,
    });
    expect(result).toMatchObject({ success: false });
  });
});
