import { DEFAULT_SEARCH_EXCLUDE, ExclusionPolicy } from '#primitives/exclusion-policy/api';
import type { PortableRelativePath } from '#primitives/path/api';

/** One semantic exclusion policy compiled for scanners, watchers, and ripgrep. */
export interface FileSearchExclusions {
  excludes(path: PortableRelativePath): boolean;
  ripgrepGlobs(): readonly string[];
  watchIgnoreGlobs(): readonly string[];
}

export class DefaultFileSearchExclusions implements FileSearchExclusions {
  private readonly policy: ExclusionPolicy;

  constructor(options: { caseSensitive?: boolean; patterns?: readonly string[] } = {}) {
    this.policy = new ExclusionPolicy(options.patterns ?? DEFAULT_SEARCH_EXCLUDE, {
      caseSensitive: options.caseSensitive,
    });
  }

  excludes(path: PortableRelativePath): boolean {
    return this.policy.excludes(path);
  }

  ripgrepGlobs(): readonly string[] {
    return this.policy.ripgrepGlobs();
  }

  watchIgnoreGlobs(): readonly string[] {
    return this.policy.watchIgnoreGlobs();
  }
}
