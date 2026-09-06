import { err, ok, type Result } from '@emdash/shared';
import {
  generateSkillMd,
  isValidSkillName,
  parseFrontmatter,
  type CatalogSkill,
} from '#primitives/skills/api';
import type { AgentConfigSkillsError } from '#runtimes/agent-config/api';
import type { AgentConfigSkillsModel } from '#runtimes/agent-config/node/state/live-models';
import { publishLiveModelState } from '#runtimes/agent-config/node/state/live-models';
import type { PluginFs } from '#services/agent-plugins/api/plugins';
import type { AgentConfigRuntimeDeps } from './types';

const SKILLS_ROOT = '.agentskills';
const EMDASH_META = `${SKILLS_ROOT}/.emdash`;
const SKILLSH_INSTALLS_PATH = `${EMDASH_META}/skillssh-installs.json`;

type SkillInstallPayload = {
  id: string;
  installId?: string;
  skillMdContent: string;
  source?: CatalogSkill['source'];
  sourceRef?: string;
  catalogSkillId?: string;
  skillShPath?: string;
  iconUrl?: string;
};

type SkillShInstallRecord = {
  sourceRef: string;
  catalogSkillId: string;
  skillShPath: string;
};

export class AgentSkillsManager {
  private list: CatalogSkill[] = [];

  constructor(
    private readonly deps: AgentConfigRuntimeDeps,
    private readonly model: AgentConfigSkillsModel
  ) {}

  async initialize(): Promise<void> {
    await this.refresh();
  }

  async refresh(): Promise<CatalogSkill[]> {
    const installed = await getInstalledSkills(this.deps.agentHost.fs, this.deps.agentHost.homeDir);
    this.publish(installed);
    return installed;
  }

  async installSkill(
    payload: SkillInstallPayload
  ): Promise<Result<CatalogSkill[], AgentConfigSkillsError>> {
    const installId = payload.installId ?? payload.id;
    if (!isValidSkillName(installId)) {
      return err({ type: 'invalid-state', message: `Invalid skill name: "${installId}"` });
    }
    try {
      await this.deps.agentHost.fs.write(
        `${SKILLS_ROOT}/${installId}/SKILL.md`,
        payload.skillMdContent
      );
      if (
        payload.source === 'skillssh' &&
        payload.sourceRef &&
        payload.catalogSkillId &&
        payload.skillShPath
      ) {
        const installs = await readSkillShInstalls(this.deps.agentHost.fs);
        installs[installId] = {
          sourceRef: payload.sourceRef,
          catalogSkillId: payload.catalogSkillId,
          skillShPath: payload.skillShPath,
        };
        await writeSkillShInstalls(this.deps.agentHost.fs, installs);
      }
      return ok(await this.refresh());
    } catch (error) {
      return err(toIoError(error));
    }
  }

  async removeSkill(name: string): Promise<Result<CatalogSkill[], AgentConfigSkillsError>> {
    try {
      await this.deps.agentHost.fs.delete(`${SKILLS_ROOT}/${name}`);
      const installs = await readSkillShInstalls(this.deps.agentHost.fs);
      if (installs[name]) {
        delete installs[name];
        await writeSkillShInstalls(this.deps.agentHost.fs, installs);
      }
      return ok(await this.refresh());
    } catch (error) {
      return err(toIoError(error));
    }
  }

  async createSkill(input: {
    name: string;
    description: string;
    content?: string;
  }): Promise<Result<CatalogSkill[], AgentConfigSkillsError>> {
    if (!isValidSkillName(input.name)) {
      return err({ type: 'invalid-state', message: `Invalid skill name: "${input.name}"` });
    }
    try {
      const existing = await this.deps.agentHost.fs.exists(`${SKILLS_ROOT}/${input.name}/SKILL.md`);
      if (existing) {
        return err({ type: 'invalid-state', message: `Skill "${input.name}" already exists` });
      }
      await this.deps.agentHost.fs.write(
        `${SKILLS_ROOT}/${input.name}/SKILL.md`,
        generateSkillMd(input.name, input.description, input.content)
      );
      return ok(await this.refresh());
    } catch (error) {
      return err(toIoError(error));
    }
  }

  private publish(list: CatalogSkill[]): void {
    const previous = this.list;
    this.list = list;
    publishLiveModelState(this.model.states.list, list, previous);
  }
}

function toIoError(error: unknown): AgentConfigSkillsError {
  return { type: 'io', message: error instanceof Error ? error.message : String(error) };
}

async function getInstalledSkills(fs: PluginFs, homeDir: string): Promise<CatalogSkill[]> {
  const entries = await fs.list(SKILLS_ROOT);
  const provenance = await readSkillShInstalls(fs);
  const skills: CatalogSkill[] = [];
  for (const entry of entries) {
    if (entry === '.emdash') continue;
    const content = await fs.read(`${SKILLS_ROOT}/${entry}/SKILL.md`);
    if (!content) continue;
    const parsed = parseFrontmatter(content);
    const source = provenance[entry] ? 'skillssh' : 'local';
    const record = provenance[entry];
    skills.push({
      id: record?.catalogSkillId ?? entry,
      installId: entry,
      displayName: parsed.frontmatter.name || entry,
      description: parsed.frontmatter.description || '',
      source,
      sourceRef: record?.sourceRef,
      catalogSkillId: record?.catalogSkillId,
      skillShPath: record?.skillShPath,
      skillMdContent: content,
      frontmatter: parsed.frontmatter,
      installed: true,
      localPath: `${homeDir}/${SKILLS_ROOT}/${entry}`,
    });
  }
  return skills;
}

async function readSkillShInstalls(fs: PluginFs): Promise<Record<string, SkillShInstallRecord>> {
  const raw = await fs.read(SKILLSH_INSTALLS_PATH);
  if (!raw) return {};
  try {
    return JSON.parse(raw) as Record<string, SkillShInstallRecord>;
  } catch {
    return {};
  }
}

async function writeSkillShInstalls(
  fs: PluginFs,
  records: Record<string, SkillShInstallRecord>
): Promise<void> {
  await fs.write(SKILLSH_INSTALLS_PATH, JSON.stringify(records, null, 2));
}
