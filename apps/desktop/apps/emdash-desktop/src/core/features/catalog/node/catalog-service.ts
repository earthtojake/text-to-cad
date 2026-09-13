import { createHash } from 'node:crypto';
import * as fs from 'node:fs';
import * as https from 'node:https';
import * as path from 'node:path';
import type { McpCatalogEntry, RawServerEntry } from '@emdash/core/primitives/mcp/api';
import {
  generateSkillMd,
  isSafeSkillShPath,
  normalizeSkillShPath,
  normalizeSkillShSkillId,
  parseFrontmatter,
  type CatalogIndex,
  type CatalogSkill,
} from '@emdash/core/primitives/skills/api';
import { log } from '@emdash/shared/logger';
import { app } from 'electron';
import { catalogData } from '@core/primitives/mcp/api';
import bundledCatalog from './bundled-catalog.json';

export type CatalogServiceError = {
  type: 'io' | 'network' | 'not-found' | 'invalid-state';
  message: string;
  statusCode?: number;
};

export type McpCatalogOptions = {
  registryBaseUrl?: string;
  search?: string;
  featuredOnly?: boolean;
};

const DEFAULT_MCP_REGISTRY_BASE_URL = 'https://registry.modelcontextprotocol.io';
const MCP_REGISTRY_CACHE_TTL_MS = 60 * 60 * 1000;
const CATALOG_VERSION = 2;
const MAX_REDIRECTS = 5;
const MAX_HTTP_RESPONSE_BYTES = 2 * 1024 * 1024;
const SKILLSH_SEARCH_CACHE_TTL_MS = 5 * 60 * 1000;
const SKILLSH_SKILL_CACHE_MAX_ENTRIES = 200;

class HttpStatusError extends Error {
  constructor(
    public readonly statusCode: number,
    url: string
  ) {
    super(`HTTP ${statusCode} for ${url}`);
    this.name = 'HttpStatusError';
  }
}

type RegistryServer = {
  name?: unknown;
  title?: unknown;
  description?: unknown;
  website_url?: unknown;
  source?: unknown;
  repository?: unknown;
  remotes?: unknown;
  packages?: unknown;
  _meta?: unknown;
};

type RegistryCacheEntry = {
  expiresAt: number;
  servers: RegistryServer[];
};

function httpsGet(
  url: string,
  options: { maxBytes?: number; redirectCount?: number } = {}
): Promise<string> {
  return new Promise((resolve, reject) => {
    const redirectCount = options.redirectCount ?? 0;
    if (redirectCount >= MAX_REDIRECTS) {
      reject(new Error(`Too many redirects (>${MAX_REDIRECTS}) for ${url}`));
      return;
    }
    const req = https.get(
      url,
      { headers: { 'User-Agent': 'hardcore-catalog', Accept: 'application/json' } },
      (res) => {
        if (res.statusCode === 301 || res.statusCode === 302) {
          const location = res.headers.location;
          if (location) {
            const resolved = new URL(location, url).href;
            httpsGet(resolved, { ...options, redirectCount: redirectCount + 1 }).then(
              resolve,
              reject
            );
            return;
          }
        }
        if (res.statusCode && res.statusCode >= 400) {
          reject(new HttpStatusError(res.statusCode, url));
          return;
        }
        let data = '';
        let bytes = 0;
        let destroyed = false;
        const maxBytes = options.maxBytes ?? MAX_HTTP_RESPONSE_BYTES;
        res.on('data', (chunk: Buffer | string) => {
          bytes += Buffer.byteLength(chunk);
          if (bytes > maxBytes) {
            destroyed = true;
            req.destroy(new Error(`Response too large for ${url}`));
            return;
          }
          data += chunk;
        });
        res.on('end', () => {
          if (!destroyed) resolve(data);
        });
        res.on('error', reject);
      }
    );
    req.on('error', reject);
    req.setTimeout(15000, () => {
      req.destroy(new Error('Request timed out'));
    });
  });
}

