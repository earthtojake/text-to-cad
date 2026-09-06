import type { SessionUpdate } from '@agentclientprotocol/sdk';
import type { NormalizedEvent } from '@emdash/core/runtimes/acp/api';
import { describe, expect, it } from 'vitest';
import { enrichCodexUpdate } from './acp-transform';

function makeToolCall(
  overrides: Partial<NormalizedEvent & { kind: 'tool_call' }> = {}
): NormalizedEvent {
  return {
    kind: 'tool_call',
    toolCallId: 'tc-1',
    title: 'Run tool',
    toolKind: 'other',
    status: 'in_progress',
    parentToolCallId: null,
    diffs: [],
    ...overrides,
  };
}

function makeToolUpdate(
  overrides: Partial<NormalizedEvent & { kind: 'tool_update' }> = {}
): NormalizedEvent {
  return {
    kind: 'tool_update',
    toolCallId: 'tc-1',
    title: null,
    toolKind: null,
    status: 'completed',
    parentToolCallId: null,
    diffs: [],
    ...overrides,
  };
}

function makeRaw(input?: unknown, meta?: Record<string, unknown>): SessionUpdate {
  return {
    sessionUpdate: 'tool_call',
    toolCallId: 'tc-1',
    title: 'Run tool',
    ...(input !== undefined ? { rawInput: input } : {}),
    ...(meta !== undefined ? { _meta: meta } : {}),
  } as unknown as SessionUpdate;
}

describe('enrichCodexUpdate', () => {
  it('is identity for non-tool events', () => {
    const update: NormalizedEvent = {
      kind: 'message',
      role: 'assistant',
      messageId: 'a-1',
      text: 'done',
    };
    expect(enrichCodexUpdate(update, makeRaw())).toBe(update);
  });

  it('promotes Codex MCP metadata and raw input to an MCP tool event', () => {
    const update = makeToolCall({ parentToolCallId: 'parent-1' });
    const raw = makeRaw(
      { server: 'browser', tool: 'open', arguments: { url: 'https://example.test' } },
      { is_mcp_tool_call: true }
    );

    expect(enrichCodexUpdate(update, raw)).toEqual({
      kind: 'mcp_tool',
      toolCallId: 'tc-1',
      server: 'browser',
      tool: 'open',
      status: 'in_progress',
      parentToolCallId: 'parent-1',
      inputSummary: 'https://example.test',
    });
  });

  it('recognizes completion updates from their repeated structured MCP input', () => {
    const update = makeToolUpdate({ status: 'completed' });
    const raw = makeRaw({ server: 'notion', tool: 'search', arguments: { query: 'CAD' } });

    expect(enrichCodexUpdate(update, raw)).toMatchObject({
      kind: 'mcp_tool',
      server: 'notion',
      tool: 'search',
      status: 'completed',
      inputSummary: 'CAD',
    });
  });

  it('summarizes only safe high-signal MCP fields and recursively skips secrets', () => {
    const update = makeToolCall();
    const raw = makeRaw(
      {
        server: 'notion',
        tool: 'search',
        arguments: {
          request: { query: 'CAD standards' },
          auth: { token: 'secret-token', nested: { name: 'must-not-leak' } },
          payload: { body: 'arbitrary raw body' },
        },
      },
      { is_mcp_tool_call: true }
    );

    const result = enrichCodexUpdate(update, raw);
    expect(result).toMatchObject({ kind: 'mcp_tool', inputSummary: 'CAD standards' });
    expect(JSON.stringify(result)).not.toContain('secret-token');
    expect(JSON.stringify(result)).not.toContain('must-not-leak');
    expect(JSON.stringify(result)).not.toContain('arbitrary raw body');
  });

  it('redacts secrets embedded in MCP URL summaries', () => {
    const update = makeToolCall();
    const raw = makeRaw(
      {
        server: 'browser',
        tool: 'open',
        arguments: {
          url: 'https://amy:password@example.test/spec?view=full&access_token=secret-token',
        },
      },
      { is_mcp_tool_call: true }
    );

    expect(enrichCodexUpdate(update, raw)).toMatchObject({
      kind: 'mcp_tool',
      inputSummary: 'https://example.test/spec?view=full&access_token=redacted',
    });
  });

  it('does not surface arbitrary MCP argument payloads', () => {
    const update = makeToolCall();
    const raw = makeRaw(
      {
        server: 'vendor',
        tool: 'mutate',
        arguments: { payload: { body: 'private arbitrary payload' }, password: 'secret' },
      },
      { is_mcp_tool_call: true }
    );

    expect(enrichCodexUpdate(update, raw)).toEqual({
      kind: 'mcp_tool',
      toolCallId: 'tc-1',
      server: 'vendor',
      tool: 'mutate',
      status: 'in_progress',
      parentToolCallId: null,
    });
  });

  it('keeps status-less MCP updates generic even when safe arguments repeat', () => {
    const update = makeToolUpdate({ title: null, status: null });
    const raw = makeRaw({
      server: 'browser',
      tool: 'open',
      arguments: { url: 'https://example.test' },
    });

    expect(enrichCodexUpdate(update, raw)).toBe(update);
  });

  it('does not promote malformed MCP metadata without server and tool names', () => {
    const update = makeToolCall();
    expect(
      enrichCodexUpdate(update, makeRaw({ server: 'browser' }, { is_mcp_tool_call: true }))
    ).toBe(update);
  });

  it('stamps image-generation starts with a semantic tool kind', () => {
    const update = makeToolCall({ title: 'Image generation', toolKind: 'other' });
    expect(enrichCodexUpdate(update, makeRaw())).toEqual({
      ...update,
      toolKind: 'image-generation',
    });
  });

  it('leaves ordinary tool calls unchanged', () => {
    const update = makeToolCall({ title: 'Guardian Review', toolKind: 'think' });
    expect(enrichCodexUpdate(update, makeRaw())).toBe(update);
  });
});

