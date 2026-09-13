import type { SessionUpdate } from '@agentclientprotocol/sdk';
import type { NormalizedEvent } from '@emdash/core/runtimes/acp/api';
import { describe, expect, it } from 'vitest';
import { enrichClaudeUpdate, parseTaskNotification } from './acp-transform';

// ── fixtures ──────────────────────────────────────────────────────────────────

function makeToolCall(
  overrides: Partial<NormalizedEvent & { kind: 'tool_call' }> = {}
): NormalizedEvent {
  return {
    kind: 'tool_call',
    toolCallId: 'tc-1',
    title: 'Run bash',
    toolKind: 'execute',
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

function makeRaw(meta?: Record<string, unknown>): SessionUpdate {
  return {
    sessionUpdate: 'tool_call',
    toolCallId: 'tc-1',
    title: 'Run bash',
    ...(meta !== undefined ? { _meta: meta } : {}),
  };
}

// ── enrichClaudeUpdate ────────────────────────────────────────────────────────

describe('enrichClaudeUpdate', () => {
  it('is identity for message kind', () => {
    const update: NormalizedEvent = {
      kind: 'message',
      role: 'assistant',
      messageId: 'assistant',
      text: 'hello',
    };
    const raw = makeRaw({ claudeCode: { parentToolUseId: 'parent-1' } });
    expect(enrichClaudeUpdate(update, raw)).toBe(update);
  });

  it('is identity for thinking kind', () => {
    const update: NormalizedEvent = { kind: 'thinking', messageId: 'main', text: 'thinking...' };
    const raw = makeRaw({ claudeCode: { parentToolUseId: 'parent-1' } });
    expect(enrichClaudeUpdate(update, raw)).toBe(update);
  });

  it('is identity for ignored kind', () => {
    const update: NormalizedEvent = { kind: 'ignored' };
    const raw = makeRaw({ claudeCode: { parentToolUseId: 'parent-1' } });
    expect(enrichClaudeUpdate(update, raw)).toBe(update);
  });

  it('is identity for tool_call when _meta is absent', () => {
    const update = makeToolCall();
    const raw = makeRaw();
    expect(enrichClaudeUpdate(update, raw)).toBe(update);
  });

  it('is identity for tool_call when claudeCode is absent', () => {
    const update = makeToolCall();
    const raw = makeRaw({ other: 'value' });
    expect(enrichClaudeUpdate(update, raw)).toBe(update);
  });

  it('is identity for tool_call when parentToolUseId is absent', () => {
    const update = makeToolCall();
    const raw = makeRaw({ claudeCode: { toolName: 'Bash' } });
    expect(enrichClaudeUpdate(update, raw)).toBe(update);
  });

  it('is identity for tool_call when parentToolUseId is not a string', () => {
    const update = makeToolCall();
    const raw = makeRaw({ claudeCode: { parentToolUseId: 42 } });
    expect(enrichClaudeUpdate(update, raw)).toBe(update);
  });

  it('promotes parentToolUseId to parentToolCallId on tool_call', () => {
    const update = makeToolCall();
    const raw = makeRaw({ claudeCode: { parentToolUseId: 'parent-abc' } });
    const result = enrichClaudeUpdate(update, raw);
    expect(result).not.toBe(update);
    expect(result).toMatchObject({ kind: 'tool_call', parentToolCallId: 'parent-abc' });
  });

  it('promotes parentToolUseId to parentToolCallId on tool_update', () => {
    const update = makeToolUpdate();
    const raw = makeRaw({ claudeCode: { parentToolUseId: 'parent-xyz' } });
    const result = enrichClaudeUpdate(update, raw);
    expect(result).not.toBe(update);
    expect(result).toMatchObject({ kind: 'tool_update', parentToolCallId: 'parent-xyz' });
  });

  it('uses rawOutput as Claude execute output fallback when standard content is absent', () => {
    const update = makeToolUpdate();
    const raw = {
      ...makeRaw({ claudeCode: { toolName: 'Bash' } }),
      rawOutput: 'hello from raw output',
    } as unknown as SessionUpdate;

    expect(enrichClaudeUpdate(update, raw)).toMatchObject({
      kind: 'tool_update',
      outputText: 'hello from raw output',
    });
  });

  it('does not overwrite standard outputText with Claude rawOutput', () => {
    const update = makeToolUpdate({ outputText: 'standard output' });
    const raw = {
      ...makeRaw({ claudeCode: { toolName: 'Bash' } }),
      rawOutput: 'raw output',
    } as unknown as SessionUpdate;

    expect(enrichClaudeUpdate(update, raw)).toBe(update);
  });

  it('preserves all other fields on tool_call when enriching', () => {
    const update = makeToolCall({ toolCallId: 'tc-99', title: 'Read file', toolKind: 'read' });
    const raw = makeRaw({ claudeCode: { parentToolUseId: 'parent-1' } });
    const result = enrichClaudeUpdate(update, raw);
    expect(result).toMatchObject({
      kind: 'tool_call',
      toolCallId: 'tc-99',
      title: 'Read file',
      toolKind: 'read',
    });
  });

  it('does not mutate the original update', () => {
    const update = makeToolCall();
    const raw = makeRaw({ claudeCode: { parentToolUseId: 'parent-42' } });
    enrichClaudeUpdate(update, raw);
    expect(update).toMatchObject({ kind: 'tool_call', parentToolCallId: null });
  });

  it('reclassifies Claude Agent tool calls as subagent events', () => {
    const update = makeToolCall({ title: 'Task', toolKind: 'think' });
    const raw = makeRaw({ claudeCode: { toolName: 'Agent' } });

    expect(enrichClaudeUpdate(update, raw)).toMatchObject({
      kind: 'subagent',
      toolCallId: 'tc-1',
      title: 'Task',
      status: 'in_progress',
      parentToolCallId: null,
    });
  });

  it('reclassifies Claude WebSearch with its query and parent', () => {
    const update = makeToolCall({ title: '"CAD tolerancing standards"', toolKind: 'fetch' });
    const raw = {
      ...makeRaw({ claudeCode: { toolName: 'WebSearch', parentToolUseId: 'parent-1' } }),
      rawInput: { query: 'CAD tolerancing standards' },
    } as unknown as SessionUpdate;

    expect(enrichClaudeUpdate(update, raw)).toEqual({
      kind: 'search',
      toolCallId: 'tc-1',
      query: 'CAD tolerancing standards',
      scope: 'web',
      status: 'in_progress',
      parentToolCallId: 'parent-1',
    });
  });

  it('reclassifies Claude WebFetch with its URL', () => {
    const update = makeToolCall({
      title: 'Fetch https://example.test/spec',
      toolKind: 'fetch',
    });
    const raw = {
      ...makeRaw({ claudeCode: { toolName: 'WebFetch' } }),
      rawInput: { url: 'https://example.test/spec', prompt: 'Summarize this specification' },
    } as unknown as SessionUpdate;

    expect(enrichClaudeUpdate(update, raw)).toEqual({
      kind: 'web_fetch',
      toolCallId: 'tc-1',
      url: 'https://example.test/spec',
      status: 'in_progress',
      parentToolCallId: null,
    });
  });

  it('removes credentials and secret-like query parameters from WebFetch URLs', () => {
    const update = makeToolCall({ title: 'Fetch secret URL', toolKind: 'fetch' });
    const raw = {
      ...makeRaw({ claudeCode: { toolName: 'WebFetch' } }),
      rawInput: {
        url: 'https://amy:password@example.test/spec?view=summary&api_key=top-secret#token=abc',
      },
    } as unknown as SessionUpdate;

    const result = enrichClaudeUpdate(update, raw);
    expect(result).toMatchObject({
      kind: 'web_fetch',
      url: 'https://example.test/spec?view=summary&api_key=redacted#redacted',
    });
    expect(JSON.stringify(result)).not.toContain('password');
    expect(JSON.stringify(result)).not.toContain('top-secret');
    expect(JSON.stringify(result)).not.toContain('token=abc');
  });

  it('reclassifies Claude MCP tools and summarizes their input', () => {
    const update = makeToolCall({ title: 'mcp__browser__open', toolKind: 'other' });
    const raw = {
      ...makeRaw({
        claudeCode: { toolName: 'mcp__browser__open', parentToolUseId: 'parent-2' },
      }),
      rawInput: { url: 'https://example.test' },
    } as unknown as SessionUpdate;

    expect(enrichClaudeUpdate(update, raw)).toEqual({
      kind: 'mcp_tool',
      toolCallId: 'tc-1',
      server: 'browser',
      tool: 'open',
      status: 'in_progress',
      parentToolCallId: 'parent-2',
      inputSummary: 'https://example.test',
    });
  });

  it('summarizes only safe high-signal MCP fields and recursively skips secrets', () => {
    const update = makeToolCall({ title: 'mcp__notion__search', toolKind: 'other' });
    const raw = {
      ...makeRaw({ claudeCode: { toolName: 'mcp__notion__search' } }),
      rawInput: {
        request: { query: 'bearing options' },
        credentials: {
          apiKey: 'secret-api-key',
          nested: { title: 'must-not-leak-from-secret-subtree' },
        },
        payload: { body: 'arbitrary raw body' },
      },
    } as unknown as SessionUpdate;

    const result = enrichClaudeUpdate(update, raw);
    expect(result).toMatchObject({
      kind: 'mcp_tool',
      inputSummary: 'bearing options',
    });
    expect(JSON.stringify(result)).not.toContain('secret-api-key');
    expect(JSON.stringify(result)).not.toContain('must-not-leak');
    expect(JSON.stringify(result)).not.toContain('arbitrary raw body');
  });

  it('does not surface arbitrary MCP payloads when no safe summary field exists', () => {
    const update = makeToolCall({ title: 'mcp__vendor__mutate', toolKind: 'other' });
    const raw = {
      ...makeRaw({ claudeCode: { toolName: 'mcp__vendor__mutate' } }),
      rawInput: { payload: { body: 'private arbitrary payload' }, apiKey: 'secret' },
    } as unknown as SessionUpdate;

    expect(enrichClaudeUpdate(update, raw)).toEqual({
      kind: 'mcp_tool',
      toolCallId: 'tc-1',
      server: 'vendor',
      tool: 'mutate',
      status: 'in_progress',
      parentToolCallId: null,
    });
  });

  it('keeps status-less MCP refinements generic even when input repeats', () => {
    const update = makeToolUpdate({ title: null, status: null });
    const raw = {
      ...makeRaw({ claudeCode: { toolName: 'mcp__browser__open' } }),
      rawInput: { url: 'https://example.test' },
    } as unknown as SessionUpdate;

    expect(enrichClaudeUpdate(update, raw)).toEqual(update);
  });

  it('keeps MCP updates without raw input generic so the start summary survives', () => {
    const update = makeToolUpdate({ title: null, status: 'completed' });
    const raw = makeRaw({ claudeCode: { toolName: 'mcp__browser__open' } });

    expect(enrichClaudeUpdate(update, raw)).toEqual(update);
  });

  it('marks async-launched agents as running background subagents', () => {
    const update = makeToolUpdate({ title: null, status: 'completed' });
    const raw = makeRaw({
      claudeCode: {
        toolName: 'Agent',
        toolResponse: {
          isAsync: true,
          status: 'async_launched',
          agentId: 'agent-1',
          description: 'Find event parsing',
          outputFile: '/tmp/agent-1.output',
        },
      },
    });

    expect(enrichClaudeUpdate(update, raw)).toMatchObject({
      kind: 'subagent',
      agentId: 'agent-1',
      background: true,
      outputFile: '/tmp/agent-1.output',
      title: 'Find event parsing',
      status: 'in_progress',
    });
  });

  it('reclassifies task-notification user chunks as subagent updates', () => {
    const update: NormalizedEvent = {
      kind: 'message',
      role: 'user',
      messageId: 'u1',
      text: [
        '<task-notification>',
        '<task-id>agent-1</task-id>',
        '<tool-use-id>toolu_123</tool-use-id>',
        '<output-file>/tmp/agent-1.output</output-file>',
        '<status>completed</status>',
        '<summary>Agent "Find event parsing" finished</summary>',
        '</task-notification>',
      ].join('\n'),
    };

    expect(enrichClaudeUpdate(update, makeRaw())).toEqual({
      kind: 'subagent_update',
      agentId: 'agent-1',
      toolCallId: 'toolu_123',
      status: 'completed',
      summary: 'Agent "Find event parsing" finished',
      outputFile: '/tmp/agent-1.output',
    });
  });

  it('ignores local command pseudo-user chunks', () => {
    const update: NormalizedEvent = {
      kind: 'message',
      role: 'user',
      messageId: 'u1',
      text: '<command-name>/model</command-name>',
    };

    expect(enrichClaudeUpdate(update, makeRaw())).toEqual({ kind: 'ignored' });
  });
});

describe('parseTaskNotification', () => {
  it('extracts the stable notification fields without parsing the result body', () => {
    expect(
      parseTaskNotification(
        [
          '<task-notification>',
          '<task-id>agent-1</task-id>',
          '<tool-use-id>toolu_123</tool-use-id>',
          '<output-file>/tmp/agent-1.output</output-file>',
          '<status>completed</status>',
          '<summary>Background command "Search & report" completed</summary>',
          '<result>May contain <xml-like> text and markdown.</result>',
          '</task-notification>',
        ].join('\n')
      )
    ).toEqual({
      taskId: 'agent-1',
      toolUseId: 'toolu_123',
      outputFile: '/tmp/agent-1.output',
      status: 'completed',
      summary: 'Background command "Search & report" completed',
    });
  });
});

describe('enrichClaudeUpdate tool names', () => {
  it('treats the Task tool as a subagent like Agent', () => {
    const raw = makeRaw({ claudeCode: { toolName: 'Task' } });
    expect(enrichClaudeUpdate(makeToolCall({ title: 'Explore the repo' }), raw)).toMatchObject({
      kind: 'subagent',
      title: 'Explore the repo',
    });
  });

  it('names an ExitPlanMode call as the plan awaiting approval', () => {
    const raw = makeRaw({ claudeCode: { toolName: 'ExitPlanMode' } });
    expect(
      enrichClaudeUpdate(
        makeToolCall({ title: 'ExitPlanMode', toolKind: 'switch_mode', outputText: '1. Ship' }),
        raw
      )
    ).toMatchObject({ kind: 'tool_call', title: 'Plan for approval', outputText: '1. Ship' });
  });
});