export class CatalogService {
  private catalogCache: CatalogIndex | null = null;
  private skillShSearchCache = new Map<string, { expiresAt: number; skills: CatalogSkill[] }>();
  private skillShSkillCache = new Map<string, CatalogSkill>();
  private mcpRegistryCache = new Map<string, RegistryCacheEntry>();

  async getSkillsCatalog(): Promise<CatalogIndex> {
    if (this.catalogCache) return this.catalogCache;

    try {
      const data = await fs.promises.readFile(this.skillsCatalogCachePath(), 'utf-8');
      const diskCache = normalizeCatalogIndex(JSON.parse(data) as CatalogIndex);
      if (diskCache.version >= CATALOG_VERSION) {
        this.catalogCache = diskCache;
        return diskCache;
      }
    } catch {
      // No app-scoped cache yet; fall back to the bundled catalog.
    }

    const bundled = this.loadBundledCatalog();
    this.catalogCache = bundled;
    return bundled;
  }

  async refreshSkillsCatalog(): Promise<CatalogIndex> {
    try {
      const [openaiSkills, anthropicSkills] = await Promise.allSettled([
        this.fetchOpenAICatalog(),
        this.fetchAnthropicCatalog(),
      ]);

      const allSkills: CatalogSkill[] = [];
      if (openaiSkills.status === 'fulfilled') allSkills.push(...openaiSkills.value);
      if (anthropicSkills.status === 'fulfilled') allSkills.push(...anthropicSkills.value);

      const seen = new Set<string>();
      const skills = allSkills.filter((skill) => {
        if (seen.has(skill.id)) return false;
        seen.add(skill.id);
        return true;
      });
      if (skills.length === 0) return this.getSkillsCatalog();

      const catalog: CatalogIndex = {
        version: CATALOG_VERSION,
        lastUpdated: new Date().toISOString(),
        skills,
      };
      this.catalogCache = catalog;
      await fs.promises.mkdir(this.catalogCacheDir(), { recursive: true });
      await fs.promises.writeFile(this.skillsCatalogCachePath(), JSON.stringify(catalog, null, 2));
      return catalog;
    } catch (error) {
      log.warn('Failed to refresh skills catalog, using cached catalog', { error });
      return this.getSkillsCatalog();
    }
  }

  async searchSkillSh(query: string): Promise<CatalogSkill[]> {
    const trimmed = this.normalizeSkillShSearchQuery(query);
    if (!trimmed) return [];

    const cached = this.skillShSearchCache.get(trimmed);
    if (cached && cached.expiresAt > Date.now()) return cached.skills;

    const url = `https://skills.sh/api/search?q=${encodeURIComponent(trimmed)}`;
    try {
      const data = await httpsGet(url);
      const result = JSON.parse(data) as {
        skills?: Array<{
          id: string;
          skillId: string;
          name?: string;
          source: string;
          installs?: number;
          isDuplicate?: boolean;
        }>;
      };

      const skills: CatalogSkill[] = [];
      for (const entry of result.skills ?? []) {
        if (entry.isDuplicate) continue;
        if (!this.isSkillShGithubSource(entry.source)) continue;
        if (skills.length >= 24) break;

        const skillShPath = normalizeSkillShPath(entry.skillId);
        if (!isSafeSkillShPath(skillShPath)) continue;
        const catalogSkillId = normalizeSkillShSkillId(skillShPath);
        if (!catalogSkillId) continue;
        const skillId = this.toSkillShId(entry.source, skillShPath);
        if (skills.some((skill) => skill.id === skillId)) continue;

        const displayName = entry.name || catalogSkillId;
        const description = entry.source;
        const sourceUrl = this.getSkillShUrl(entry.source, skillShPath);
        const skill: CatalogSkill = {
          id: skillId,
          installId: getSkillShInstallName(entry.source, skillShPath),
          displayName,
          description,
          source: 'skillssh',
          sourceRef: entry.source,
          sourceUrl,
          catalogSkillId,
          skillShPath,
          installs: entry.installs,
          iconUrl: this.getSkillShIconUrl(entry.source),
          brandColor: '#000000',
          frontmatter: { name: catalogSkillId, description },
          installed: false,
        };
        skills.push(skill);
      }

      this.skillShSearchCache.set(trimmed, {
        expiresAt: Date.now() + SKILLSH_SEARCH_CACHE_TTL_MS,
        skills,
      });
      for (const skill of skills) this.setSkillShSkillCache(skill.id, skill);
      return skills;
    } catch (error) {
      if (cached) {
        log.warn(`Skills.sh search failed for "${trimmed}", using stale cache`, { error });
        return cached.skills;
      }
      log.warn(`Skills.sh search failed for "${trimmed}"`, { error });
      return [];
    }
  }

