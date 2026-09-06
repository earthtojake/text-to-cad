import type { SessionUpdate } from '@agentclientprotocol/sdk';
import { describe, expect, it } from 'vitest';
import { decodeSessionUpdate } from './decode';

function executeCall(extra: Record<string, unknown>): SessionUpdate {
  return {
    sessionUpdate: 'tool_call',
    toolCallId: 'call-1',
    title: 'ls -la',
    kind: 'execute',
    status: 'in_progress',
    ...extra,
  } as unknown as SessionUpdate;
}

describe('decodeSessionUpdate terminal attachment', () => {
  it('reads the terminal id from a terminal content block', () => {
    const event = decodeSessionUpdate(
      executeCall({ content: [{ type: 'terminal', terminalId: 'call-1' }] })
    );
    expect(event).toMatchObject({ kind: 'tool_call', terminalId: 'call-1' });
  });

  it('prefers an explicit terminalId over content blocks', () => {
    const event = decodeSessionUpdate(
      executeCall({
        terminalId: 'explicit',
        content: [{ type: 'terminal', terminalId: 'from-content' }],
      })
    );
    expect(event).toMatchObject({ kind: 'tool_call', terminalId: 'explicit' });
  });

  it('leaves the terminal id unset without a terminal block', () => {
    const event = decodeSessionUpdate(
      executeCall({ content: [{ type: 'content', content: { type: 'text', text: 'ok' } }] })
    );
    expect(event).toMatchObject({ kind: 'tool_call' });
    expect('terminalId' in event).toBe(false);
  });
});

describe('decodeSessionUpdate message content blocks', () => {
  function chunk(content: Record<string, unknown>): SessionUpdate {
    return {
      sessionUpdate: 'agent_message_chunk',
      messageId: 'm1',
      content,
    } as unknown as SessionUpdate;
  }

  it('turns a resource link into a message link', () => {
    expect(
      decodeSessionUpdate(
        chunk({
          type: 'resource_link',
          uri: 'file:///repo/models/plate.step',
          name: 'plate.step',
          title: 'Plate',
          mimeType: 'model/step',
          size: 1234,
        })
      )
    ).toEqual({
      kind: 'message',
      role: 'assistant',
      messageId: 'm1',
      text: '',
      links: [
        {
          uri: 'file:///repo/models/plate.step',
          name: 'plate.step',
          title: 'Plate',
          mimeType: 'model/step',
          size: 1234,
        },
      ],
    });
  });

  it('inlines embedded text resources under their uri', () => {
    expect(
      decodeSessionUpdate(
        chunk({
          type: 'resource',
          resource: { uri: 'file:///repo/notes.md', mimeType: 'text/markdown', text: '# Notes' },
        })
      )
    ).toMatchObject({ kind: 'message', text: '\nfile:///repo/notes.md\n# Notes\n' });
  });

  it('keeps an image chunk as an empty message for the attachment ingress', () => {
    expect(
      decodeSessionUpdate(chunk({ type: 'image', data: 'AAAA', mimeType: 'image/png' }))
    ).toEqual({ kind: 'message', role: 'assistant', messageId: 'm1', text: '' });
  });

  it('ignores audio', () => {
    expect(
      decodeSessionUpdate(chunk({ type: 'audio', data: 'AAAA', mimeType: 'audio/wav' }))
    ).toEqual({ kind: 'ignored' });
  });
});

describe('decodeSessionUpdate tool locations and plans', () => {
  it('carries reported file locations', () => {
    const event = decodeSessionUpdate({
      sessionUpdate: 'tool_call',
      toolCallId: 'call-2',
      title: 'Edit',
      kind: 'edit',
      status: 'in_progress',
      locations: [{ path: '/repo/src/a.ts', line: 12 }, { path: 42 }],
    } as unknown as SessionUpdate);
    expect(event).toMatchObject({
      kind: 'tool_call',
      locations: [{ path: '/repo/src/a.ts', line: 12 }],
    });
  });

  it('maps item, markdown, and removed plan updates onto the plan event', () => {
    expect(
      decodeSessionUpdate({
        sessionUpdate: 'plan_update',
        plan: {
          type: 'items',
          id: 'p1',
          entries: [{ content: 'Write tests', status: 'in_progress', priority: 'high' }],
        },
      } as unknown as SessionUpdate)
    ).toEqual({
      kind: 'plan',
      entries: [{ content: 'Write tests', status: 'in_progress', priority: 'high' }],
    });
    expect(
      decodeSessionUpdate({
        sessionUpdate: 'plan_update',
        plan: { type: 'markdown', id: 'p1', content: '1. Do the thing' },
      } as unknown as SessionUpdate)
    ).toEqual({
      kind: 'plan',
      entries: [{ content: '1. Do the thing', status: 'in_progress', priority: 'medium' }],
    });
    expect(
      decodeSessionUpdate({ sessionUpdate: 'plan_removed', id: 'p1' } as unknown as SessionUpdate)
    ).toEqual({ kind: 'plan', entries: [] });
  });
});

describe('decodeSessionUpdate initial tool text and rate limits', () => {
  it('keeps text a tool call carries from the start', () => {
    const event = decodeSessionUpdate({
      sessionUpdate: 'tool_call',
      toolCallId: 'plan-1',
      title: 'ExitPlanMode',
      kind: 'switch_mode',
      status: 'pending',
      content: [{ type: 'content', content: { type: 'text', text: '1. Add tests\n2. Ship' } }],
    } as unknown as SessionUpdate);
    expect(event).toMatchObject({ kind: 'tool_call', outputText: '1. Add tests\n2. Ship' });
  });

  it('reads linked resources inside tool results as lines', () => {
    const event = decodeSessionUpdate({
      sessionUpdate: 'tool_call_update',
      toolCallId: 'view-1',
      status: 'completed',
      content: [
        {
          type: 'content',
          content: { type: 'resource_link', name: 'render.png', uri: 'file:///repo/render.png' },
        },
      ],
    } as unknown as SessionUpdate);
    expect(event).toMatchObject({
      kind: 'tool_update',
      outputText: 'render.png: file:///repo/render.png',
    });
  });

  it('carries provider rate limits beside usage', () => {
    const event = decodeSessionUpdate({
      sessionUpdate: 'usage_update',
      used: 10,
      size: 100,
      _meta: {
        '_claude/rateLimit': {
          status: 'allowed_warning',
          resetsAt: 1_700_000_000,
          utilization: 0.9,
        },
      },
    } as unknown as SessionUpdate);
    expect(event).toEqual({
      kind: 'usage',
      usage: {
        contextUsed: 10,
        contextSize: 100,
        cost: null,
        rateLimit: { status: 'allowed_warning', resetsAt: 1_700_000_000, utilization: 0.9 },
      },
    });
  });
});
