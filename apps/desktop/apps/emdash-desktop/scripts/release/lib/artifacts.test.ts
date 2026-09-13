import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { duplicateChannelManifests, findManifests, resolvePublishChannels } from './artifacts.ts';

describe('duplicateChannelManifests', () => {
  let dir: string;

  beforeEach(() => {
    dir = mkdtempSync(join(tmpdir(), 'artifacts-test-'));
  });

  afterEach(() => {
    rmSync(dir, { recursive: true, force: true });
  });

  it('copies latest*.yml to v1-stable*.yml', () => {
    const content = 'version: 1.1.34\nfiles: []\n';
    writeFileSync(join(dir, 'latest-mac.yml'), content);
    writeFileSync(join(dir, 'latest-linux.yml'), content);
    writeFileSync(join(dir, 'latest.yml'), content);

    const created = duplicateChannelManifests('latest', 'v1-stable', dir);

    expect(created).toHaveLength(3);
    const names = created
      .map((f) => f.split('/').pop())
      .sort((a, b) => (a ?? '').localeCompare(b ?? ''));
    expect(names).toEqual(['v1-stable-linux.yml', 'v1-stable-mac.yml', 'v1-stable.yml']);
  });

  it('created files have identical content to sources', () => {
    const content = 'version: 1.2.0\nfiles:\n  - url: emdash-arm64.zip\n';
    writeFileSync(join(dir, 'latest-mac.yml'), content);

    duplicateChannelManifests('latest', 'v1-stable', dir);

    const copied = readFileSync(join(dir, 'v1-stable-mac.yml'), 'utf-8');
    expect(copied).toBe(content);
  });

  it('returns empty array when sourceChannel equals targetChannel', () => {
    writeFileSync(join(dir, 'latest-mac.yml'), 'version: 1.0.0\n');
    const created = duplicateChannelManifests('latest', 'latest', dir);
    expect(created).toHaveLength(0);
  });

  it('returns empty array when no source manifests exist', () => {
    const created = duplicateChannelManifests('latest', 'v1-stable', dir);
    expect(created).toHaveLength(0);
  });

  it('does not copy non-yml files', () => {
    writeFileSync(join(dir, 'latest-mac.yml'), 'version: 1.0.0\n');
    writeFileSync(join(dir, 'latest-mac.dmg'), 'binary');

    const created = duplicateChannelManifests('latest', 'v1-stable', dir);
    expect(created).toHaveLength(1);
    expect(created[0]).toMatch(/v1-stable-mac\.yml$/);
  });

  it('handles canary channel duplication', () => {
    writeFileSync(join(dir, 'canary-mac.yml'), 'version: 1.1.34-canary.10\n');
    writeFileSync(join(dir, 'canary-linux.yml'), 'version: 1.1.34-canary.10\n');
    writeFileSync(join(dir, 'canary.yml'), 'version: 1.1.34-canary.10\n');

    const created = duplicateChannelManifests('canary', 'v1-canary', dir);

    expect(created).toHaveLength(3);
    const names = created
      .map((f) => f.split('/').pop())
      .sort((a, b) => (a ?? '').localeCompare(b ?? ''));
    expect(names).toEqual(['v1-canary-linux.yml', 'v1-canary-mac.yml', 'v1-canary.yml']);
  });
});

describe('resolvePublishChannels', () => {
  it('extracts github and generic channels', () => {
    const publish = [
      { provider: 'github', owner: 'org', repo: 'repo', channel: 'latest' },
      { provider: 'generic', url: 'https://example.com', channel: 'v1-stable' },
    ];
    const { githubChannel, r2Channel } = resolvePublishChannels(publish);
    expect(githubChannel).toBe('latest');
    expect(r2Channel).toBe('v1-stable');
  });

  it('defaults github channel to "latest" when not specified', () => {
    const publish = [
      { provider: 'github', owner: 'org', repo: 'repo' },
      { provider: 'generic', url: 'https://example.com', channel: 'v1-stable' },
    ];
    const { githubChannel } = resolvePublishChannels(publish);
    expect(githubChannel).toBe('latest');
  });

  it('returns r2Channel undefined when no generic provider present', () => {
    const publish = [{ provider: 'github', owner: 'org', repo: 'repo', channel: 'latest' }];
    const { r2Channel } = resolvePublishChannels(publish);
    expect(r2Channel).toBeUndefined();
  });

  it('handles canary config', () => {
    const publish = [
      { provider: 'github', owner: 'org', repo: 'repo', channel: 'canary' },
      { provider: 'generic', url: 'https://example.com', channel: 'v1-canary' },
    ];
    const { githubChannel, r2Channel } = resolvePublishChannels(publish);
    expect(githubChannel).toBe('canary');
    expect(r2Channel).toBe('v1-canary');
  });

  it('skips string entries in the publish array', () => {
    const publish = [
      'github',
      { provider: 'generic', url: 'https://example.com', channel: 'v1-stable' },
    ];
    const { githubChannel, r2Channel } = resolvePublishChannels(publish);
    expect(githubChannel).toBe('latest');
    expect(r2Channel).toBe('v1-stable');
  });

  it('returns undefined r2Channel when generic channel is not a string', () => {
    const publish = [
      { provider: 'github', channel: 'latest' },
      { provider: 'generic', channel: 42 },
    ];
    const { r2Channel } = resolvePublishChannels(publish);
    expect(r2Channel).toBeUndefined();
  });
});

describe('findManifests with missing-manifest guard scenario', () => {
  let dir: string;

  beforeEach(() => {
    dir = mkdtempSync(join(tmpdir(), 'artifacts-guard-test-'));
  });

  afterEach(() => {
    rmSync(dir, { recursive: true, force: true });
  });

  it('returns empty array when channel manifests are absent (guard trigger condition)', () => {
    // Simulate the state where build emits latest*.yml but v1-stable*.yml was not duplicated.
    writeFileSync(join(dir, 'latest-mac.yml'), 'version: 1.1.33\n');
    writeFileSync(join(dir, 'emdash-arm64.dmg'), 'binary');

    const missing = findManifests('v1-stable', dir);
    expect(missing).toHaveLength(0);

    // upload-r2.ts: `if (manifests.length === 0) fail(...)` catches this.
  });

  it('returns manifests when channel has been correctly duplicated', () => {
    writeFileSync(join(dir, 'latest-mac.yml'), 'version: 1.1.34\n');
    duplicateChannelManifests('latest', 'v1-stable', dir);

    const found = findManifests('v1-stable', dir);
    expect(found).toHaveLength(1);
    expect(found[0]).toMatch(/v1-stable-mac\.yml$/);
  });
});