  async getSkillContent(skillId: string): Promise<CatalogSkill> {
    const skill = await this.resolveCatalogSkill(skillId);
    if (!skill) throw catalogError('not-found', `Skill "${skillId}" not found in catalog`);
    if (skill.skillMdContent) return skill;

    try {
      if (skill.source === 'skillssh') {
        return { ...skill, skillMdContent: await this.fetchSkillShContent(skill) };
      }
      const mdUrl = this.getSkillMdUrl(skill);
      if (!mdUrl) return skill;
      return { ...skill, skillMdContent: await httpsGet(mdUrl) };
    } catch (error) {
      log.warn(`Failed to fetch SKILL.md for ${skill.id}`, { error });
      return skill;
    }
  }

  async resolveSkillInstall(skillId: string) {
    const skill = await this.getSkillContent(skillId);
    const skillMdContent =
      skill.skillMdContent || generateSkillMd(skill.displayName, skill.description);
    return {
      id: skill.id,
      installId: skill.installId ?? (skill.source === 'skillssh' ? undefined : skill.id),
      skillMdContent,
      source: skill.source,
      sourceRef: skill.sourceRef,
      catalogSkillId: skill.catalogSkillId,
      skillShPath: skill.skillShPath,
      iconUrl: skill.iconUrl,
    };
  }

  async getMcpCatalog(options: McpCatalogOptions = {}): Promise<McpCatalogEntry[]> {
    const staticCatalog = loadStaticMcpCatalog();
    const baseUrl = options.registryBaseUrl ?? DEFAULT_MCP_REGISTRY_BASE_URL;
    const search = options.search?.trim().toLowerCase();

    if (options.featuredOnly ?? true) {
      return filterMcpCatalog(staticCatalog, search);
    }

    const registryEntries = await this.getMcpRegistryCatalog(baseUrl, search);
    const merged = new Map<string, McpCatalogEntry>();
    for (const entry of staticCatalog) merged.set(entry.key, entry);
    for (const entry of registryEntries) merged.set(entry.key, entry);
    return filterMcpCatalog([...merged.values()], search);
  }

  private async getMcpRegistryCatalog(
    registryBaseUrl: string,
    search?: string
  ): Promise<McpCatalogEntry[]> {
    try {
      const servers = await this.fetchMcpRegistryServers(registryBaseUrl, search);
      return servers.flatMap((server) => {
        const entry = registryServerToCatalogEntry(server);
        return entry ? [entry] : [];
      });
    } catch (error) {
      log.warn('Failed to fetch MCP registry catalog, using curated fallback', { error });
      return [];
    }
  }

  private async fetchMcpRegistryServers(
    registryBaseUrl: string,
    search?: string
  ): Promise<RegistryServer[]> {
    const cacheKey = `${registryBaseUrl}|${search ?? ''}`;
    const cached = this.mcpRegistryCache.get(cacheKey);
    if (cached && cached.expiresAt > Date.now()) return cached.servers;

    const url = new URL('/v0.1/servers', registryBaseUrl);
    url.searchParams.set('version', 'latest');
    url.searchParams.set('limit', '100');
    if (search) url.searchParams.set('search', search);

    const data = await httpsGet(url.href, { maxBytes: 8 * 1024 * 1024 });
    const parsed = JSON.parse(data) as { servers?: RegistryServer[]; data?: RegistryServer[] };
    const servers = parsed.servers ?? parsed.data ?? [];
    this.mcpRegistryCache.set(cacheKey, {
      expiresAt: Date.now() + MCP_REGISTRY_CACHE_TTL_MS,
      servers,
    });
    return servers;
  }

