import { describe, expect, it } from 'vitest';
import { sshConnectionMetadata } from './ssh-connection-metadata';

// Migration tests for the versioned SSH connection metadata chain, per the
// versioned-schema conventions: every stored shape must upgrade to the latest
// version without data loss.
describe('sshConnectionMetadata versioned schema', () => {
  it('parses an unversioned v0 object and upgrades it to the latest version', () => {
    const result = sshConnectionMetadata.safeParse({
      sshConfigAlias: 'my-host',
      forwardAgent: true,
      proxyJump: 'jump-host',
    });
    expect(result.status).toBe('ok');
    if (result.status !== 'ok') return;
    expect(result.data.sshConfigAlias).toBe('my-host');
    expect(result.data.forwardAgent).toBe(true);
    expect(result.data.proxyJump).toBe('jump-host');
    // v4's field defaults to unset (treated as false by readers).
    expect(result.data.syncLocalSettings).toBeUndefined();
    expect(result.data.version).toBe(sshConnectionMetadata.currentVersion);
  });

  it('upgrades v3 data to v4 preserving dependency selections', () => {
    const result = sshConnectionMetadata.safeParse({
      version: '3',
      sshConfigAlias: 'my-host',
      dependencySelections: {
        claude: { kind: 'pinned', realpath: '/usr/local/bin/claude' },
        codex: null,
      },
    });
    expect(result.status).toBe('ok');
    if (result.status !== 'ok') return;
    expect(result.data.version).toBe('4');
    expect(result.data.dependencySelections).toEqual({
      claude: { kind: 'pinned', realpath: '/usr/local/bin/claude' },
      codex: null,
    });
    expect(result.data.syncLocalSettings).toBeUndefined();
  });

  it('round-trips a v4 object with syncLocalSettings through serialize/parseJson', () => {
    const value = sshConnectionMetadata.schema.parse({
      version: '4',
      sshConfigAlias: 'my-host',
      syncLocalSettings: true,
    });
    const roundTripped = sshConnectionMetadata.parseJson(sshConnectionMetadata.serialize(value));
    expect(roundTripped).toEqual(value);
    expect(roundTripped?.syncLocalSettings).toBe(true);
  });

  it('keeps syncLocalSettings false-y for shapes written before v4', () => {
    for (const stored of [
      {},
      { version: '1', dependencySelections: { claude: { path: '/bin/claude' } } },
      { version: '2', dependencySelections: { claude: { kind: 'path', path: '/bin/claude' } } },
    ]) {
      const result = sshConnectionMetadata.safeParse(stored);
      expect(result.status).toBe('ok');
      if (result.status !== 'ok') continue;
      expect(result.data.syncLocalSettings ?? false).toBe(false);
    }
  });
});
