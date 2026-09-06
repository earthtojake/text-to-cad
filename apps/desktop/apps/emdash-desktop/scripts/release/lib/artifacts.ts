import { copyFileSync, readdirSync } from 'node:fs';
import { basename, join } from 'node:path';
import { ARTIFACT_PREFIX, RELEASE_DIR, UPDATE_CHANNEL } from './config.ts';

function matchFiles(pattern: RegExp, dir = RELEASE_DIR): string[] {
  try {
    return readdirSync(dir)
      .filter((f) => pattern.test(f))
      .map((f) => join(dir, f));
  } catch {
    return [];
  }
}

export function findManifests(channel = UPDATE_CHANNEL, dir = RELEASE_DIR): string[] {
  return matchFiles(new RegExp(`^${channel}.*\\.yml$`), dir);
}

export function findInstallers(prefix = ARTIFACT_PREFIX): string[] {
  return matchFiles(new RegExp(`^${prefix}-.*\\.(dmg|zip|exe|msi|AppImage|deb|rpm)$`));
}

export function findBlockmaps(): string[] {
  return matchFiles(/\.blockmap$/);
}

export function findArtifacts(patterns: string[]): string[] {
  const combined = new RegExp(patterns.map((p) => `(?:${p})`).join('|'));
  return matchFiles(combined);
}

/**
 * Copies each `${sourceChannel}*.yml` in `dir` to a `${targetChannel}*.yml` sibling,
 * returning the paths of the newly created files. No-op when the channels are equal.
 *
 * This is used to produce `v1-stable*.yml` (R2 feed) from `latest*.yml` (GitHub feed)
 * without running a second electron-builder pass — the manifests are identical in content,
 * differing only in filename.
 */
export function duplicateChannelManifests(
  sourceChannel: string,
  targetChannel: string,
  dir = RELEASE_DIR
): string[] {
  if (sourceChannel === targetChannel) return [];
  const sources = findManifests(sourceChannel, dir);
  const created: string[] = [];
  for (const src of sources) {
    const srcName = basename(src);
    const targetName = srcName.replace(sourceChannel, targetChannel);
    const targetPath = join(dir, targetName);
    copyFileSync(src, targetPath);
    created.push(targetPath);
  }
  return created;
}

type PublishEntry = Record<string, unknown> | string;

/**
 * Derives the GitHub and R2 update channels from the electron-builder publish array.
 * - `githubChannel`: the `channel` field of the first `provider: 'github'` entry (default `'latest'`).
 * - `r2Channel`: the `channel` field of the first `provider: 'generic'` entry (`undefined` if absent).
 */
export function resolvePublishChannels(publish: PublishEntry[]): {
  githubChannel: string;
  r2Channel: string | undefined;
} {
  const entries = publish.filter((p): p is Record<string, unknown> => typeof p !== 'string');
  const github = entries.find((p) => p['provider'] === 'github');
  const generic = entries.find((p) => p['provider'] === 'generic');
  return {
    githubChannel: typeof github?.['channel'] === 'string' ? github['channel'] : 'latest',
    r2Channel: typeof generic?.['channel'] === 'string' ? generic['channel'] : undefined,
  };
}