  private async resolveCatalogSkill(skillId: string): Promise<CatalogSkill | null> {
    const catalog = await this.getSkillsCatalog();
    return catalog.skills.find((skill) => skill.id === skillId) ?? this.resolveSkillShId(skillId);
  }

  private loadBundledCatalog(): CatalogIndex {
    return normalizeCatalogIndex(bundledCatalog as CatalogIndex);
  }

  private catalogCacheDir(): string {
    return path.join(app.getPath('userData'), 'catalog');
  }

  private skillsCatalogCachePath(): string {
    return path.join(this.catalogCacheDir(), 'skills-catalog-index.json');
  }

  private getSkillMdUrl(skill: CatalogSkill): string | null {
    if (skill.source === 'skillssh' && skill.sourceRef && skill.catalogSkillId) return null;
    if ((skill.source === 'openai' || skill.source === 'anthropic') && skill.sourceUrl) {
      const match = skill.sourceUrl.match(/github\.com\/([^/]+\/[^/]+)\/tree\/main\/(.+)/);
      if (match) return `https://raw.githubusercontent.com/${match[1]}/main/${match[2]}/SKILL.md`;
    }
    return null;
  }

  private normalizeSkillShSearchQuery(query: string): string {
    const trimmed = query.trim();
    if (!trimmed) return '';
    try {
      const url = new URL(trimmed);
      const hostname = url.hostname.toLowerCase();
      if (hostname === 'skills.sh' || hostname === 'www.skills.sh') {
        const parts = url.pathname.split('/').filter(Boolean);
        return parts.at(-1) ?? '';
      }
    } catch {
      // Not a URL; use the plain search query.
    }
    return trimmed.toLowerCase();
  }

  private isSkillShGithubSource(sourceRef: string): boolean {
    const parts = sourceRef.split('/');
    return parts.length === 2 && Boolean(parts[0]) && Boolean(parts[1]);
  }

  private toSkillShId(sourceRef: string, skillPath: string): string {
    return `skillssh:${sourceRef}/${normalizeSkillShPath(skillPath)}`;
  }

  private setSkillShSkillCache(skillId: string, skill: CatalogSkill): void {
    if (this.skillShSkillCache.has(skillId)) this.skillShSkillCache.delete(skillId);
    this.skillShSkillCache.set(skillId, skill);
    while (this.skillShSkillCache.size > SKILLSH_SKILL_CACHE_MAX_ENTRIES) {
      const oldestKey = this.skillShSkillCache.keys().next().value;
      if (!oldestKey) break;
      this.skillShSkillCache.delete(oldestKey);
    }
  }

  private async resolveSkillShId(skillId: string): Promise<CatalogSkill | null> {
    const cached = this.skillShSkillCache.get(skillId);
    if (cached) return cached;
    if (!skillId.startsWith('skillssh:')) return null;

    const parsed = this.parseSkillShRemoteId(skillId);
    if (!parsed) return null;

    const sourceUrl = this.getSkillShUrl(parsed.sourceRef, parsed.skillShPath);
    const pageDescription = await this.fetchSkillShPageDescription(sourceUrl).catch(() => null);
    const skill: CatalogSkill = {
      id: skillId,
      installId: getSkillShInstallName(parsed.sourceRef, parsed.skillShPath),
      displayName: parsed.catalogSkillId,
      description: parsed.sourceRef,
      source: 'skillssh',
      sourceRef: parsed.sourceRef,
      sourceUrl,
      catalogSkillId: parsed.catalogSkillId,
      skillShPath: parsed.skillShPath,
      iconUrl: this.getSkillShIconUrl(parsed.sourceRef),
      brandColor: '#000000',
      frontmatter: {
        name: parsed.catalogSkillId,
        description: pageDescription ?? parsed.sourceRef,
      },
      installed: false,
    };
    this.setSkillShSkillCache(skill.id, skill);
    return skill;
  }

