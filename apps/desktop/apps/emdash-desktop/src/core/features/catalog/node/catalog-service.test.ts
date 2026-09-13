import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

let userDataDir: string;

vi.mock('electron', () => ({
  app: {
    getPath: () => userDataDir,
  },
}));

vi.mock('@emdash/shared/logger', () => ({
  log: { error: vi.fn(), warn: vi.fn(), info: vi.fn() },
}));

describe('CatalogService', () => {
  beforeEach(async () => {
    userDataDir = await fs.promises.mkdtemp(path.join(os.tmpdir(), 'emdash-catalog-'));
  });

  afterEach(async () => {
    await fs.promises.rm(userDataDir, { recursive: true, force: true });
    vi.restoreAllMocks();
  });

  it('loads bundled skills as raw catalog entries without installed state merging', async () => {
    const { CatalogService } = await import('./catalog-service');
    const service = new CatalogService();

    const catalog = await service.getSkillsCatalog();

    expect(catalog.skills.length).toBeGreaterThan(0);
    expect(catalog.skills.every((skill) => skill.installed === false)).toBe(true);
  });

  it('resolves a cached skill to an agent-config install payload', async () => {
    const catalogDir = path.join(userDataDir, 'catalog');
    await fs.promises.mkdir(catalogDir, { recursive: true });
    await fs.promises.writeFile(
      path.join(catalogDir, 'skills-catalog-index.json'),
      JSON.stringify({
        version: 2,
        lastUpdated: '2026-01-01T00:00:00.000Z',
        skills: [
          {
            id: 'cached-skill',
            displayName: 'Cached Skill',
            description: 'Cached description',
            source: 'openai',
            frontmatter: { name: 'cached-skill', description: 'Cached description' },
            installed: false,
            skillMdContent:
              '---\nname: cached-skill\ndescription: Cached description\n---\nUse it.\n',
          },
        ],
      })
    );
    const { CatalogService } = await import('./catalog-service');
    const service = new CatalogService();

    const payload = await service.resolveSkillInstall('cached-skill');

    expect(payload).toMatchObject({
      id: 'cached-skill',
      installId: 'cached-skill',
      source: 'openai',
    });
    expect(payload.skillMdContent).toContain('---');
  });

  it('returns the curated in-source MCP catalog by default', async () => {
    const { CatalogService } = await import('./catalog-service');
    const service = new CatalogService();

    const catalog = await service.getMcpCatalog();

    expect(catalog.length).toBeGreaterThan(0);
    expect(catalog.find((entry) => entry.key === 'playwright')).toMatchObject({
      name: 'Playwright',
      defaultConfig: { command: 'npx' },
    });
  });
});
