import { err, ok, type Result } from '@emdash/shared';
import {
  parseRepositoryRef,
  type RepositoryRef,
  type RepositoryRefParseError,
} from '@core/primitives/repository/api';
import {
  githubHostService,
  type GitHubHostProbeError,
  type GitHubHostService,
} from '../../../node/services/github-host-service';

export type GitHubResolveError =
  | { type: 'not_parseable'; error: RepositoryRefParseError }
  | GitHubHostProbeError;

export type GitHubResolveResult = Result<RepositoryRef, GitHubResolveError>;

export class GitHubRepositoryResolver {
  constructor(private readonly hostService: Pick<GitHubHostService, 'probe'> = githubHostService) {}

  async resolve(input: string | null | undefined): Promise<GitHubResolveResult> {
    const raw = input ?? '';
    const ref = parseRepositoryRef(raw, { defaultHost: 'github.com' });
    if (!ref)
      return err({
        type: 'not_parseable',
        error: { type: 'invalid-repository-ref', input: raw },
      });

    const probe = await this.hostService.probe(ref.host);
    if (!probe.success) return err(probe.error);
    return ok(ref);
  }
}

export const githubRepositoryResolver = new GitHubRepositoryResolver();