  private parseSkillShRemoteId(
    skillId: string
  ): { sourceRef: string; catalogSkillId: string; skillShPath: string } | null {
    const fullId = skillId.slice('skillssh:'.length);
    const parts = fullId.split('/');
    if (parts.length < 3) return null;

    const sourceRef = parts.slice(0, 2).join('/');
    if (!this.isSkillShGithubSource(sourceRef)) return null;

    const skillShPath = normalizeSkillShPath(parts.slice(2).join('/'));
    if (!isSafeSkillShPath(skillShPath)) return null;
    const catalogSkillId = normalizeSkillShSkillId(skillShPath);
    if (!catalogSkillId) return null;
    return { sourceRef, catalogSkillId, skillShPath };
  }

  private getSkillShUrl(sourceRef: string, skillPath: string): string {
    const encodedSkillPath = normalizeSkillShPath(skillPath)
      .split('/')
      .map(encodeURIComponent)
      .join('/');
    return `https://skills.sh/${sourceRef}/${encodedSkillPath}`;
  }

  private getSkillShIconUrl(sourceRef: string): string | undefined {
    const [owner, repo] = sourceRef.split('/');
    if (!owner || !repo || sourceRef.split('/').length !== 2) return undefined;
    return `https://github.com/${owner}.png?size=80`;
  }

  private async fetchSkillShContent(skill: CatalogSkill): Promise<string> {
    try {
      return await this.fetchSkillShSkillMd(skill);
    } catch (error) {
      log.warn(`Failed to fetch Skills.sh SKILL.md for ${skill.id}, using page metadata`, {
        error,
      });
      const description = await this.fetchSkillShDescription(skill).catch(() => skill.description);
      return generateSkillMd(skill.displayName, description);
    }
  }

  private async fetchSkillShSkillMd(skill: CatalogSkill): Promise<string> {
    if (!skill.sourceRef || !skill.catalogSkillId || !skill.skillShPath) {
      throw new Error('Invalid Skills.sh skill reference');
    }
    const [owner, repo] = skill.sourceRef.split('/');
    if (!owner || !repo || skill.sourceRef.split('/').length !== 2) {
      throw new Error(`Skills.sh source "${skill.sourceRef}" is not a GitHub repository`);
    }
    if (!isSafeSkillShPath(skill.skillShPath)) {
      throw new Error(
        `Invalid Skills.sh skill path for ${skill.sourceRef}/${skill.catalogSkillId}`
      );
    }

    const candidatePaths = [`${skill.skillShPath}/SKILL.md`];
    if (!skill.skillShPath.startsWith('skills/')) {
      candidatePaths.push(`skills/${skill.skillShPath}/SKILL.md`);
    }

    for (const skillMdPath of candidatePaths) {
      const encodedPath = skillMdPath.split('/').map(encodeURIComponent).join('/');
      try {
        return await httpsGet(
          `https://raw.githubusercontent.com/${owner}/${repo}/HEAD/${encodedPath}`
        );
      } catch (error) {
        if (!(error instanceof HttpStatusError) || error.statusCode !== 404) throw error;
      }
    }

    const treePath = await this.findSkillShSkillMdPath(owner, repo, skill.skillShPath);
    if (treePath) {
      const encodedPath = treePath.split('/').map(encodeURIComponent).join('/');
      return httpsGet(`https://raw.githubusercontent.com/${owner}/${repo}/HEAD/${encodedPath}`);
    }

    throw new Error(`Could not fetch SKILL.md for ${skill.sourceRef}/${skill.catalogSkillId}`);
  }

