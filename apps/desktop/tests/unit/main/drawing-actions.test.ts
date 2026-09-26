import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { afterEach, expect, it } from 'vitest';
import { createActions, RendererCommands } from '@main/integrations/actions';
import type { BridgeSession } from '@main/integrations/mcp-bridge';
import { IntegrationCommandKindSchema, type IntegrationCommand } from '@shared/ipc/integrations';
import { dialogsContract } from '@shared/ipc/dialogs';

const relays: RendererCommands[] = [];
const directories: string[] = [];
afterEach(() => { for (const relay of relays.splice(0)) relay.dispose(); for (const directory of directories.splice(0)) fs.rmSync(directory, { recursive: true, force: true }); });
function fixture(root: string | null = null) {
  const directory = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'hardcore-drawing-actions-')));
  directories.push(directory);
  root = root === null ? null : directory;
  const session: BridgeSession = { sessionId: 'session', projectId: 'project', cwd: directory };
  const sent: IntegrationCommand[] = [];
  let reply: unknown = { tabId: 'sketch', title: 'Sketch', ephemeral: true };
  let refusal: string | null = null;
  let sequence = 0;
  const deps = { sessionRoot: () => ({ directory: session.cwd, root }), newId: () => `r${++sequence}`,
    send(command: IntegrationCommand) {
      sent.push(command);
      relay.reply(refusal ? { requestId: command.requestId, ok: false, error: refusal }
        : { requestId: command.requestId, ok: true, result: reply });
    } };
  const relay = new RendererCommands(deps);
  relays.push(relay);
  return { session, sent, actions: createActions(deps, relay), setReply: (value: unknown) => { reply = value; },
    setRefusal: (value: string) => { refusal = value; } };
}
it('opens only an empty temporary drawing in the authenticated session root', async () => {
  const f = fixture('/worktree');
  const result = await f.actions.open_drawing!(f.session, { title: 'Sketch' });
  expect(result).toMatchObject({ tabId: 'sketch', ephemeral: true });
  expect(f.sent[0]).toMatchObject({ kind: 'open-drawing', projectId: 'project', root: f.session.cwd, title: 'Sketch' });
  expect(f.sent[0]).not.toHaveProperty('path');
  expect(f.sent[0]).not.toHaveProperty('scene');
  expect(() => f.actions.open_drawing!(f.session, { path: 'plan.excalidraw' })).toThrow();
  expect(f.sent).toHaveLength(1);
});
it('reads and captures an identified sketch without exposing an editable scene or destination path', async () => {
  const f = fixture();
  const state = { tabId: 'sketch', title: 'Sketch', elementCount: 2, ephemeral: true };
  f.setReply(state);
  expect(await f.actions.drawing_state!(f.session, { tabId: 'sketch' })).toEqual(state);
  const image = { ...state, mimeType: 'image/png', base64: 'cG5n' };
  f.setReply(image);
  expect(await f.actions.capture_drawing!(f.session, { tabId: 'sketch' })).toEqual(image);
  expect(f.sent.map(command => ({ kind: command.kind, tabId: command.tabId, root: command.root }))).toEqual([
    { kind: 'drawing-state', tabId: 'sketch', root: null }, { kind: 'drawing-capture', tabId: 'sketch', root: null },
  ]);
});
it('offers no drawing persistence tool, scene relay or native save dialog', () => {
  const f = fixture();
  expect(f.actions).not.toHaveProperty('save_drawing');
  expect(IntegrationCommandKindSchema.safeParse('drawing-scene').success).toBe(false);
  expect(dialogsContract.dialogs).not.toHaveProperty('saveDrawing');
});
it('propagates workspace or closed-sketch refusals instead of claiming a capture succeeded', async () => {
  const f = fixture();
  f.setRefusal('that drawing belongs to another workspace');
  await expect(f.actions.capture_drawing!(f.session, { tabId: 'sketch' })).rejects.toThrow('another workspace');
});
