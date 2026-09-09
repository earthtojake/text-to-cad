import type { ContractClient } from '@emdash/wire/rpc';
import { domainClient } from '@core/primitives/wire/browser/connection';
import { githubContract, githubDomain } from '../contract';

export type GithubClient = ContractClient<typeof githubContract>;

export function getGithubClient(): Promise<GithubClient> {
  return domainClient<GithubClient>(githubDomain, githubContract);
}
