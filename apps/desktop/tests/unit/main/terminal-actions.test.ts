import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { RendererCommands } from '@main/integrations/actions';
import { createTerminalActions } from '@main/integrations/terminals/actions';
import { Terminals } from '@main/explorer/terminal';
import type { BridgeSession } from '@main/integrations/mcp-bridge';
import type { IntegrationCommand } from '@shared/ipc/integrations';

const spawn = vi.hoisted(() => vi.fn());
vi.mock('node-pty', () => ({ spawn }));
let directory: string;
const relays: RendererCommands[] = [];
beforeEach(async () => { directory = await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(), 'hardcore-terminal-actions-'))); spawn.mockReset(); });
afterEach(async () => { for (const relay of relays.splice(0)) relay.dispose(); await fs.rm(directory, { recursive: true, force: true }); });
function fixture() {
  const process = { write: vi.fn(), kill: vi.fn(), resize: vi.fn(), onData: vi.fn(), onExit: vi.fn() };
  spawn.mockReturnValue(process);
  const terminals = new Terminals(() => {});
  const sent: IntegrationCommand[] = [];
  const session: BridgeSession = { sessionId: 's', projectId: 'project', cwd: directory };
  let answer: unknown = { id: 'tab', kind: 'terminal', root: directory };
  let refusal = ''; let paused = false; let sequence = 0;
  const deps = { sessionRoot: () => ({ directory, root: directory }), newId: () => `r${++sequence}`,
    send(command: IntegrationCommand) { sent.push(command); if (!paused) relay.reply(refusal ? { requestId: command.requestId, ok: false, error: refusal } : { requestId: command.requestId, ok: true, result: answer }); } };
  const relay = new RendererCommands(deps); relays.push(relay);
  return { session, terminals, process, sent, actions: createTerminalActions(deps, relay, () => terminals),
    answer: (value: unknown) => { answer = value; }, refuse: (value: string) => { refusal = value; }, pause: () => { paused = true; } };
}
it('creates a PTY in authenticated cwd and relays its project-owned identity to the scoped tab', async () => {
  const f = fixture(); await fs.mkdir(path.join(directory, 'nested'));
  await f.actions.create_terminal!(f.session, { cwd: 'nested' });
  const info = f.terminals.list()[0]!;
  expect(info.cwd).toBe(path.join(directory, 'nested'));
  expect(f.terminals.owns(info.id, 'project')).toBe(true);
  expect(f.sent[0]).toMatchObject({ kind: 'terminal-open', projectId: 'project', root: directory, rootDirectory: directory, params: { cwd: info.cwd, ptyId: info.id } });
  f.terminals.killAll();
});
it('refuses outside or file cwd paths before spawning', async () => {
  const f = fixture(); await fs.writeFile(path.join(directory, 'file'), 'x');
  await expect(f.actions.create_terminal!(f.session, { cwd: '..' })).rejects.toThrow('outside');
  await expect(f.actions.create_terminal!(f.session, { cwd: 'file' })).rejects.toThrow('directory');
  expect(spawn).not.toHaveBeenCalled(); expect(f.sent).toEqual([]);
});
it('requires a scoped terminal tab and project-owned PTY before read, write or stop', async () => {
  const f = fixture(); const info = await f.terminals.create({ cwd: directory, projectId: 'other' });
  f.answer({ id: 'tab', kind: 'terminal', root: directory, ptyId: info.id });
  await expect(f.actions.read_terminal!(f.session, { tabId: 'tab' })).rejects.toThrow('app-owned');
  f.answer({ id: 'tab', kind: 'browser', root: directory, ptyId: info.id });
  await expect(f.actions.write_terminal!(f.session, { tabId: 'tab', data: 'command\n', expectedSequence: 0, expectedInputRevision: 0 })).rejects.toThrow('app-owned');
  f.refuse('that tab belongs to another workspace');
  await expect(f.actions.stop_terminal!(f.session, { tabId: 'tab' })).rejects.toThrow('another workspace');
  expect(f.sent.every(command => command.kind === 'tab-resource' && command.projectId === 'project' && command.root === directory)).toBe(true);
  expect(f.process.write).not.toHaveBeenCalled(); expect(f.process.kill).not.toHaveBeenCalled(); f.terminals.killAll();
});
it('honors cursor limits and guarded input and leaves stopped output available', async () => {
  const f = fixture(); const info = await f.terminals.create({ cwd: directory, projectId: 'project' });
  f.answer({ id: 'tab', kind: 'terminal', root: directory, ptyId: info.id });
  const onData = f.process.onData.mock.calls[0]![0] as (text: string) => void;
  onData('older'); onData('newer');
  expect(await f.actions.read_terminal!(f.session, { tabId: 'tab', after: 1, limit: 3 })).toMatchObject({ data: 'wer', sequence: 2, truncated: true });
  await expect(f.actions.write_terminal!(f.session, { tabId: 'tab', data: 'x\n', expectedSequence: 1, expectedInputRevision: 0 })).rejects.toThrow('changed');
  expect(await f.actions.write_terminal!(f.session, { tabId: 'tab', data: 'x\n', expectedSequence: 2, expectedInputRevision: 0 })).toMatchObject({ inputRevision: 1 });
  expect(f.process.write).toHaveBeenCalledExactlyOnceWith('x\n');
  expect(await f.actions.stop_terminal!(f.session, { tabId: 'tab' })).toEqual({ stopped: true, id: info.id });
  (f.process.onExit.mock.calls[0]![0] as (event: { exitCode: number }) => void)({ exitCode: 143 });
  expect(await f.actions.read_terminal!(f.session, { tabId: 'tab' })).toMatchObject({ data: 'oldernewer', info: { exitCode: 143 } });
  expect(f.terminals.list()).toHaveLength(1); f.terminals.killAll();
});
it('cleans up spawned PTYs when tab creation refuses or is aborted', async () => {
  const f = fixture(); f.refuse('workspace closed');
  await expect(f.actions.create_terminal!(f.session, {})).rejects.toThrow('workspace closed');
  expect(f.terminals.list()).toEqual([]); expect(f.process.kill).toHaveBeenCalledOnce();
  const abort = new AbortController(); f.pause();
  const pending = f.actions.create_terminal!(f.session, {}, abort.signal);
  await vi.waitFor(() => expect(f.sent).toHaveLength(2)); abort.abort(new Error('cancelled'));
  await expect(pending).rejects.toThrow('cancelled');
  expect(f.terminals.list()).toEqual([]); expect(f.process.kill).toHaveBeenCalledTimes(2);
});
it('does not spawn for an already-aborted creation request', async () => {
  const f = fixture(); const abort = new AbortController(); abort.abort(new Error('cancelled'));
  await expect(f.actions.create_terminal!(f.session, {}, abort.signal)).rejects.toThrow('cancelled');
  expect(spawn).not.toHaveBeenCalled(); expect(f.sent).toEqual([]);
});
