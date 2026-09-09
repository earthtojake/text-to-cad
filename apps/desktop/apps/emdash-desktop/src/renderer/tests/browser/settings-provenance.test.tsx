import '@emdash/ui/style.css';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import {
  BrokenSettingNotice,
  ProvenanceBadge,
  ProvenanceSourceLine,
  ResetProvenanceButton,
} from '@core/features/projects/contributions/browser/settings-provenance';
import type { GitHubAccountSummary } from '@core/primitives/github/api';
import {
  resolveEffectiveSettings,
  type RepoFacts,
  type StoredProjectGitSettings,
} from '@core/primitives/project-settings/api';

beforeAll(() => {
  (
    globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;
});

const repoFacts: RepoFacts = {
  remotes: [
    { name: 'origin', host: 'github.com', headBranch: 'main', branches: ['main', 'develop'] },
    { name: 'fork', host: 'github.com', headBranch: null, branches: ['main'] },
  ],
  localBranches: ['main'],
};

const accounts: GitHubAccountSummary[] = [
  {
    accountId: 'row-1',
    host: 'github.com',
    login: 'dkonopka',
    avatarUrl: '',
    credentialSource: 'cli',
    isDefault: true,
  },
];

function resolve(project: StoredProjectGitSettings) {
  return resolveEffectiveSettings(
    { project, hostWorktreeRoot: '/hosts/worktrees', builtInWorktreeRoot: '/built-in/worktrees' },
    repoFacts,
    accounts
  );
}

describe('provenance rendering layer over resolver output', () => {
  let host: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    host = document.createElement('div');
    document.body.appendChild(host);
    root = createRoot(host);
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    host.remove();
  });

  it('renders inferred values with a badge and their inference source', async () => {
    const effective = resolve({});

    await act(async () => {
      root.render(
        <div>
          <ProvenanceBadge provenance={effective.baseRemote.provenance} />
          <ProvenanceSourceLine provenance={effective.defaultBranch.provenance} />
          <ProvenanceSourceLine provenance={effective.githubAccount.provenance} />
        </div>
      );
    });

    expect(effective.baseRemote.value).toBe('origin');
    expect(host.textContent).toContain('Inferred');
    expect(host.textContent).toContain('from remote HEAD');
    expect(host.textContent).toContain('from the default account');
  });

  it('renders explicit values as Set with a reset affordance', async () => {
    const effective = resolve({ baseRemote: 'fork' });
    let resetCalls = 0;

    await act(async () => {
      root.render(
        <div>
          <ProvenanceBadge provenance={effective.baseRemote.provenance} />
          <ResetProvenanceButton onReset={() => resetCalls++} />
        </div>
      );
    });

    expect(effective.baseRemote.value).toBe('fork');
    expect(host.textContent).toContain('Set');
    const reset = host.querySelector('button');
    expect(reset?.textContent).toContain('Reset to inferred');
    await act(async () => reset!.click());
    expect(resetCalls).toBe(1);
  });

  it('renders broken settings with the stale value and the live fallback', async () => {
    const effective = resolve({ baseRemote: 'gone' });
    const provenance = effective.baseRemote.provenance;
    if (provenance.kind !== 'broken-setting') throw new Error('expected broken-setting');

    await act(async () => {
      root.render(
        <div>
          <ProvenanceBadge provenance={provenance} />
          <BrokenSettingNotice
            staleValue={provenance.staleValue}
            effectiveValue={effective.baseRemote.value}
          />
        </div>
      );
    });

    expect(effective.baseRemote.value).toBe('origin');
    expect(host.textContent).toContain('Broken');
    expect(host.textContent).toContain("Set to 'gone' — not found, using 'origin'.");
  });

  it('renders a dangling account pin as Unavailable, never another identity', async () => {
    const effective = resolve({ githubAccount: { kind: 'account', accountId: 'gone-row' } });

    await act(async () => {
      root.render(<ProvenanceBadge provenance={effective.githubAccount.provenance} />);
    });

    expect(effective.githubAccount.value).toBeNull();
    expect(effective.githubAccount.provenance.kind).toBe('unresolvable');
    expect(host.textContent).toContain('Unavailable');
  });

  it('reads Inherited for the worktree root flavor', async () => {
    const effective = resolve({});

    await act(async () => {
      root.render(
        <div>
          <ProvenanceBadge provenance={effective.worktreeRoot.provenance} flavor="inherited" />
          <ProvenanceSourceLine provenance={effective.worktreeRoot.provenance} />
        </div>
      );
    });

    expect(effective.worktreeRoot.value).toBe('/hosts/worktrees');
    expect(host.textContent).toContain('Inherited');
    expect(host.textContent).toContain('from the host default');
  });
});
