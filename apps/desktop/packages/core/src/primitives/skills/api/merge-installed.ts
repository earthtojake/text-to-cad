import type { CatalogIndex, CatalogSkill } from './types';
import { isValidSkillName } from './validation';

export function mergeSkillsInstalledState(
  catalog: CatalogIndex,
  installed: readonly CatalogSkill[]
): CatalogIndex {
  const installedMap = new Map(installed.map((skill) => [skill.id, skill]));
  const seen = new Set<string>();
  const dedupedSkills = catalog.skills.filter((skill) => {
    if (seen.has(skill.id)) return false;
    seen.add(skill.id);
    return true;
  });

  const mergedSkills: CatalogSkill[] = dedupedSkills.map((skill) => {
    const installNames = getSkillInstallNameCandidates(skill);
    const installName = installNames[0] ?? skill.id;
    const local =
      installedMap.get(skill.id) ??
      installNames.map((name) => installedMap.get(name)).find(Boolean);
    if (!local) {
      return {
        ...skill,
        installId: installName !== skill.id ? installName : skill.installId,
        installed: false,
      };
    }

    installedMap.delete(local.id);
    return {
      ...skill,
      installId: installName !== skill.id ? installName : skill.installId,
      displayName: local.displayName || skill.displayName,
      description: local.description || skill.description,
      frontmatter: { ...skill.frontmatter, ...local.frontmatter },
      installed: true,
      localPath: local.localPath,
      skillMdContent: local.skillMdContent,
    };
  });

  for (const local of installedMap.values()) {
    mergedSkills.push(local);
  }

  return { ...catalog, skills: mergedSkills };
}

export function getSkillInstallNameCandidates(skill: CatalogSkill): string[] {
  if (skill.source !== 'skillssh' || !skill.sourceRef || !skill.catalogSkillId) return [skill.id];

  // installId is pre-computed by the main-process catalog service; use it directly here so
  // this module remains browser-safe (no node:crypto dependency).
  const installNames: string[] = skill.installId ? [skill.installId] : [skill.id];
  const legacyInstallName = getLegacySkillShInstallName(skill.sourceRef, skill.catalogSkillId);
  if (legacyInstallName && !installNames.includes(legacyInstallName)) {
    installNames.push(legacyInstallName);
  }
  return installNames;
}

export function normalizeSkillShPath(skillId: string): string {
  const normalized = skillId.replace(/\\/g, '/').replace(/^\/+|\/+$/g, '');
  return normalized.endsWith('/SKILL.md') ? normalized.slice(0, -'/SKILL.md'.length) : normalized;
}

export function normalizeSkillShSkillId(skillId: string): string {
  const normalized = skillId.replace(/\\/g, '/').replace(/\/+$/, '');
  const withoutSkillMd = normalized.endsWith('/SKILL.md')
    ? normalized.slice(0, -'/SKILL.md'.length)
    : normalized;
  return withoutSkillMd.split('/').at(-1) ?? '';
}

export function isSafeSkillShPath(skillPath: string): boolean {
  if (!skillPath || skillPath.startsWith('/')) return false;
  return !skillPath.split('/').some((part) => !part || part === '.' || part === '..');
}

function getLegacySkillShInstallName(sourceRef: string, catalogSkillId: string): string | null {
  const [owner, repo] = sourceRef.split('/');
  const installName = `skillssh-${owner}-${repo}-${normalizeSkillShSkillId(catalogSkillId)}`;
  return isValidSkillName(installName) ? installName : null;
}
