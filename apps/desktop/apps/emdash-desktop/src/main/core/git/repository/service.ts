import type { GitRemotesState, RepositorySelector } from '@emdash/core/runtimes/git/api';
import { gitContract } from '@emdash/core/runtimes/git/api';
import type { Unsubscribe } from '@emdash/shared';
import { createScope } from '@emdash/shared/concurrency';
import { observe, remote } from '@emdash/wire/state';
import type { EffectiveSettings } from '@core/primitives/project-settings/api';
import type { ProjectRemoteState } from '@core/primitives/projects/api';
import type { GitRuntimeClient } from '@main/gateway/desktop-workers';

export class GitRepositoryService {
  constructor(
    private readonly client: GitRuntimeClient,
    private readonly selector: RepositorySelector,
    /** The project's blessed-resolver output (spec: github-git-settings §2). */
    private readonly resolveEffectiveSettings: () => Promise<EffectiveSettings>
  ) {}

  subscribeRemotes(cb: (update: GitRemotesState) => void): Unsubscribe {
    const scope = createScope({ label: 'git-repository-remotes' });
    const repository = remote(gitContract.repository.model, this.client.repository.model, {
      scope,
      lingerMs: 15_000,
    });
    observe(
      repository(this.selector).states.remotes,
      (snapshot) => {
        if (snapshot.value) cb(snapshot.value);
      },
      { scope }
    );
    return () => {
      void scope.dispose();
    };
  }

  /**
   * The effective base remote through the blessed resolver (spec:
   * github-git-settings §2). `null` means the repository has no remotes.
   */
  async getBaseRemote(): Promise<string | null> {
    return (await this.resolveEffectiveSettings()).baseRemote.value;
  }

  async getEffectiveRemotes(): Promise<{ baseRemote: string | null; pushRemote: string | null }> {
    const effective = await this.resolveEffectiveSettings();
    return {
      baseRemote: effective.baseRemote.value,
      pushRemote: effective.pushRemote.value,
    };
  }

  async getRemoteState(): Promise<ProjectRemoteState> {
    try {
      const remotes = (
        await this.client.repository.model.state(this.selector, 'remotes').snapshot()
      ).data.remotes;
      const remoteName = await this.getBaseRemote();
      const remoteUrl =
        remoteName !== null ? remotes.find((r) => r.name === remoteName)?.url : undefined;
      return { hasRemote: remotes.length > 0, selectedRemoteUrl: remoteUrl ?? null };
    } catch {
      return { hasRemote: false, selectedRemoteUrl: null };
    }
  }
}
