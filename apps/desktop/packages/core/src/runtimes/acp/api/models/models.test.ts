import type { SessionUpdate } from '@agentclientprotocol/sdk';
import { describe, expect, it } from 'vitest';
import { transcriptTurnSchema } from '#runtimes/acp/api/models/turns';
import { AcpTranscriptParser } from '../reducer/parser';
import { agentStateSchema } from './agents';
import { sessionConfigStateSchema, sessionUsageSchema } from './config';
import { planStateSchema } from './plan';

function buildParserOutput(): AcpTranscriptParser {
  const parser = new AcpTranscriptParser({ conversationId: 'models-test' });
  parser.push({
    sessionUpdate: 'user_message_chunk',
    sessionId: 'session-1',
    messageId: 'user-1',
    content: { type: 'text', text: 'Audit the reducer.' },
  } as unknown as SessionUpdate);
  parser.push({
    sessionUpdate: 'config_option_update',
    sessionId: 'session-1',
    configOptions: [
      {
        id: 'model',
        category: 'model',
        type: 'select',
        currentValue: 'sonnet',
        options: [{ value: 'sonnet', name: 'Sonnet' }],
      },
    ],
  } as unknown as SessionUpdate);
  parser.push({
    sessionUpdate: 'usage_update',
    sessionId: 'session-1',
    used: 100,
    size: 200000,
    cost: { amount: 0.01, currency: 'USD' },
  } as unknown as SessionUpdate);
  parser.push({
    sessionUpdate: 'tool_call',
    sessionId: 'session-1',
    toolCallId: 'execute-1',
    title: 'echo ok',
    kind: 'execute',
    status: 'in_progress',
    terminalId: 'term-1',
    content: [],
  } as unknown as SessionUpdate);
  parser.push({
    sessionUpdate: 'tool_call_update',
    sessionId: 'session-1',
    toolCallId: 'execute-1',
    title: null,
    kind: 'execute',
    status: 'completed',
    content: [{ type: 'content', content: { type: 'text', text: 'ok' } }],
  } as unknown as SessionUpdate);
  parser.pushEvent({
    kind: 'tool_update',
    toolCallId: 'execute-1',
    title: null,
    toolKind: 'execute',
    status: 'completed',
    parentToolCallId: null,
    diffs: [],
    attachments: [{ id: 'sha256-image', name: 'output.png', mimeType: 'image/png' }],
  });
  parser.push({
    sessionUpdate: 'plan',
    sessionId: 'session-1',
    entries: [{ content: 'Read reducer.ts', status: 'pending', priority: 'medium' }],
  } as unknown as SessionUpdate);
  parser.pushEvent(
    {
      kind: 'subagent',
      toolCallId: 'tool-1',
      title: 'Inspect reducer',
      status: 'in_progress',
      parentToolCallId: null,
      background: true,
      agentId: 'agent-1',
      outputFile: '/tmp/agent-1.output',
    },
    100
  );
  parser.endTurn(200);
  return parser;
}

describe('ACP zod models', () => {
  it('validates representative parser output', () => {
    const parser = buildParserOutput();

    expect(() => transcriptTurnSchema.array().parse(parser.history)).not.toThrow();
    expect(() =>
      parser.activeTurn === null ? null : transcriptTurnSchema.parse(parser.activeTurn)
    ).not.toThrow();
    expect(() => sessionConfigStateSchema.parse(parser.config)).not.toThrow();
    expect(() =>
      parser.usage === null ? null : sessionUsageSchema.parse(parser.usage)
    ).not.toThrow();
    expect(() => agentStateSchema.array().parse(parser.agents)).not.toThrow();
    expect(() => (parser.plan === null ? null : planStateSchema.parse(parser.plan))).not.toThrow();
  });
});
