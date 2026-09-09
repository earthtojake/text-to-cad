import { createTestWire } from '@emdash/wire/testing';
import { describe, expect, it, vi } from 'vitest';
import { searchContract } from '../api';
import type { SearchService } from './search-service';
import { createSearchWireController } from './wire-controller';

describe('search Wire controller', () => {
  it('exposes kind-filtered palette entity search at the domain boundary', async () => {
    const searchEntities = vi.fn(async () => [
      {
        kind: 'task' as const,
        id: 'task-1',
        projectId: 'project-1',
        taskId: null,
        title: 'Theme task',
        subtitle: 'THEME-123',
        score: 0,
      },
    ]);
    const service = {
      searchEntities,
      searchFiles: vi.fn(),
      searchContent: vi.fn(),
    } as unknown as SearchService;
    const wire = createTestWire(searchContract, createSearchWireController(service));
    const input = {
      kind: 'task' as const,
      query: 'tt',
      context: { projectId: 'project-1' },
      limit: 50,
    };

    try {
      await expect(wire.client.searchPaletteEntities(input)).resolves.toEqual([
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
      expect(searchEntities).toHaveBeenCalledWith(input);
    } finally {
      await wire.dispose();
    }
  });
});
