import { openFixture } from '@tooling/utils/db';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createSearchService } from '@core/features/search/node/search-service';
import { projects, tasks } from '@core/services/app-db/node/schema';
import { initializeDatabase } from '@main/db/initialize';

describe('palette search index rebuild', () => {
  let fixture: Awaited<ReturnType<typeof openFixture>>;

  afterEach(() => {
    fixture?.close();
  });

  it('rebuilds the derived index so legacy command rows cannot survive', async () => {
    fixture = await openFixture('empty');
    fixture.db.insert(projects).values({ id: 'project-1', name: 'Palette project' }).run();
    fixture.db
      .insert(tasks)
      .values({
        id: 'task-1',
        projectId: 'project-1',
        name: 'Theme task',
        status: 'running',
        linkedIssue: {
          provider: 'linear',
          url: 'https://linear.app/example/issue/THEME-123',
          title: 'Restore theme switching',
          identifier: 'THEME-123',
        },
      })
      .run();
    fixture.sqlite
      .prepare(
        `INSERT INTO search_index(item_type, item_id, project_id, task_id, title, keywords)
         VALUES ('command', 'app.toggleTheme', NULL, NULL, 'Toggle Theme', 'appearance')`
      )
      .run();
    fixture.sqlite
      .prepare(
        `INSERT OR REPLACE INTO kv (key, value, updated_at)
         VALUES ('fts_version', '3', unixepoch())`
      )
      .run();

    await initializeDatabase(fixture.sqlite);

    expect(fixture.sqlite.prepare(`SELECT value FROM kv WHERE key = 'fts_version'`).get()).toEqual({
      value: '4',
    });
    expect(fixture.sqlite.prepare(`SELECT item_type FROM search_index`).all()).toEqual([]);

    const service = createSearchService({
      db: fixture.db,
      sqlite: fixture.sqlite,
      acquireWorkspaceRuntime: async () => null,
      searchFileSearchRoot: async () => [],
      getSearchExclusions: async () => [],
      tasks: { on: vi.fn() } as never,
    });
    service.initialize();

    expect(
      fixture.sqlite
        .prepare(`SELECT item_type, keywords FROM search_index WHERE item_id = 'task-1'`)
        .get()
    ).toEqual({
      item_type: 'task',
      keywords: 'THEME-123 Restore theme switching',
    });
    await expect(
      service.searchEntities({
        kind: 'task',
        query: 'tt',
        context: { projectId: 'project-1' },
      })
    ).resolves.toMatchObject([
      {
        kind: 'task',
        id: 'task-1',
        title: 'Theme task',
        subtitle: 'THEME-123 Restore theme switching',
      },
    ]);
  });
});
