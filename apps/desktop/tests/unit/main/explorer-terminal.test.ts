import { beforeEach, expect, it, vi } from 'vitest';
import { SCROLLBACK_BYTES, Terminals, type TerminalEvent } from '@main/explorer/terminal';

const spawn = vi.hoisted(() => vi.fn());
vi.mock('node-pty', () => ({ spawn }));
function fixture() {
  let data: (text: string) => void = () => {};
  let exit: (result: { exitCode: number; signal?: number }) => void = () => {};
  const process = { write: vi.fn(), kill: vi.fn(), resize: vi.fn(),
    onData: (listener: typeof data) => { data = listener; }, onExit: (listener: typeof exit) => { exit = listener; } };
  spawn.mockReturnValue(process);
  const events: TerminalEvent[] = [];
  const terminals = new Terminals(event => events.push(event));
  return { terminals, process, events, data: (text: string) => data(text), exit: (code: number) => exit({ exitCode: code }) };
}
beforeEach(() => spawn.mockReset());
it('reads only output after its cursor and caps the returned tail with explicit truncation', async () => {
  const f = fixture(); const { id } = await f.terminals.create({ cwd: '/project', projectId: 'p' });
  f.data('one'); f.data('two'); f.data('three');
  expect(f.terminals.read(id, 1)).toMatchObject({ data: 'twothree', sequence: 3, truncated: false });
  expect(f.terminals.read(id, 1, 4)).toMatchObject({ data: 'hree', sequence: 3, truncated: true });
  expect(f.terminals.read(id, 3)).toMatchObject({ data: '', truncated: false });
  expect(() => f.terminals.read(id, 4)).toThrow('ahead');
  expect(f.events.map(event => event.type === 'data' ? event.seq : null)).toEqual([1, 2, 3]);
});
it('bounds UTF8 scrollback and reports a partially discarded first chunk', async () => {
  const f = fixture(); const { id } = await f.terminals.create({ cwd: '/project' });
  f.data('é'.repeat(SCROLLBACK_BYTES));
  const retained = f.terminals.attach(id)!;
  expect(Buffer.byteLength(retained.scrollback)).toBeLessThanOrEqual(SCROLLBACK_BYTES);
  expect(retained.scrollback).not.toContain('\ufffd');
  expect(f.terminals.read(id, 0, SCROLLBACK_BYTES)).toMatchObject({ sequence: 1, truncated: true });
  expect(f.terminals.read(id, 1)).toMatchObject({ data: '', truncated: false });
  f.data('next');
  expect(f.terminals.read(id, 0)).toMatchObject({ data: 'next', sequence: 2, truncated: true });
  expect(f.terminals.read(id, 1)).toMatchObject({ data: 'next', truncated: false });
});
it('guards against new output, completed user input and unfinished user input independently', async () => {
  const f = fixture(); const { id } = await f.terminals.create({ cwd: '/project' });
  f.data('$ ');
  f.terminals.write(id, 'user command\n');
  expect(() => f.terminals.writeGuarded(id, 'agent\n', 1, 0)).toThrow('changed');
  f.terminals.write(id, 'unfinished');
  const pending = f.terminals.read(id);
  expect(() => f.terminals.writeGuarded(id, 'agent\n', pending.sequence, pending.inputRevision)).toThrow('unfinished');
  f.terminals.write(id, '\x03still unfinished');
  expect(f.terminals.read(id).inputPending).toBe(true);
  f.terminals.write(id, '\x03');
  const ready = f.terminals.read(id); f.data('new output');
  expect(() => f.terminals.writeGuarded(id, 'agent\n', ready.sequence, ready.inputRevision)).toThrow('changed');
  const latest = f.terminals.read(id);
  f.terminals.writeGuarded(id, 'agent\n', latest.sequence, latest.inputRevision);
  expect(f.process.write).toHaveBeenLastCalledWith('agent\n');
  expect(f.terminals.read(id)).toMatchObject({ inputRevision: latest.inputRevision + 1, inputPending: false });
});
it('stops a PTY while retaining output, then removes its identity only when the tab closes', async () => {
  const f = fixture(); const { id } = await f.terminals.create({ cwd: '/project', projectId: 'shared-directory', sessionId: 'owner' });
  f.data('result');
  expect(f.terminals.owns(id, 'owner')).toBe(true); expect(f.terminals.owns(id, 'other')).toBe(false);
  f.terminals.stop(id); expect(f.process.kill).toHaveBeenCalledOnce(); f.exit(143);
  expect(f.terminals.read(id)).toMatchObject({ data: 'result', info: { exitCode: 143 } });
  expect(() => f.terminals.writeGuarded(id, 'x\n', 1, 0)).toThrow('no longer running');
  f.terminals.kill(id); expect(f.process.kill).toHaveBeenCalledOnce();
  expect(f.terminals.owns(id, 'owner')).toBe(false); expect(f.terminals.attach(id)).toBeNull();
  expect(() => f.terminals.read(id)).toThrow('no longer exists');
});
