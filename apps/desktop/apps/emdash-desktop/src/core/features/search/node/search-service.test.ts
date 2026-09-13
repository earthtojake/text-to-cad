import { ok } from '@emdash/shared';
import { deferred } from '@emdash/shared/testing';
import { createController } from '@emdash/wire/rpc';
import { createTestWire } from '@emdash/wire/testing';
import Database from 'better-sqlite3';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { hostPathFromNative } from '@core/primitives/desktop-runtime/api';
import { portablePath } from '@core/primitives/desktop-runtime/api';
import { contentSearchRuntimeContract } from '../api';
import { createSearchService } from './search-service';

const mocks = vi.hoisted(() => ({
  fileSearch: vi.fn(),
  prepare: vi.fn(),
  workspaceGet: vi.fn(),
  getSearchExclusions: vi.fn(),
  warn: vi.fn(),
}));

vi.mock(import('@emdash/shared/logger'), async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...actual,
    log: { ...actual.log, info: vi.fn(), warn: mocks.warn },
  };
});

vi.mock('@core/features/conversations/api/node/conversation-events', () => ({
  conversationEvents: { on: vi.fn() },
}));

vi.mock('@core/features/projects/api/node/project-events', () => ({
  projectEvents: { on: vi.fn() },
}));

describe('SearchService runtime file search', () => {
  const root = hostPathFromNative('/repo');
  const searchService = createSearchService({
    db: {} as never,
    sqlite: { prepare: mocks.prepare } as never,
    acquireWorkspaceRuntime: mocks.workspaceGet,
    searchFileSearchRoot: mocks.fileSearch,
    getSearchExclusions: mocks.getSearchExclusions,
    tasks: { on: vi.fn() } as never,
  });

  beforeEach(() => {
    vi.clearAllMocks();
    mocks.workspaceGet.mockReturnValue({
      client: { fileSearch: { searchPaths: vi.fn() } },
      files: { root },
    });
    mocks.fileSearch.mockResolvedValue([{ path: '/repo/src/index.ts', filename: 'index.ts' }]);
    mocks.getSearchExclusions.mockResolvedValue(['dist']);
  });

  it('delegates path search to the resolved workspace runtime', async () => {
    await expect(searchService.searchFiles('workspace-1', 'index', 25)).resolves.toEqual([
      { path: '/repo/src/index.ts', filename: 'index.ts' },
    ]);
    expect(mocks.fileSearch).toHaveBeenCalledWith(
      expect.objectContaining({ searchPaths: expect.any(Function) }),
      root,
      'index',
      25
    );
  });

  it('relays progressive content search through the resolved workspace runtime', async () => {
    const progressGate = deferred<void>();
    let didStartSearch = false;
    const files = [
      {
        path: portablePath('src/index.ts'),
        matches: [
          {
            lineNumber: 4,
            previewText: 'const test = true;',
            locations: [
              {
                sourceRange: { startColumn: 7, endColumn: 11 },
                previewRange: { startColumn: 7, endColumn: 11 },
              },
            ],
          },
        ],
      },
    ];
    const upstream = createTestWire(
      contentSearchRuntimeContract,
      createController(contentSearchRuntimeContract, {
        searchContent: {
          run: async (input, context) => {
            didStartSearch = true;
            expect(input).toEqual({ root, query: 'test', limit: 25, exclusions: ['dist'] });
            await progressGate.promise;
            context.progress({ files });
            return ok({ files, complete: true });
          },
        },
      })
    );
    mocks.workspaceGet.mockResolvedValue({
      client: { fileSearch: upstream.client },
      files: { root },
    });
    const progress: unknown[] = [];

    try {
      const result = searchService.searchContent(
        { workspaceId: 'workspace-1', query: 'test', limit: 25 },
        {
          jobId: 'desktop-search-1',
          signal: new AbortController().signal,
          progress: (update) => progress.push(update),
        }
      );
      await vi.waitFor(() => expect(didStartSearch).toBe(true));
      progressGate.resolve();

      await expect(result).resolves.toEqual(ok({ files, complete: true }));
      expect(progress).toEqual([{ files }]);
    } finally {
      await upstream.dispose();
    }
  });
});

describe('SearchService palette entity search', () => {
  it('returns kind-filtered candidates for one-character queries', async () => {
    const sqlite = new Database(':memory:');
    sqlite.exec(`
      CREATE VIRTUAL TABLE search_index USING fts5(
        item_type,
        item_id UNINDEXED,
        project_id UNINDEXED,
        task_id UNINDEXED,
        title,
        keywords,
        tokenize = 'trigram case_sensitive 0'
      );
      INSERT INTO search_index VALUES
        ('task', 'task-1', 'project-1', NULL, 'Theme task', 'THEME-123'),
        ('project', 'project-1', NULL, NULL, 'Theme project', '/repo/theme'),
        ('conversation', 'conversation-1', 'project-1', 'task-1', 'Theme chat', '');
    `);
    const service = createSearchService({
      db: {} as never,
      sqlite,
      acquireWorkspaceRuntime: mocks.workspaceGet,
      searchFileSearchRoot: mocks.fileSearch,
      getSearchExclusions: mocks.getSearchExclusions,
      tasks: { on: vi.fn() } as never,
    });

    try {
      await expect(
        service.searchEntities({
          kind: 'task',
          query: 't',
          context: { projectId: 'project-1' },
        })
      ).resolves.toEqual([
        {
          kind: 'task',
          id: 'task-1',
          projectId: 'project-1',
          taskId: null,
          title: 'Theme task',
          subtitle: 'THEME-123',
          score: 0,
        },
      ]);
      await expect(
        service.searchEntities({
          kind: 'task',
          query: 'tt',
          context: { projectId: 'project-1' },
        })
      ).resolves.toEqual([
        {
          kind: 'task',
          id: 'task-1',
          projectId: 'project-1',
          taskId: null,
          title: 'Theme task',
          subtitle: 'THEME-123',
          score: 0,
        },
      ]);
      await expect(
        service.searchEntities({
          kind: 'project',
          query: 't',
          context: { projectId: 'project-1' },
        })
      ).resolves.toEqual([
        {
          kind: 'project',
          id: 'project-1',
          projectId: null,
          taskId: null,
          title: 'Theme project',
          subtitle: '/repo/theme',
          score: 0,
        },
      ]);
      await expect(
        service.searchEntities({
          kind: 'conversation',
          query: 't',
          context: { projectId: 'project-1', taskId: 'task-1' },
        })
      ).resolves.toEqual([
        {
          kind: 'conversation',
          id: 'conversation-1',
          projectId: 'project-1',
          taskId: 'task-1',
          title: 'Theme chat',
          subtitle: '',
          score: 0,
        },
      ]);
      await expect(
        service.searchEntities({
          kind: 'conversation',
          query: 't',
          context: { taskId: 'other-task' },
        })
      ).resolves.toEqual([]);
    } finally {
      sqlite.close();
    }
  });
});
