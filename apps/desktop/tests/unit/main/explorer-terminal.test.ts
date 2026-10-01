import { beforeEach, expect, it, vi } from 'vitest';
import { SCROLLBACK_BYTES, Terminals, terminalEnv, type TerminalEvent } from '@main/explorer/terminal';

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
it('lets the agent send its answer and then the newline as two guarded writes', async () => {
  const f = fixture(); const { id } = await f.terminals.create({ cwd: '/project' });
  f.data('Continue? [y/N] ');
  const before = f.terminals.read(id);
  f.terminals.writeGuarded(id, 'y', before.sequence, before.inputRevision);
  const after = f.terminals.read(id);
  expect(after.inputPending).toBe(false);
  expect(() => f.terminals.writeGuarded(id, '\n', after.sequence, after.inputRevision)).not.toThrow();
  expect(f.process.write).toHaveBeenLastCalledWith('\n');
});
it('passes the widget\'s replies to a program\'s queries through without counting them as typing', async () => {
  const f = fixture(); const { id } = await f.terminals.create({ cwd: '/project' });
  f.data('$ ');
  const before = f.terminals.read(id);
  // Device attributes, a cursor position report, focus in, a background colour answer.
  for (const reply of ['\x1b[?1;2c', '\x1b[12;40R', '\x1b[I', '\x1b]11;rgb:0a0a/0a0a/0a0a\x1b\\']) f.terminals.write(id, reply);
  expect(f.process.write).toHaveBeenLastCalledWith('\x1b]11;rgb:0a0a/0a0a/0a0a\x1b\\');
  expect(f.terminals.read(id)).toMatchObject({ inputRevision: before.inputRevision, inputPending: false });
  f.terminals.writeGuarded(id, 'ls\n', before.sequence, before.inputRevision);
  // An arrow key is the person, and still counts.
  f.terminals.write(id, '\x1b[A');
  expect(f.terminals.read(id).inputPending).toBe(true);
});
it('gives a shell none of a host Claude Code session\'s variables, so a nested claude is not logged out', () => {
  const env = terminalEnv({ PATH: '/bin', HOME: '/home/me', CLAUDECODE: '1', CLAUDE_CODE_ENTRYPOINT: 'cli',
    CLAUDE_CODE_SSE_PORT: '1234', ANTHROPIC_BASE_URL: 'http://127.0.0.1:1', ELECTRON_RUN_AS_NODE: '1' });
  expect(Object.keys(env).filter(key => /^(CLAUDE|ANTHROPIC_BASE_URL|ELECTRON_)/.test(key))).toEqual([]);
  expect(env).toMatchObject({ PATH: '/bin', HOME: '/home/me' });
});
