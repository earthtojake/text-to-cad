import { openFixture } from '@tooling/utils/db';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { projectSettings, projects } from '@core/services/app-db/node/schema';
import { countProjectsUsingGithubAccount } from './count-projects-using-github-account';

const TARGET_ACCOUNT_ID = 'github.com:42';
const OTHER_ACCOUNT_ID = 'github.com:99';

function baseSettingsJson(githubAccountId?: string | null): string {
  const settings: Record<string, unknown> = {
    defaultBranch: 'main',
    baseRemote: 'origin',
  };
  if (githubAccountId !== undefined) {
    settings.githubAccountId = githubAccountId;
  }
  return JSON.stringify(settings);
}

describe('countProjectsUsingGithubAccount', () => {
  let fixture: Awaited<ReturnType<typeof openFixture>>;

  beforeEach(async () => {
    fixture = await openFixture('empty');
  });

  afterEach(() => {
    fixture.close();
  });

  it('counts only persisted projects pinned to the target account', async () => {
    await fixture.db.insert(projects).values([
      { id: 'project-match-1', name: 'Match 1' },
      { id: 'project-match-2', name: 'Match 2' },
      { id: 'project-null', name: 'Null' },
      { id: 'project-other', name: 'Other' },
      { id: 'project-unconfigured', name: 'Unconfigured' },
    ]);
    await fixture.db.insert(projectSettings).values([
      {
        projectId: 'project-match-1',
        baseProjectSettingsJson: baseSettingsJson(TARGET_ACCOUNT_ID),
      },
      {
        projectId: 'project-match-2',
        baseProjectSettingsJson: baseSettingsJson(` ${TARGET_ACCOUNT_ID} `),
      },
      {
        projectId: 'project-null',
        baseProjectSettingsJson: baseSettingsJson(null),
      },
      {
        projectId: 'project-other',
        baseProjectSettingsJson: baseSettingsJson(OTHER_ACCOUNT_ID),
      },
      {
        projectId: 'project-unconfigured',
        baseProjectSettingsJson: baseSettingsJson(),
      },
    ]);

    await expect(countProjectsUsingGithubAccount(fixture.db, TARGET_ACCOUNT_ID)).resolves.toBe(2);
    await expect(countProjectsUsingGithubAccount(fixture.db, OTHER_ACCOUNT_ID)).resolves.toBe(1);
    await expect(countProjectsUsingGithubAccount(fixture.db, 'github.com:missing')).resolves.toBe(
      0
    );
  });

  it('counts rows already migrated to the stored githubAccount model', async () => {
    await fixture.db.insert(projects).values([
      { id: 'project-account-ref', name: 'Account ref' },
      { id: 'project-none', name: 'Explicit none' },
    ]);
    await fixture.db.insert(projectSettings).values([
      {
        projectId: 'project-account-ref',
        baseProjectSettingsJson: JSON.stringify({
          githubAccount: { kind: 'account', accountId: TARGET_ACCOUNT_ID },
        }),
      },
      {
        projectId: 'project-none',
        baseProjectSettingsJson: JSON.stringify({ githubAccount: { kind: 'none' } }),
      },
    ]);

    await expect(countProjectsUsingGithubAccount(fixture.db, TARGET_ACCOUNT_ID)).resolves.toBe(1);
  });

  it('skips malformed base settings JSON', async () => {
    await fixture.db.insert(projects).values([
      { id: 'project-malformed', name: 'Malformed' },
      { id: 'project-valid', name: 'Valid' },
    ]);
    await fixture.db.insert(projectSettings).values([
      {
        projectId: 'project-malformed',
        baseProjectSettingsJson: '{not-json',
      },
      {
        projectId: 'project-valid',
        baseProjectSettingsJson: baseSettingsJson(TARGET_ACCOUNT_ID),
      },
    ]);

    await expect(countProjectsUsingGithubAccount(fixture.db, TARGET_ACCOUNT_ID)).resolves.toBe(1);
  });
});