  private async findSkillShSkillMdPath(
    owner: string,
    repo: string,
    skillPath: string
  ): Promise<string | null> {
    const treeData = await httpsGet(
      `https://api.github.com/repos/${owner}/${repo}/git/trees/HEAD?recursive=1`
    );
    const tree = JSON.parse(treeData) as { tree?: Array<{ path: string; type: string }> };
    const candidates =
      tree.tree?.filter((entry) => {
        if (entry.type !== 'blob') return false;
        if (entry.path === `${skillPath}/SKILL.md`) return true;
        if (entry.path.endsWith(`/skills/${skillPath}/SKILL.md`)) return true;
        return entry.path.endsWith(`/${skillPath}/SKILL.md`);
      }) ?? [];
    return candidates[0]?.path ?? null;
  }

  private async fetchSkillShDescription(skill: CatalogSkill): Promise<string> {
    if (!skill.sourceUrl) return skill.description;
    return this.fetchSkillShPageDescription(skill.sourceUrl);
  }

  private async fetchSkillShPageDescription(sourceUrl: string): Promise<string> {
    const html = await httpsGet(sourceUrl);
    const description =
      this.extractHtmlMetaContent(html, 'description') ??
      this.extractHtmlMetaContent(html, 'og:description') ??
      '';
    return this.decodeHtmlEntities(description).trim();
  }

  private extractHtmlMetaContent(html: string, name: string): string | null {
    const escapedName = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const nameBeforeContent = new RegExp(
      `<meta[^>]+(?:name|property)=["']${escapedName}["'][^>]+content=["']([^"']*)["']`,
      'i'
    );
    const contentBeforeName = new RegExp(
      `<meta[^>]+content=["']([^"']*)["'][^>]+(?:name|property)=["']${escapedName}["']`,
      'i'
    );
    return html.match(nameBeforeContent)?.[1] ?? html.match(contentBeforeName)?.[1] ?? null;
  }

