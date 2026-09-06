import { spawnSync } from 'node:child_process';
import { chmod, mkdtemp, mkdir, realpath, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import {
  CONTENT_SEARCH_MAX_PREVIEW_LENGTH,
  type ContentSearchProgress,
} from '#runtimes/file-search/api';
import { DefaultFileSearchExclusions } from '../../exclusions';
import { hostPath as absolute } from '../../testing/paths';
import { RipgrepContentSearcher } from './ripgrep-content-searcher';

const hasRipgrep = spawnSync('rg', ['--version'], { stdio: 'ignore' }).status === 0;
const temporaryDirectories: string[] = [];

afterEach(async () => {
  await Promise.all(
    temporaryDirectories
      .splice(0)
      .map((directory) => rm(directory, { recursive: true, force: true }))
  );
});

describe('RipgrepContentSearcher', () => {
  it.skipIf(!hasRipgrep)(
    'groups literal matches by file and line, excludes generated trees, and enforces limits',
    async () => {
      const rootPath = await createRoot();
      await mkdir(path.join(rootPath, 'src'));
      await mkdir(path.join(rootPath, 'node_modules', 'pkg'), { recursive: true });
      await writeFile(path.join(rootPath, 'src', 'index.ts'), 'const 😀 VALUE = 1;\nVALUE VALUE\n');
      await writeFile(path.join(rootPath, 'node_modules', 'pkg', 'hidden.ts'), 'VALUE\n');
      const progress: ContentSearchProgress[] = [];
      const searcher = createSearcher();

      const result = await searcher.search(
        { root: absolute(rootPath), rootPath, searchPath: rootPath, query: 'value', limit: 2 },
        {
          signal: new AbortController().signal,
          onProgress: (update) => progress.push(update),
        }
      );

      expect(result).toEqual({
        success: true,
        data: {
          files: [
            {
              path: 'src/index.ts',
              matches: [
                {
                  lineNumber: 1,
                  previewText: 'const 😀 VALUE = 1;',
                  locations: [
                    {
                      sourceRange: { startColumn: 10, endColumn: 15 },
                      previewRange: { startColumn: 10, endColumn: 15 },
                    },
                  ],
                },
                {
                  lineNumber: 2,
                  previewText: 'VALUE VALUE',
                  locations: [
                    {
                      sourceRange: { startColumn: 1, endColumn: 6 },
                      previewRange: { startColumn: 1, endColumn: 6 },
                    },
                  ],
                },
              ],
            },
          ],
          complete: false,
        },
      });
      expect(progress).toHaveLength(1);
      expect(progress[0].files[0].path).toBe('src/index.ts');
    }
  );

  it.skipIf(!hasRipgrep)('applies per-search exclusions to ripgrep', async () => {
    const rootPath = await createRoot();
    await mkdir(path.join(rootPath, 'generated'));
    await writeFile(path.join(rootPath, 'keep.ts'), 'VALUE\n');
    await writeFile(path.join(rootPath, 'generated', 'client.ts'), 'VALUE\n');

    const result = await createSearcher().search(
      {
        root: absolute(rootPath),
        rootPath,
        searchPath: rootPath,
        query: 'value',
        limit: 1_000,
        exclusions: ['generated'],
      },
      { signal: new AbortController().signal, onProgress: () => {} }
    );

    expect(result.success).toBe(true);
    if (!result.success) return;
    expect(result.data.files.map((file) => file.path)).toEqual(['keep.ts']);
  });

  it.skipIf(!hasRipgrep)('treats ripgrep exit one as a successful empty search', async () => {
    const rootPath = await createRoot();
    await writeFile(path.join(rootPath, 'file.ts'), 'nothing here\n');

    await expect(
      createSearcher().search(
        {
          root: absolute(rootPath),
          rootPath,
          searchPath: rootPath,
          query: 'not-present',
          limit: 1_000,
        },
        { signal: new AbortController().signal, onProgress: () => {} }
      )
    ).resolves.toEqual({ success: true, data: { files: [], complete: true } });
  });

  it('reports a missing ripgrep executable as an unavailable search engine', async () => {
    const rootPath = await createRoot();
    const result = await createSearcher({
      executable: path.join(rootPath, 'missing-ripgrep'),
    }).search(
      { root: absolute(rootPath), rootPath, searchPath: rootPath, query: 'term', limit: 1_000 },
      { signal: new AbortController().signal, onProgress: () => {} }
    );

    expect(result).toMatchObject({
      success: false,
      error: { type: 'content-search-unavailable' },
    });
  });

  it('throws cancellation instead of converting it to an I/O Result', async () => {
    const rootPath = await createRoot();
    const cancellation = new Error('cancel content search');
    const controller = new AbortController();
    controller.abort(cancellation);

    await expect(
      createSearcher({ executable: process.execPath }).search(
        { root: absolute(rootPath), rootPath, searchPath: rootPath, query: 'term', limit: 1_000 },
        { signal: controller.signal, onProgress: () => {} }
      )
    ).rejects.toBe(cancellation);
  });

  it.skipIf(!hasRipgrep)(
    'ignores an incomplete JSON record after mid-stream cancellation',
    async () => {
      const rootPath = await createRoot();
      await writeFile(
        path.join(rootPath, 'large.txt'),
        Array.from({ length: 500 }, () => `VALUE ${'x'.repeat(8_000)}`).join('\n')
      );
      const cancellation = new Error('cancel content search mid-stream');

      for (let attempt = 0; attempt < 10; attempt += 1) {
        const controller = new AbortController();
        await expect(
          createSearcher().search(
            {
              root: absolute(rootPath),
              rootPath,
              searchPath: rootPath,
              query: 'VALUE',
              limit: 1_000,
            },
            {
              signal: controller.signal,
              onProgress: () => controller.abort(cancellation),
            }
          )
        ).rejects.toBe(cancellation);
      }
    }
  );

  it.skipIf(!hasRipgrep)(
    'ignores an incomplete JSON record after reaching the result limit',
    async () => {
      const rootPath = await createRoot();
      await writeFile(
        path.join(rootPath, 'many-large-lines.txt'),
        Array.from({ length: 500 }, () => `VALUE ${'x'.repeat(8_000)}`).join('\n')
      );

      for (let attempt = 0; attempt < 10; attempt += 1) {
        await expect(
          createSearcher().search(
            { root: absolute(rootPath), rootPath, searchPath: rootPath, query: 'VALUE', limit: 1 },
            { signal: new AbortController().signal, onProgress: () => {} }
          )
        ).resolves.toMatchObject({ success: true, data: { complete: false } });
      }
    }
  );

  it.skipIf(!hasRipgrep)(
    'compacts every distant match from a 210K-character source line',
    async () => {
      const rootPath = await createRoot();
      const offsets = [10_415, 111_692, 138_233, 162_433, 190_314, 190_636];
      const line = lineWithMatches(210_474, offsets, 'LoL');
      await writeFile(path.join(rootPath, 'generated-icon.ts'), `${line}\n`);

      const result = await createSearcher().search(
        { root: absolute(rootPath), rootPath, searchPath: rootPath, query: 'lol', limit: 1_000 },
        { signal: new AbortController().signal, onProgress: () => {} }
      );

      expect(result.success).toBe(true);
      if (!result.success) return;
      expect(result.data.complete).toBe(true);
      const match = result.data.files[0]?.matches[0];
      expect(match?.previewText.length).toBeLessThanOrEqual(CONTENT_SEARCH_MAX_PREVIEW_LENGTH);
      expect(match?.locations).toHaveLength(offsets.length);
      expect(match?.locations.map(({ sourceRange }) => sourceRange)).toEqual(
        offsets.map((offset) => ({ startColumn: offset + 1, endColumn: offset + 4 }))
      );
      for (const location of match?.locations ?? []) {
        expect(
          match?.previewText.slice(
            location.previewRange.startColumn - 1,
            location.previewRange.endColumn - 1
          )
        ).toBe('LoL');
      }
    }
  );

  it.skipIf(!hasRipgrep)('keeps CR-only files within the single-line result contract', async () => {
    const rootPath = await createRoot();
    await writeFile(path.join(rootPath, 'old-mac.txt'), 'alpha\rbeta VALUE\rgamma');

    const result = await createSearcher().search(
      { root: absolute(rootPath), rootPath, searchPath: rootPath, query: 'value', limit: 1_000 },
      { signal: new AbortController().signal, onProgress: () => {} }
    );

    expect(result).toMatchObject({
      success: true,
      data: {
        files: [
          {
            path: 'old-mac.txt',
            matches: [
              {
                lineNumber: 1,
                previewText: 'alpha␍beta VALUE␍gamma',
                locations: [
                  {
                    sourceRange: { startColumn: 12, endColumn: 17 },
                    previewRange: { startColumn: 12, endColumn: 17 },
                  },
                ],
              },
            ],
          },
        ],
        complete: true,
      },
    });
  });

  it.skipIf(!hasRipgrep)(
    'omits an oversized raw record, recovers, and reports an incomplete result',
    async () => {
      const rootPath = await createRoot();
      await writeFile(path.join(rootPath, 'a-huge.txt'), `VALUE ${'x'.repeat(20_000)}\n`);
      await writeFile(path.join(rootPath, 'z-small.txt'), 'VALUE\n');

      const result = await createSearcher({ maxRecordBytes: 512 }).search(
        { root: absolute(rootPath), rootPath, searchPath: rootPath, query: 'VALUE', limit: 1_000 },
        { signal: new AbortController().signal, onProgress: () => {} }
      );

      expect(result).toMatchObject({
        success: true,
        data: {
          files: [{ path: 'z-small.txt' }],
          complete: false,
        },
      });
    }
  );

  it.skipIf(!hasRipgrep)(
    'returns a deterministic partial line when all distant occurrences cannot fit',
    async () => {
      const rootPath = await createRoot();
      const line = Array.from({ length: 1_000 }, () => `VALUE${'x'.repeat(100)}`).join('');
      await writeFile(path.join(rootPath, 'many-distant-matches.txt'), `${line}\n`);

      const result = await createSearcher().search(
        { root: absolute(rootPath), rootPath, searchPath: rootPath, query: 'VALUE', limit: 1_000 },
        { signal: new AbortController().signal, onProgress: () => {} }
      );

      expect(result.success).toBe(true);
      if (!result.success) return;
      expect(result.data).toMatchObject({
        complete: false,
      });
      const match = result.data.files[0]?.matches[0];
      expect(match?.locations.length).toBeGreaterThan(0);
      expect(match?.locations.length).toBeLessThan(1_000);
      expect(match?.locations.map(({ sourceRange }) => sourceRange.startColumn)).toEqual(
        Array.from({ length: match?.locations.length ?? 0 }, (_, index) => index * 105 + 1)
      );
    }
  );

  it.skipIf(!hasRipgrep)('searches hidden files and ignores user ripgrep config', async () => {
    const rootPath = await createRoot();
    const configPath = path.join(rootPath, 'ripgrep-config');
    await writeFile(configPath, '--glob=!*.ts\n');
    await writeFile(path.join(rootPath, '.hidden.ts'), 'VALUE\n');

    const result = await createSearcher({
      env: async () => ({ ...process.env, RIPGREP_CONFIG_PATH: configPath }),
    }).search(
      { root: absolute(rootPath), rootPath, searchPath: rootPath, query: 'VALUE', limit: 1_000 },
      { signal: new AbortController().signal, onProgress: () => {} }
    );

    expect(result).toMatchObject({
      success: true,
      data: { files: [{ path: '.hidden.ts' }], complete: true },
    });
  });

  it.skipIf(!hasRipgrep || process.platform === 'win32' || process.getuid?.() === 0)(
    'retains readable matches when ripgrep also encounters an unreadable directory',
    async () => {
      const rootPath = await createRoot();
      const unreadablePath = path.join(rootPath, 'z-unreadable');
      await writeFile(path.join(rootPath, 'a-readable.txt'), 'VALUE\n');
      await mkdir(unreadablePath);
      await writeFile(path.join(unreadablePath, 'secret.txt'), 'VALUE\n');
      await chmod(unreadablePath, 0o000);

      try {
        const result = await createSearcher().search(
          {
            root: absolute(rootPath),
            rootPath,
            searchPath: rootPath,
            query: 'VALUE',
            limit: 1_000,
          },
          { signal: new AbortController().signal, onProgress: () => {} }
        );

        expect(result).toMatchObject({
          success: true,
          data: {
            files: [{ path: 'a-readable.txt' }],
            complete: false,
          },
        });
      } finally {
        await chmod(unreadablePath, 0o700);
      }
    }
  );

  it.skipIf(!hasRipgrep)('throws unexpected progress observer failures', async () => {
    const rootPath = await createRoot();
    await writeFile(
      path.join(rootPath, 'many.txt'),
      Array.from({ length: 60 }, () => 'VALUE').join('\n')
    );
    const bug = new Error('progress observer bug');

    await expect(
      createSearcher().search(
        { root: absolute(rootPath), rootPath, searchPath: rootPath, query: 'VALUE', limit: 1_000 },
        {
          signal: new AbortController().signal,
          onProgress: () => {
            throw bug;
          },
        }
      )
    ).rejects.toBe(bug);
  });
});

async function createRoot(): Promise<string> {
  const directory = await mkdtemp(path.join(os.tmpdir(), 'emdash-content-search-'));
  temporaryDirectories.push(directory);
  return realpath(directory);
}

function lineWithMatches(length: number, offsets: readonly number[], match: string): string {
  let line = '';
  let cursor = 0;
  for (const offset of offsets) {
    line += 'x'.repeat(offset - cursor) + match;
    cursor = offset + match.length;
  }
  return line + 'x'.repeat(length - cursor);
}

function createSearcher(
  options: Omit<ConstructorParameters<typeof RipgrepContentSearcher>[0], 'exclusions'> = {}
): RipgrepContentSearcher {
  return new RipgrepContentSearcher({
    ...options,
    exclusions: new DefaultFileSearchExclusions({ caseSensitive: true }),
  });
}
