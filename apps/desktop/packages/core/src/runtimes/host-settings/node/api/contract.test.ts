import { promises as fs } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { remote, snapshot } from '@emdash/wire/state';
import { createTestWire, type TestWire } from '@emdash/wire/testing';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { hostSettingsContract } from '#runtimes/host-settings/api';
import { HostSettingsRuntime } from '#runtimes/host-settings/node/runtime';
import { createHostSettingsController } from './controller';

async function eventually(assertion: () => void | Promise<void>, timeoutMs = 5_000): Promise<void> {
  const started = Date.now();
  for (;;) {
    try {
      await assertion();
      return;
    } catch (error) {
      if (Date.now() - started > timeoutMs) throw error;
      await new Promise((resolve) => setTimeout(resolve, 50));
    }
  }
}

// Contract-seam tests for the host-settings runtime: get/update round-trips,
// live-model updates on out-of-band file edits, lenient handling of a broken
// file, and unknown-key preservation on update (forward compatibility).
describe('host settings contract', () => {
  let root: string;
  let settingsPath: string;
  let runtime: HostSettingsRuntime;
  let wire: TestWire<typeof hostSettingsContract>;

  beforeEach(async () => {
    root = await fs.mkdtemp(path.join(os.tmpdir(), 'host-settings-'));
    settingsPath = path.join(root, 'data', 'host-settings.json');
    runtime = new HostSettingsRuntime({ settingsPath });
    wire = createTestWire(hostSettingsContract, createHostSettingsController(runtime));
  });

  afterEach(async () => {
    wire.dispose();
    runtime.dispose();
    await fs.rm(root, { recursive: true, force: true });
  });

  async function currentState() {
    const state = remote(hostSettingsContract.state, wire.client.state);
    const model = state(undefined);
    try {
      await model.states.current.refresh();
      return snapshot(model.states.current).value;
    } finally {
      await state.dispose();
    }
  }

  it('get returns empty defaults when no file exists', async () => {
    const result = await wire.client.get();
    expect(result).toEqual({ success: true, data: { settings: {}, parseError: false } });
  });

  it('update round-trips through get, the live model, and the file on disk', async () => {
    const updated = await wire.client.update({ shellSetup: 'source ~/.nvm/nvm.sh', tmux: true });
    expect(updated).toEqual({
      success: true,
      data: {
        settings: { shellSetup: 'source ~/.nvm/nvm.sh', tmux: true },
        parseError: false,
      },
    });

    const got = await wire.client.get();
    expect(got.success && got.data.settings.shellSetup).toBe('source ~/.nvm/nvm.sh');
    expect(await currentState()).toEqual({
      settings: { shellSetup: 'source ~/.nvm/nvm.sh', tmux: true },
      parseError: false,
    });

    const onDisk = JSON.parse(await fs.readFile(settingsPath, 'utf8')) as Record<string, unknown>;
    expect(onDisk).toEqual({ shellSetup: 'source ~/.nvm/nvm.sh', tmux: true });
  });

  it('update writes watcherExclude and round-trips through get and the file', async () => {
    const patterns = ['**/node_modules/**', '**/.cache/**'];
    const updated = await wire.client.update({ watcherExclude: patterns });
    expect(updated).toEqual({
      success: true,
      data: { settings: { watcherExclude: patterns }, parseError: false },
    });

    const got = await wire.client.get();
    expect(got).toEqual({
      success: true,
      data: { settings: { watcherExclude: patterns }, parseError: false },
    });

    const onDisk = JSON.parse(await fs.readFile(settingsPath, 'utf8')) as Record<string, unknown>;
    expect(onDisk).toEqual({ watcherExclude: patterns });
  });

  it('watcherExclude keeps an empty array distinct from unset (null clears)', async () => {
    await wire.client.update({ watcherExclude: [] });
    const afterEmpty = await wire.client.get();
    expect(afterEmpty).toEqual({
      success: true,
      data: { settings: { watcherExclude: [] }, parseError: false },
    });

    await wire.client.update({ watcherExclude: null });
    const afterClear = await wire.client.get();
    expect(afterClear).toEqual({
      success: true,
      data: { settings: {}, parseError: false },
    });
  });

  it('null clears a field; absent fields stay untouched', async () => {
    await wire.client.update({ shellSetup: 'setup', worktreeRoot: '/worktrees', tmux: false });
    const result = await wire.client.update({ shellSetup: null });
    expect(result).toEqual({
      success: true,
      data: { settings: { worktreeRoot: '/worktrees', tmux: false }, parseError: false },
    });
  });

  it('preserves unknown keys in the file across updates', async () => {
    await fs.mkdir(path.dirname(settingsPath), { recursive: true });
    await fs.writeFile(
      settingsPath,
      JSON.stringify({ shellSetup: 'old', futureSetting: { nested: 1 } }),
      'utf8'
    );

    const result = await wire.client.update({ shellSetup: 'new' });
    expect(result.success).toBe(true);

    const onDisk = JSON.parse(await fs.readFile(settingsPath, 'utf8')) as Record<string, unknown>;
    expect(onDisk).toEqual({ shellSetup: 'new', futureSetting: { nested: 1 } });
  });

  it('an out-of-band file edit shows up in the live model without a verb call', async () => {
    await fs.mkdir(path.dirname(settingsPath), { recursive: true });
    await fs.writeFile(settingsPath, JSON.stringify({ worktreeRoot: '/external' }), 'utf8');

    await eventually(async () => {
      expect(await currentState()).toEqual({
        settings: { worktreeRoot: '/external' },
        parseError: false,
      });
    });
  });

  it('a present-but-broken file degrades to defaults with parseError set', async () => {
    await fs.mkdir(path.dirname(settingsPath), { recursive: true });
    await fs.writeFile(settingsPath, '{not json', 'utf8');

    await eventually(async () => {
      expect(await currentState()).toEqual({ settings: {}, parseError: true });
    });

    // An update replaces the broken file and recovers.
    const result = await wire.client.update({ tmux: true });
    expect(result).toEqual({
      success: true,
      data: { settings: { tmux: true }, parseError: false },
    });
  });
});