describe('enrichCodexUpdate command output', () => {
  it('promotes formatted_output so the transcript keeps command results', () => {
    const raw = {
      sessionUpdate: 'tool_call_update',
      toolCallId: 'tc-1',
      status: 'completed',
      rawOutput: { formatted_output: 'HEAD\n', exit_code: 0 },
    } as unknown as SessionUpdate;
    expect(enrichCodexUpdate(makeToolUpdate(), raw)).toMatchObject({
      kind: 'tool_update',
      outputText: 'HEAD\n',
    });
  });

  it('keeps ACP text output when both are present', () => {
    const raw = {
      sessionUpdate: 'tool_call_update',
      toolCallId: 'tc-1',
      status: 'completed',
      rawOutput: { formatted_output: 'ignored', exit_code: 0 },
    } as unknown as SessionUpdate;
    expect(enrichCodexUpdate(makeToolUpdate({ outputText: 'from acp' }), raw)).toMatchObject({
      outputText: 'from acp',
    });
  });
});

describe('enrichCodexUpdate child activity', () => {
  const child = '01a0758a-19c1-7af2-b22d-cd3e7e20f7f7';
  const activity = (kind: string, overrides: Record<string, unknown> = {}) =>
    makeRaw({
      type: 'subAgentActivity',
      kind,
      agentThreadId: child,
      agentPath: '/root/card_dimensions',
      ...overrides,
    });

  it('shows the named child as running even though the spawn activity is complete', () => {
    expect(enrichCodexUpdate(makeToolCall({ status: 'completed' }), activity('started'))).toEqual({
      kind: 'subagent',
      toolCallId: 'tc-1',
      title: 'card_dimensions',
      status: 'in_progress',
      parentToolCallId: null,
      background: true,
      agentId: child,
    });
  });

  it.each(['completed', 'interrupted'])(
    'settles %s activity by child id, not activity id',
    (kind) => {
      expect(
        enrichCodexUpdate(makeToolCall({ toolCallId: 'different-call' }), activity(kind))
      ).toEqual({ kind: 'subagent_update', agentId: child, status: 'completed' });
    }
  );

  it('keeps interactions separate from spawn rows', () => {
    expect(enrichCodexUpdate(makeToolCall(), activity('interacted'))).toMatchObject({
      kind: 'tool_call',
      title: 'Message to agent',
      inputSummary: '/root/card_dimensions',
    });
  });

  it.each([
    { type: 'another-tool' },
    { agentThreadId: null },
    { agentThreadId: '' },
    { agentPath: null },
    { kind: 'unknown' },
  ])('leaves unsupported activity intact: %j', (overrides) => {
    const update = makeToolCall();
    expect(enrichCodexUpdate(update, activity('started', overrides))).toBe(update);
  });
});

