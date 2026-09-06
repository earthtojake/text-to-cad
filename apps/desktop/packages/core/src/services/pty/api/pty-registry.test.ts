import { describe, expect, it, vi } from 'vitest';
import { FakePtySpawner } from '#services/pty/testing';
import { PtyRegistry } from './pty-registry';
import type { PtySpawnSpec } from './types';

const spec: PtySpawnSpec = {
  command: 'claude',
  args: ['auth', 'login'],
  cwd: '/tmp',
  env: { PATH: '/bin' },
  cols: 120,
  rows: 30,
};

describe('PtyRegistry', () => {
  it('spawns a session and streams output into a LiveLogSource', async () => {
    const spawner = new FakePtySpawner();
    const registry = new PtyRegistry(spawner);

    const session = await registry.create('auth:claude', spec);
    spawner.processes[0]!.emitData('hello');
    spawner.processes[0]!.emitData(' world');

    expect(spawner.specs).toEqual([spec]);
    expect(registry.get('auth:claude')).toBe(session);
    expect(registry.getLog('auth:claude')?.snapshot().data.text).toBe('hello world');
  });

  it('forwards input, resize, and kill to the process', async () => {
    const spawner = new FakePtySpawner();
    const registry = new PtyRegistry(spawner);

    await registry.create('auth:claude', spec);
    registry.write('auth:claude', 'abc');
    registry.resize('auth:claude', 80, 24);
    registry.kill('auth:claude');

    expect(spawner.processes[0]!.writes).toEqual(['abc']);
    expect(spawner.processes[0]!.resizes).toEqual([{ cols: 80, rows: 24 }]);
    expect(spawner.processes[0]!.killCount).toBeGreaterThan(0);
  });

  it('tracks exit status and notifies registry changes', async () => {
    const spawner = new FakePtySpawner();
    const onSessionChanged = vi.fn();
    const registry = new PtyRegistry(spawner, { onSessionChanged });

    const session = await registry.create('auth:claude', spec);
    spawner.processes[0]!.emitExit({ exitCode: 0, signal: null });

    expect(session.exitStatus).toEqual({ exitCode: 0, signal: null });
    expect(onSessionChanged).toHaveBeenLastCalledWith('auth:claude', session);
  });

  it('replaces an existing session by default', async () => {
    const spawner = new FakePtySpawner();
    const registry = new PtyRegistry(spawner);

    await registry.create('auth:claude', spec);
    await registry.create('auth:claude', { ...spec, args: [] });

    expect(spawner.processes[0]!.killCount).toBeGreaterThan(0);
    expect(spawner.processes).toHaveLength(2);
    expect(registry.get('auth:claude')?.spec.args).toEqual([]);
  });
});
