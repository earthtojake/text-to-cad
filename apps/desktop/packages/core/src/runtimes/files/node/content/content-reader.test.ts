import { mkdtemp, realpath, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { RootPathPolicy } from '#runtimes/files/node/fs/path-policy';
import { relativePath } from '#runtimes/files/node/testing/paths';
import { ContentReader } from './content-reader';

const roots: string[] = [];

afterEach(async () => {
  await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true })));
});

describe('ContentReader', () => {
  it('classifies EOL, over-limit, binary content, and unavailable files', async () => {
    const root = await makeRoot();
    await writeFile(path.join(root, 'text.txt'), 'a\r\nb\r\n');
    await writeFile(path.join(root, 'binary.bin'), new Uint8Array([1, 0, 2]));
    await writeFile(path.join(root, 'invalid-utf8.bin'), new Uint8Array([0xc3, 0x28]));
    const paths = new RootPathPolicy(root);

    await expect(new ContentReader(paths, 4).read(relativePath('text.txt'))).resolves.toEqual({
      kind: 'too-large',
      path: 'text.txt',
      byteSize: 6,
      limit: 4,
    });
    await expect(new ContentReader(paths).read(relativePath('text.txt'))).resolves.toMatchObject({
      kind: 'text',
      content: 'a\r\nb\r\n',
      eol: 'crlf',
      byteSize: 6,
    });
    await expect(new ContentReader(paths).read(relativePath('binary.bin'))).resolves.toMatchObject({
      kind: 'binary',
      byteSize: 3,
    });
    await expect(
      new ContentReader(paths).read(relativePath('invalid-utf8.bin'))
    ).resolves.toMatchObject({ kind: 'binary', byteSize: 2 });
    await expect(new ContentReader(paths).read(relativePath('missing.txt'))).resolves.toMatchObject(
      {
        kind: 'unavailable',
        code: 'not-found',
      }
    );
  });
});

async function makeRoot(): Promise<string> {
  const root = await realpath(await mkdtemp(path.join(tmpdir(), 'emdash-content-reader-')));
  roots.push(root);
  return root;
}
