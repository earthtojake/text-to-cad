import { describe, expect, it } from 'vitest';
import { mergeSkillsInstalledState } from './merge-installed';
import type { CatalogIndex, CatalogSkill } from './types';

describe('mergeSkillsInstalledState', () => {
  it('marks catalog skills installed by id', () => {
    const merged = mergeSkillsInstalledState(catalog([skill({ id: 'git' })]), [
      skill({ id: 'git', installed: true, localPath: '/home/ada/.agentskills/git' }),
    ]);

    expect(merged.skills[0]).toMatchObject({
      id: 'git',
      installed: true,
      localPath: '/home/ada/.agentskills/git',
    });
  });

  it('matches Skills.sh catalog entries by pre-computed installId', () => {
    // The main-process catalog service pre-computes installId before sending to the renderer.
    const installId = 'skillssh-owner-repo-skills-react-ab12cd34';
    const merged = mergeSkillsInstalledState(
      catalog([
        skill({
          id: 'skillssh:owner/repo/skills/react',
          source: 'skillssh',
          sourceRef: 'owner/repo',
          catalogSkillId: 'react',
          skillShPath: 'skills/react',
          installId,
        }),
      ]),
      [
        skill({
          id: installId,
          installId,
          displayName: 'React Local',
          installed: true,
          localPath: `/home/ada/.agentskills/${installId}`,
        }),
      ]
    );

    expect(merged.skills[0]).toMatchObject({
      installed: true,
      installId,
      displayName: 'React Local',
    });
  });

  it('keeps local-only skills not present in the catalog', () => {
    const local = skill({ id: 'local-skill', installed: true, source: 'local' });
    const merged = mergeSkillsInstalledState(catalog([skill({ id: 'catalog-skill' })]), [local]);

    expect(merged.skills.map((entry) => entry.id)).toEqual(['catalog-skill', 'local-skill']);
  });
});

function catalog(skills: CatalogSkill[]): CatalogIndex {
  return { version: 1, lastUpdated: '2026-01-01T00:00:00.000Z', skills };
}

function skill(overrides: Partial<CatalogSkill>): CatalogSkill {
  return {
    id: 'skill',
    displayName: 'Skill',
    description: 'A skill',
    source: 'openai',
    frontmatter: { name: 'skill', description: 'A skill' },
    installed: false,
    ...overrides,
  };
}
