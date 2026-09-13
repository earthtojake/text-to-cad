import { readFileSync } from 'node:fs';

export type ReleaseChannel = 'stable' | 'canary';

export interface ReleaseVersion {
  version: string;
  tag: string;
  isCanary: boolean;
}

/**
 * Derives the version and git tag for a release.
 *
 * Stable: uses package.json version verbatim (e.g. 1.1.32 → v1.1.32).
 *
 * Canary: increments the patch segment and appends a -canary.<run> prerelease
 * suffix (e.g. 1.1.32 → 1.1.33-canary.42 → v1.1.33-canary.42). This ensures
 * canary versions always rank above any already-installed stable or canary build
 * at the same base, satisfying electron-updater's allowDowngrade=false constraint.
 *
 * GITHUB_RUN_NUMBER is monotonic and identical across all jobs in a workflow run,
 * so build.ts and finalize-release.ts compute the same tag independently.
 */
export function resolveReleaseVersion(channel: ReleaseChannel): ReleaseVersion {
  const pkg = JSON.parse(readFileSync('package.json', 'utf-8')) as { version: string };

  if (channel === 'canary') {
    const base = pkg.version.split('-')[0];
    const parts = base.split('.').map(Number);
    if (parts.length !== 3 || parts.some(Number.isNaN)) {
      throw new Error(`Cannot parse package.json version "${pkg.version}" as major.minor.patch`);
    }
    const [maj, min, pat] = parts;
    const nextBase = `${maj}.${min}.${pat + 1}`;
    const run = process.env.GITHUB_RUN_NUMBER ?? '0';
    const version = `${nextBase}-canary.${run}`;
    return { version, tag: `v${version}`, isCanary: true };
  }

  return { version: pkg.version, tag: `v${pkg.version}`, isCanary: false };
}
