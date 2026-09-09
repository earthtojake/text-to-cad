import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { err, ok } from '@emdash/shared';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { hostPathFromNative, nativePathFromHost } from '@core/primitives/desktop-runtime/api';
import { isRealPathContained, realPathNearestExisting } from '../files/realpath-containment';
import { filesClientScope } from '../files/runtime-client';

const pathOperations = {
  basename: path.basename,
  dirname: path.dirname,
  join: path.join,
  contains(parent: string, child: string): boolean {
    const relative = path.relative(parent, child);
    return relative === '' || (!relative.startsWith('..') && !path.isAbsolute(relative));
  },
};

function makeFiles(root: string) {
  return filesClientScope(
    {
      fs: {
        realPath: async ({ path: target }: { path: Parameters<typeof nativePathFromHost>[0] }) => {
          const filePath = nativePathFromHost(target);
          try {
            return ok({ path: hostPathFromNative(fs.realpathSync(filePath)) });
          } catch {
            return err({ type: 'not-found', path: filePath } as never);
          }
        },
      },
    } as never,
    root
  );
}

describe('realpath containment', () => {
  let root: string;
  let outside: string;

  beforeEach(() => {
    root = fs.mkdtempSync(path.join(os.tmpdir(), 'fh-root-'));
    outside = fs.mkdtempSync(path.join(os.tmpdir(), 'fh-out-'));
  });

  afterEach(() => {
    fs.rmSync(root, { recursive: true, force: true });
    fs.rmSync(outside, { recursive: true, force: true });
  });

  it('treats a real path inside the root as contained', async () => {
    fs.mkdirSync(path.join(root, 'inside'));
    const result = await isRealPathContained(
      makeFiles(root),
      pathOperations,
      root,
      path.join(root, 'inside', 'file.txt')
    );
    expect(result.success && result.data).toBe(true);
  });

  it('rejects a destination whose parent symlink escapes the root', async () => {
    fs.symlinkSync(outside, path.join(root, 'escape'), 'dir');
    const result = await isRealPathContained(
      makeFiles(root),
      pathOperations,
      root,
      path.join(root, 'escape', 'file.txt')
    );
    expect(result.success && result.data).toBe(false);
  });

  it('rejects an existing symlink that resolves outside the root', async () => {
    fs.symlinkSync(outside, path.join(root, 'escape'), 'dir');
    const result = await isRealPathContained(
      makeFiles(root),
      pathOperations,
      root,
      path.join(root, 'escape'),
      { candidateMustExist: true }
    );
    expect(result.success && result.data).toBe(false);
  });

  it('resolves the nearest existing ancestor for a non-existent path', async () => {
    fs.mkdirSync(path.join(root, 'a'));
    const realRoot = fs.realpathSync(root);
    const resolved = await realPathNearestExisting(
      makeFiles(root),
      pathOperations,
      path.join(root, 'a', 'b', 'c.txt')
    );
    expect(resolved.success && resolved.data).toBe(path.join(realRoot, 'a', 'b', 'c.txt'));
  });
});