  private decodeHtmlEntities(value: string): string {
    return value
      .replace(/&quot;/g, '"')
      .replace(/&#x27;|&#39;/g, "'")
      .replace(/&amp;/g, '&')
      .replace(/&lt;/g, '<')
      .replace(/&gt;/g, '>');
  }

  private async fetchOpenAICatalog(): Promise<CatalogSkill[]> {
    const baseUrl = 'https://api.github.com/repos/openai/skills/contents/skills';
    const rawBase = 'https://raw.githubusercontent.com/openai/skills/main/skills';
    const [curatedData, systemData] = await Promise.all([
      httpsGet(`${baseUrl}/.curated`),
      httpsGet(`${baseUrl}/.system`).catch(() => '[]'),
    ]);
    const entries = [
      ...(JSON.parse(curatedData) as Array<{ name: string; type: string; html_url?: string }>).map(
        (entry) => ({ ...entry, category: '.curated' as const })
      ),
      ...(JSON.parse(systemData) as Array<{ name: string; type: string; html_url?: string }>).map(
        (entry) => ({ ...entry, category: '.system' as const })
      ),
    ].filter((entry) => entry.type === 'dir');

    return Promise.all(
      entries.map(async (entry): Promise<CatalogSkill> => {
        const fallbackName = titleCaseSlug(entry.name);
        let displayName = fallbackName;
        let description = '';
        let iconUrl: string | undefined;
        let brandColor: string | undefined;
        let defaultPrompt: string | undefined;

        try {
          const yamlUrl = `${rawBase}/${entry.category}/${entry.name}/agents/openai.yaml`;
          const parsed = parseSimpleYaml(await httpsGet(yamlUrl));
          displayName = parsed['display_name'] || fallbackName;
          description = parsed['short_description'] || '';
          defaultPrompt = parsed['default_prompt'];
          brandColor = parsed['brand_color'];
          const iconPath = parsed['icon_small'] || parsed['icon_large'];
          if (iconPath) {
            iconUrl = `${rawBase}/${entry.category}/${entry.name}/${iconPath.replace(/^\.\//, '')}`;
          }
        } catch {
          // openai.yaml is optional.
        }

        if (!description) {
          description = await this.fetchFrontmatterDescription(
            `${rawBase}/${entry.category}/${entry.name}/SKILL.md`
          );
        }
        if (!description) description = entry.name.replace(/-/g, ' ');

        return {
          id: entry.name,
          displayName,
          description,
          source: 'openai',
          sourceUrl: entry.html_url,
          iconUrl,
          brandColor: brandColor || '#10a37f',
          defaultPrompt,
          frontmatter: { name: entry.name, description },
          installed: false,
        };
      })
    );
  }

  private async fetchAnthropicCatalog(): Promise<CatalogSkill[]> {
    const url = 'https://api.github.com/repos/anthropics/skills/contents/skills';
    const rawBase = 'https://raw.githubusercontent.com/anthropics/skills/main/skills';
    const entries = JSON.parse(await httpsGet(url)) as Array<{
      name: string;
      type: string;
      html_url?: string;
    }>;
    const skills: CatalogSkill[] = [];
    for (const entry of entries) {
      if (entry.type !== 'dir') continue;
      const description =
        (await this.fetchFrontmatterDescription(`${rawBase}/${entry.name}/SKILL.md`)) ||
        entry.name.replace(/-/g, ' ');
      skills.push({
        id: entry.name,
        displayName: titleCaseSlug(entry.name),
        description,
        source: 'anthropic',
        sourceUrl: entry.html_url,
        brandColor: '#d4a574',
        frontmatter: { name: entry.name, description },
        installed: false,
      });
    }
    return skills;
  }

  private async fetchFrontmatterDescription(url: string): Promise<string> {
    try {
      const { frontmatter } = parseFrontmatter(await httpsGet(url));
      return frontmatter.description;
    } catch {
      return '';
    }
  }
}

export const catalogService = new CatalogService();

export function toCatalogServiceError(error: unknown): CatalogServiceError {
  if (isCatalogServiceError(error)) return error;
  if (error instanceof HttpStatusError) {
    return { type: 'network', message: error.message, statusCode: error.statusCode };
  }
  return { type: 'io', message: error instanceof Error ? error.message : String(error) };
}

function catalogError(type: CatalogServiceError['type'], message: string): CatalogServiceError {
  return { type, message };
}

function isCatalogServiceError(error: unknown): error is CatalogServiceError {
  return (
    typeof error === 'object' &&
    error !== null &&
    'type' in error &&
    'message' in error &&
    typeof (error as CatalogServiceError).message === 'string'
  );
}

function normalizeCatalogIndex(catalog: CatalogIndex): CatalogIndex {
  return {
    ...catalog,
    skills: catalog.skills.map((skill) => ({
      ...skill,
      installed: skill.installed ?? false,
    })),
  };
}

function loadStaticMcpCatalog(): McpCatalogEntry[] {
  return Object.entries(catalogData).map(([key, entry]) => ({
    key,
    name: entry.name,
    description: entry.description,
    docsUrl: entry.docsUrl,
    defaultConfig: entry.config,
    credentialKeys: entry.credentialKeys,
  }));
}

function filterMcpCatalog(entries: McpCatalogEntry[], search?: string): McpCatalogEntry[] {
  if (!search) return entries;
  return entries.filter(
    (entry) =>
      entry.key.toLowerCase().includes(search) ||
      entry.name.toLowerCase().includes(search) ||
      entry.description.toLowerCase().includes(search)
  );
}

function registryServerToCatalogEntry(server: RegistryServer): McpCatalogEntry | null {
  const registryName = stringValue(server.name);
  if (!registryName) return null;
  const defaultConfig = registryServerDefaultConfig(server);
  if (!defaultConfig) return null;
  const name = stringValue(server.title) ?? titleCaseSlug(registryName.split('/').at(-1) ?? '');
  const docsUrl =
    stringValue(server.website_url) ??
    stringValue(server.repository) ??
    stringValue(server.source) ??
    DEFAULT_MCP_REGISTRY_BASE_URL;
  return {
    key: registryKey(registryName),
    name,
    description: stringValue(server.description) ?? '',
    docsUrl,
    defaultConfig,
    credentialKeys: credentialKeysFromConfig(defaultConfig),
    _meta: recordValue(server._meta),
  };
}

function registryServerDefaultConfig(server: RegistryServer): RawServerEntry | null {
  const remote = arrayValue(server.remotes)
    .map(recordValue)
    .find((entry): entry is Record<string, unknown> => Boolean(stringValue(entry?.url)));
  if (remote) {
    return { type: 'http', url: stringValue(remote.url) };
  }

  const npmPackage = arrayValue(server.packages)
    .map(recordValue)
    .find((entry): entry is Record<string, unknown> => {
      const registry =
        stringValue(entry?.registry_name) ??
        stringValue(entry?.registry) ??
        stringValue(entry?.package_registry);
      return registry?.toLowerCase() === 'npm' && Boolean(stringValue(entry?.name));
    });
  if (!npmPackage) return null;

  const packageName = stringValue(npmPackage.name)!;
  const version = stringValue(npmPackage.version);
  const args = ['-y', version ? `${packageName}@${version}` : packageName];
  for (const arg of packageArguments(npmPackage)) args.push(arg);
  return { command: 'npx', args };
}

function packageArguments(pkg: Record<string, unknown>): string[] {
  return arrayValue(pkg.package_arguments)
    .map((entry) => (typeof entry === 'string' ? entry : stringValue(recordValue(entry)?.value)))
    .filter((entry): entry is string => Boolean(entry));
}

function credentialKeysFromConfig(config: RawServerEntry) {
  const keys: Array<{ key: string; required: boolean }> = [];
  for (const key of Object.keys(recordValue(config.env) ?? {})) keys.push({ key, required: true });
  for (const key of Object.keys(recordValue(config.headers) ?? {})) {
    keys.push({ key, required: true });
  }
  return keys;
}

function registryKey(name: string): string {
  const leaf = name.split('/').at(-1) ?? name;
  const key = leaf
    .toLowerCase()
    .replace(/[^\w\-._]+/g, '_')
    .replace(/^_+|_+$/g, '');
  if (key) return key;
  return createHash('sha256').update(name).digest('hex').slice(0, 12);
}

function stringValue(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value : undefined;
}

function recordValue(value: unknown): Record<string, unknown> | undefined {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : undefined;
}

function arrayValue(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function titleCaseSlug(value: string): string {
  return value
    .split(/[-_]/g)
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

function parseSimpleYaml(content: string): Record<string, string> {
  const result: Record<string, string> = {};
  for (const line of content.split('\n')) {
    const match = line.match(/^\s+(\w+):\s*"?([^"]*)"?\s*$/);
    if (match) result[match[1]] = match[2].trim();
  }
  return result;
}

const MAX_SKILL_NAME_LENGTH = 64;

function getSkillShInstallName(sourceRef: string, skillPath: string): string {
  const sourceSlug = toSkillNameSlug(sourceRef.replace(/\//g, '-'));
  const normalizedSkillPath = normalizeSkillShPath(skillPath);
  const skillSlug = toSkillNameSlug(normalizedSkillPath);
  const hash = createHash('sha256')
    .update(`${sourceRef}/${normalizedSkillPath}`)
    .digest('hex')
    .slice(0, 8);
  const base = `skillssh-${sourceSlug}-${skillSlug}`;
  const maxBaseLength = MAX_SKILL_NAME_LENGTH - hash.length - 1;
  const truncatedBase = base.slice(0, maxBaseLength).replace(/-+$/g, '') || 'skillssh';
  return `${truncatedBase}-${hash}`;
}

function toSkillNameSlug(value: string): string {
  return (
    value
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '') || 'skill'
  );
}