describe('enrichCodexUpdate multi-agent tools', () => {
  const child = '019f259c-8089-7470-a1ac-f0481c9eb13a';

  function collabRaw(
    title: string,
    sessionUpdate: 'tool_call' | 'tool_call_update',
    input: Record<string, unknown>
  ): SessionUpdate {
    return {
      sessionUpdate,
      toolCallId: 'tc-1',
      title,
      kind: 'other',
      status: sessionUpdate === 'tool_call' ? 'in_progress' : 'completed',
      rawInput: { senderThreadId: 'parent', receiverThreadIds: [], agentsStates: {}, ...input },
    } as unknown as SessionUpdate;
  }

  it('surfaces spawnAgent as a background subagent with its brief', () => {
    const raw = collabRaw('spawnAgent', 'tool_call', {
      prompt: 'Find files under packages/core that mention stopReason.',
      status: 'inProgress',
    });
    expect(enrichCodexUpdate(makeToolCall({ title: 'spawnAgent' }), raw)).toEqual({
      kind: 'subagent',
      toolCallId: 'tc-1',
      title: 'Codex agent',
      status: 'in_progress',
      parentToolCallId: null,
      inputSummary: 'Find files under packages/core that mention stopReason.',
      background: true,
    });
  });

  it('attaches the agent id and keeps the row running once the spawn completes', () => {
    const raw = collabRaw('spawnAgent', 'tool_call_update', {
      prompt: 'Find files',
      receiverThreadIds: [child],
      agentsStates: { [child]: { status: 'pendingInit', message: null } },
    });
    expect(enrichCodexUpdate(makeToolUpdate(), raw)).toMatchObject({
      kind: 'subagent',
      status: 'in_progress',
      agentId: child,
      background: true,
    });
  });

  it('closes the subagent row when closeAgent completes', () => {
    const raw = collabRaw('closeAgent', 'tool_call_update', {
      receiverThreadIds: [child],
      agentsStates: { [child]: { status: 'running', message: null } },
    });
    expect(enrichCodexUpdate(makeToolUpdate(), raw)).toEqual({
      kind: 'subagent_update',
      agentId: child,
      status: 'completed',
    });
  });

  it('describes waits and messages instead of leaving raw tool names', () => {
    const wait = collabRaw('wait', 'tool_call', { prompt: null, receiverThreadIds: [child] });
    expect(enrichCodexUpdate(makeToolCall({ title: 'wait' }), wait)).toMatchObject({
      kind: 'tool_call',
      title: 'Wait for agent',
      inputSummary: 'agent 019f259c',
    });
    const message = collabRaw('sendInput', 'tool_call', {
      prompt: 'Return only confirmed matches.',
      receiverThreadIds: [child],
    });
    expect(enrichCodexUpdate(makeToolCall({ title: 'sendInput' }), message)).toMatchObject({
      kind: 'tool_call',
      title: 'Message to agent',
      inputSummary: 'Return only confirmed matches.',
    });
  });

  it('leaves unrelated tools named like the collab tools alone', () => {
    const raw = {
      sessionUpdate: 'tool_call',
      toolCallId: 'tc-1',
      title: 'wait',
      kind: 'other',
      status: 'in_progress',
      rawInput: { seconds: 5 },
    } as unknown as SessionUpdate;
    const update = makeToolCall({ title: 'wait' });
    expect(enrichCodexUpdate(update, raw)).toBe(update);
  });
});

describe('enrichCodexUpdate MCP progress', () => {
  it('keeps the latest progress line while an integration call runs', () => {
    const raw = {
      sessionUpdate: 'tool_call_update',
      toolCallId: 'tc-1',
      _meta: { mcp_output_delta: { data: 'connecting\nfetching issues (page 2)\n' } },
    } as unknown as SessionUpdate;
    expect(enrichCodexUpdate(makeToolUpdate({ status: null }), raw)).toMatchObject({
      kind: 'tool_update',
      progress: 'fetching issues (page 2)',
    });
  });
});
