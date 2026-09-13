import type { GitRemote } from '@emdash/core/runtimes/git/api';
import { parseRepositoryRef, type RepositoryRef } from '@core/primitives/repository/api';

export type TargetRemote = {
  remote: GitRemote;
  repository: RepositoryRef;
};

export function getTargetRemotes(
  remotes: ReadonlyArray<GitRemote>,
  options: { host?: string } = {}
): TargetRemote[] {
  return remotes
    .map((remote) => {
      const repository = parseRepositoryRef(remote.url);
      return repository ? { remote, repository } : null;
    })
    .filter((option): option is TargetRemote => option !== null)
    .filter((option) => !options.host || option.repository.host === options.host);
}

export function resolveCreatePrTargetRemote({
  options,
  projectRemoteName,
  selectedRemoteName,
  fallbackRepositoryUrl,
}: {
  options: ReadonlyArray<TargetRemote>;
  /** The effective base remote from the blessed resolver; null when the repository has none. */
  projectRemoteName: string | null;
  selectedRemoteName?: string;
  fallbackRepositoryUrl?: string;
}): TargetRemote | undefined {
  const selected = selectedRemoteName
    ? options.find((option) => option.remote.name === selectedRemoteName)
    : undefined;
  if (selected) return selected;

  const projectRemote =
    projectRemoteName !== null
      ? options.find((option) => option.remote.name === projectRemoteName)
      : undefined;
  if (projectRemote) return projectRemote;

  const fallbackRepository = parseRepositoryRef(fallbackRepositoryUrl);
  if (fallbackRepository) {
    const fallback = options.find(
      (option) => option.repository.repositoryUrl === fallbackRepository.repositoryUrl
    );
    if (fallback) return fallback;
  }

  return options[0];
}
