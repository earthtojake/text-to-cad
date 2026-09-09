import { isOk } from '@emdash/shared';
import { peek, remote, snapshot } from '@emdash/wire/state';
import { createTestWire } from '@emdash/wire/testing';
import { describe, expect, it, vi } from 'vitest';
import {
  acpApiContract,
  acpRuntimeErrorSchema,
  promptDraftSchema,
  sessionConfigStateSchema,
  sessionStateSchema,
  sessionUsageSchema,
  transcriptTurnSchema,
  uploadAttachmentCommandSchema,
} from '#runtimes/acp/api';
import { makeAcpHarness, makeStartInput } from '#runtimes/acp/node/acp-test-support';
import { AcpRuntime } from '#runtimes/acp/node/runtime/runtime';
import { createAcpController } from './controller';

describe('ACP API contract schemas', () => {
  it('parses runtime live model snapshots with the public schemas', async () => {
    const h = makeAcpHarness();
    const rt = new AcpRuntime(h.deps);
    const started = await rt.startSession(makeStartInput({ conversationId: 'conv-contract' }));
    expect(isOk(started)).toBe(true);

    const live = rt.sessionLiveModels('conv-contract');
    if (!live) throw new Error('expected live models');

    expect(acpApiContract.session.id).toBe('session');
    expect(() => sessionStateSchema.parse(peek(live.states.state))).not.toThrow();
    expect(() => sessionConfigStateSchema.parse(peek(live.states.config))).not.toThrow();
    expect(() => sessionUsageSchema.nullable().parse(peek(live.states.usage))).not.toThrow();
    expect(() => transcriptTurnSchema.nullable().parse(peek(live.states.activeTurn))).not.toThrow();
    expect(() => promptDraftSchema.nullable().parse(peek(live.states.draft))).not.toThrow();
  });

  it('round-trips procedures and live state over a wire transport', async () => {
    const h = makeAcpHarness();
    const rt = new AcpRuntime(h.deps);
    const wire = createTestWire(acpApiContract, createAcpController(rt));
    const contractClient = wire.client;
    const sessions = remote(acpApiContract.sessions, contractClient.sessions);
    const sessionRemote = remote(acpApiContract.session, contractClient.session);
    const summaries = sessions(undefined);

    try {
      await summaries.states.list.refresh();
      const input = makeStartInput({ conversationId: 'conv-wire' });
      const started = await contractClient.start(input);
      expect(started).toEqual({ success: true, data: { sessionId: 'session-1' } });

      await vi.waitFor(() => {
        expect(snapshot(summaries.states.list).value?.['conv-wire']).toMatchObject({
          conversationId: 'conv-wire',
          lifecycle: 'ready',
        });
      });

      const session = sessionRemote({ conversationId: 'conv-wire' });
      await session.states.state.refresh();
      expect(snapshot(session.states.state).value).toMatchObject({ lifecycle: 'ready' });
    } finally {
      await sessions.dispose();
      await sessionRemote.dispose();
      wire.dispose();
    }
  });

  it('accepts attachment upload sidecar input with or without original path', () => {
    expect(() => uploadAttachmentCommandSchema.parse({ conversationId: 'conv-1' })).not.toThrow();
    expect(() =>
      uploadAttachmentCommandSchema.parse({
        conversationId: 'conv-1',
        originalPath: '/tmp/image.png',
      })
    ).not.toThrow();
    // Attachments are conversation-scoped (spec §3.6): the owning conversation is required.
    expect(() => uploadAttachmentCommandSchema.parse({})).toThrow();
  });

  it('accepts auth_required runtime errors', () => {
    expect(() =>
      acpRuntimeErrorSchema.parse({
        type: 'auth_required',
        cause: { name: 'RequestError', message: 'Authentication required' },
      })
    ).not.toThrow();
  });
});
