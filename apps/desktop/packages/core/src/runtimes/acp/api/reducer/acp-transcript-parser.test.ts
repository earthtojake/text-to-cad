/**
 * Unit tests for AcpTranscriptParser.
 *
 * Uses hand-authored minimal SessionUpdate objects — no captured fixtures.
 * Fixture-driven provider-specific tests are a separate follow-up.
 */

import type { SessionUpdate } from '@agentclientprotocol/sdk';
import { describe, expect, it } from 'vitest';
import { SESSION_PLAN_ID } from '../models/plan';
import {
  makeDiffId,
  makeMessageId,
  makeThinkingId,
  makeToolGroupId,
  makeToolId,
  makeTurnId,
} from './ids';
import { foldItem } from './item-fold';
import { AcpTranscriptParser } from './parser';

const CID = 'conv-1';

function deps() {
  return { conversationId: CID };
}

function userChunk(messageId: string, text: string): SessionUpdate {
  return {
    sessionUpdate: 'user_message_chunk',
    sessionId: 'sess-1',
    messageId,
    content: { type: 'text', text },
  } as unknown as SessionUpdate;
}

function assistantChunk(messageId: string, text: string): SessionUpdate {
  return {
    sessionUpdate: 'agent_message_chunk',
    sessionId: 'sess-1',
    messageId,
    content: { type: 'text', text },
  } as unknown as SessionUpdate;
}

function thoughtChunk(messageId: string, text: string): SessionUpdate {
  return {
    sessionUpdate: 'agent_thought_chunk',
    sessionId: 'sess-1',
    messageId,
    content: { type: 'text', text },
  } as unknown as SessionUpdate;
}

function toolCallUpdate(toolCallId: string, title: string, toolKind = 'other'): SessionUpdate {
  return {
    sessionUpdate: 'tool_call',
    sessionId: 'sess-1',
    toolCallId,
    title,
    kind: toolKind,
    status: 'in_progress',
    content: [],
  } as unknown as SessionUpdate;
}

function toolUpdateDone(toolCallId: string): SessionUpdate {
  return {
    sessionUpdate: 'tool_call_update',
    sessionId: 'sess-1',
    toolCallId,
    title: null,
    kind: null,
    status: 'completed',
    content: [],
  } as unknown as SessionUpdate;
}

function toolUpdateWithTextOutput(
  toolCallId: string,
  text: string,
  terminalId?: string
): SessionUpdate {
  return {
    sessionUpdate: 'tool_call_update',
    sessionId: 'sess-1',
    toolCallId,
    title: null,
    kind: 'execute',
    status: 'completed',
    content: [{ type: 'content', content: { type: 'text', text } }],
    ...(terminalId !== undefined ? { terminalId } : {}),
  } as unknown as SessionUpdate;
}

function toolUpdateWithDiff(
  toolCallId: string,
  path: string,
  oldText: string | null,
  newText: string,
  status = 'completed'
): SessionUpdate {
  return {
    sessionUpdate: 'tool_call_update',
    sessionId: 'sess-1',
    toolCallId,
    title: null,
    kind: 'edit',
    status,
    content: [{ type: 'diff', path, oldText, newText }],
  } as unknown as SessionUpdate;
}

function planUpdate(
  entries: Array<{ content: string; status: string; priority: string }>
): SessionUpdate {
  return {
    sessionUpdate: 'plan',
    sessionId: 'sess-1',
    entries,
  } as unknown as SessionUpdate;
}

describe('AcpTranscriptParser', () => {
  it('single user+assistant exchange produces one committed turn after endTurn', () => {
    const p = new AcpTranscriptParser(deps());
    p.push(userChunk('u1', 'hello'));
    p.push(assistantChunk('a1', 'hi'));
    p.endTurn();

    expect(p.history).toHaveLength(1);
    expect(p.activeTurn).toBeNull();

    const turn = p.history[0];
    expect(turn.id).toBe(makeTurnId(CID, 0));
    expect(turn.items).toHaveLength(2);
    expect(turn.items[0].kind).toBe('message');
    expect(turn.items[1].kind).toBe('message');
  });

  it('N user messages produce N committed turns after live push+endTurn sequence', () => {
    const p = new AcpTranscriptParser(deps());

    p.push(userChunk('u1', 'first'));
    p.push(assistantChunk('a1', 'one'));
    p.endTurn();

    p.push(userChunk('u2', 'second'));
    p.push(assistantChunk('a2', 'two'));
    p.endTurn();

    p.push(userChunk('u3', 'third'));
    p.push(assistantChunk('a3', 'three'));
    p.endTurn();

    expect(p.history).toHaveLength(3);
    expect(p.history[0].id).toBe(makeTurnId(CID, 0));
    expect(p.history[1].id).toBe(makeTurnId(CID, 1));
    expect(p.history[2].id).toBe(makeTurnId(CID, 2));
  });

  it('new user message automatically closes the previous turn (implicit boundary)', () => {
    const p = new AcpTranscriptParser(deps());

    p.push(userChunk('u1', 'first'));
    p.push(assistantChunk('a1', 'response'));
    // No explicit endTurn — the next user message should close this turn.
    p.push(userChunk('u2', 'second'));

    expect(p.history).toHaveLength(1);
    expect(p.activeTurn).not.toBeNull();
    expect(p.activeTurn?.id).toBe(makeTurnId(CID, 1));
  });

  // ── Multi-chunk same messageId stays one turn ─────────────────────────────

  it('multiple chunks with the same messageId accumulate into one message item', () => {
    const p = new AcpTranscriptParser(deps());
    p.push(userChunk('u1', 'hel'));
    p.push(userChunk('u1', 'lo')); // same messageId → same message row
    p.endTurn();

    const turn = p.history[0];
    const messages = turn.items.filter((i) => i.kind === 'message');
    expect(messages).toHaveLength(1);
    expect((messages[0] as { text: string }).text).toBe('hello');
  });

  it('chunks with different messageIds open different rows within the same turn', () => {
    const p = new AcpTranscriptParser(deps());
    p.push(userChunk('u1', 'question'));
    p.push(assistantChunk('a1', 'part1 '));
    p.push(assistantChunk('a1', 'part2')); // same assistant id → append
    p.endTurn();

    const turn = p.history[0];
    const messages = turn.items.filter((i) => i.kind === 'message');
    expect(messages).toHaveLength(2); // one user, one assistant
    const asst = messages.find((m) => (m as { role: string }).role === 'assistant') as {
      text: string;
    };
    expect(asst.text).toBe('part1 part2');
  });

  // ── Message id stability ──────────────────────────────────────────────────

  it('item ids are non-null and stable across chunks', () => {
    const p = new AcpTranscriptParser(deps());
    p.push(userChunk('u1', 'chunk1'));
    const turnId = makeTurnId(CID, 0);
    const expectedId = makeMessageId(turnId, 'u1', 'user');

    const liveItems = p.activeTurn?.items ?? [];
    expect(liveItems[0].id).toBe(expectedId);

    p.push(userChunk('u1', 'chunk2')); // same id, text appended
    expect(p.activeTurn?.items[0].id).toBe(expectedId);
  });

  it('synthesizes a segment id when messageId is absent', () => {
    const p = new AcpTranscriptParser(deps());
    // Simulate a provider that doesn't supply messageId (null)
    const update: SessionUpdate = {
      sessionUpdate: 'user_message_chunk',
      sessionId: 'sess-1',
      messageId: undefined,
      content: { type: 'text', text: 'hi' },
    } as unknown as SessionUpdate;
    p.push(update);

    const turnId = makeTurnId(CID, 0);
    const expectedId = makeMessageId(turnId, 'auto:user:0', 'user');
    expect(p.activeTurn?.items[0].id).toBe(expectedId);
  });

  it('segments id-less assistant message runs around tool calls', () => {
    const p = new AcpTranscriptParser(deps());
    p.push(userChunk('u1', 'do it'));
    p.push({
      sessionUpdate: 'agent_message_chunk',
      sessionId: 'sess-1',
      messageId: undefined,
      content: { type: 'text', text: 'before' },
    } as unknown as SessionUpdate);
    p.push(toolCallUpdate('tc1', 'Run command'));
    p.push({
      sessionUpdate: 'agent_message_chunk',
      sessionId: 'sess-1',
      messageId: undefined,
      content: { type: 'text', text: 'after' },
    } as unknown as SessionUpdate);

    const messages = (p.activeTurn?.items ?? []).filter((item) => item.kind === 'message');
    expect(messages.map((message) => message.text)).toEqual(['do it', 'before', 'after']);
    expect(messages.map((message) => message.id)).toEqual([
      makeMessageId(makeTurnId(CID, 0), 'u1', 'user'),
      makeMessageId(makeTurnId(CID, 0), 'auto:assistant:0', 'assistant'),
      makeMessageId(makeTurnId(CID, 0), 'auto:assistant:1', 'assistant'),
    ]);
    expect(messages.map((message) => message.seq)).toEqual([0, 1, 3]);
  });

  it('replay treats id-less user chunks after agent content as new turns', () => {
    const updates: SessionUpdate[] = [
      {
        sessionUpdate: 'user_message_chunk',
        sessionId: 'sess-1',
        content: { type: 'text', text: 'first' },
      } as unknown as SessionUpdate,
      {
        sessionUpdate: 'agent_message_chunk',
        sessionId: 'sess-1',
        content: { type: 'text', text: 'one' },
      } as unknown as SessionUpdate,
      {
        sessionUpdate: 'user_message_chunk',
        sessionId: 'sess-1',
        content: { type: 'text', text: 'second' },
      } as unknown as SessionUpdate,
      {
        sessionUpdate: 'agent_message_chunk',
        sessionId: 'sess-1',
        content: { type: 'text', text: 'two' },
      } as unknown as SessionUpdate,
    ];

    const result = AcpTranscriptParser.replay(updates, deps());
    expect(result.committed).toHaveLength(2);
    expect(
      result.committed.map((turn) =>
        turn.items.filter((item) => item.kind === 'message').map((item) => item.text)
      )
    ).toEqual([
      ['first', 'one'],
      ['second', 'two'],
    ]);
  });

  // ── Lazy agent-initiated turn ─────────────────────────────────────────────

  it('agent content with no preceding user message opens a lazy turn', () => {
    const p = new AcpTranscriptParser(deps());
    p.push(assistantChunk('a1', 'unsolicited'));
    p.endTurn();

    expect(p.history).toHaveLength(1);
    const turn = p.history[0];
    expect(turn.items[0].kind).toBe('message');
    expect((turn.items[0] as { role: string }).role).toBe('assistant');
  });

  // ── Thinking auto-finalize ────────────────────────────────────────────────

  it('open thinking row is finalized when a message chunk arrives', () => {
    const p = new AcpTranscriptParser(deps());
    p.push(userChunk('u1', 'question'));
    p.push(thoughtChunk('t1', 'thinking...'));
    // Thinking is still open — next content event should finalize it.
    p.push(assistantChunk('a1', 'answer'));

    const items = p.activeTurn?.items ?? [];
    const thinking = items.find((i) => i.kind === 'thinking') as { status: string } | undefined;
    expect(thinking?.status).toBe('done');
  });

  it('thinking row has correct id', () => {
    const p = new AcpTranscriptParser(deps());
    p.push(userChunk('u1', 'q'));
    p.push(thoughtChunk('t1', 'musing'));

    const turnId = makeTurnId(CID, 0);
    const expectedId = makeThinkingId(turnId, 't1');
    const items = p.activeTurn?.items ?? [];
    expect(items.find((i) => i.kind === 'thinking')?.id).toBe(expectedId);
  });

  // ── Tool call ─────────────────────────────────────────────────────────────

  it('tool_call creates an unknown tool-call row with running status', () => {
    const p = new AcpTranscriptParser(deps());
    p.push(userChunk('u1', 'do something'));
    p.push(toolCallUpdate('tc1', 'My Tool'));

    const items = p.activeTurn?.items ?? [];
    const tool = items.find((i) => i.kind === 'unknown-tool-call');
    expect(tool).toBeDefined();
    expect(tool).toMatchObject({
      id: makeToolId(makeTurnId(CID, 0), 'tc1'),
      status: 'running',
      toolCallId: 'tc1',
    });
  });

  it('tool_call_update updates tool-call status to done', () => {
    const p = new AcpTranscriptParser(deps());
    p.push(userChunk('u1', 'do it'));
    p.push(toolCallUpdate('tc1', 'My Tool'));
    p.push(toolUpdateDone('tc1'));

    const items = p.activeTurn?.items ?? [];
    const tool = items.find((i) => i.kind === 'unknown-tool-call');
    expect(tool).toMatchObject({ status: 'done' });
  });

  it('carries durable tool image refs across updates without duplicating replayed output', () => {
    const p = new AcpTranscriptParser(deps());
    p.push(userChunk('u1', 'make an image'));
    const first = { id: 'sha256-first', name: 'first.png', mimeType: 'image/png' as const };
    const second = { id: 'sha256-second', name: 'second.webp', mimeType: 'image/webp' as const };
    p.pushEvent({
      kind: 'tool_call',
      toolCallId: 'image-1',
      title: 'Image generation',
      toolKind: 'image-generation',
      status: 'in_progress',
      parentToolCallId: null,
      diffs: [],
      attachments: [first],
    });
    p.pushEvent({
      kind: 'tool_update',
      toolCallId: 'image-1',
      title: null,
      toolKind: 'image-generation',
      status: 'completed',
      parentToolCallId: null,
      diffs: [],
      attachments: [first, second],
    });

    expect(p.activeTurn?.items.find((item) => item.kind === 'unknown-tool-call')).toMatchObject({
      status: 'done',
      attachments: [first, second],
    });
    expect(JSON.stringify(p.activeTurn)).not.toContain('base64');
  });

  it('tool_call_update content materializes execute outputText', () => {
    const p = new AcpTranscriptParser(deps());
    p.push(userChunk('u1', 'run it'));
    p.push(toolCallUpdate('exec-1', 'printf "hello"', 'execute'));
    p.push(toolUpdateWithTextOutput('exec-1', '```console\nhello\n```'));

    expect(p.activeTurn?.items.find((i) => i.kind === 'execute-tool-call')).toMatchObject({
      command: 'printf "hello"',
      outputText: 'hello',
      status: 'done',
    });
  });

  it('preserves provider execute descriptions as inputSummary', () => {
    const p = new AcpTranscriptParser(deps());
    p.push(userChunk('u1', 'install dependencies'));
    p.push({
      ...toolCallUpdate('exec-1', 'pnpm install', 'execute'),
      description: 'Installing Dependencies',
    } as unknown as SessionUpdate);

    expect(p.activeTurn?.items.find((i) => i.kind === 'execute-tool-call')).toMatchObject({
      command: 'pnpm install',
      inputSummary: 'Installing Dependencies',
    });
  });

  it('passes through standard terminalId on execute tool updates', () => {
    const p = new AcpTranscriptParser(deps());
    p.push(userChunk('u1', 'run it'));
    p.push(toolCallUpdate('exec-1', 'pnpm test', 'execute'));
    p.push(toolUpdateWithTextOutput('exec-1', 'ok', 'term-1'));

    expect(p.activeTurn?.items.find((i) => i.kind === 'execute-tool-call')).toMatchObject({
      terminalId: 'term-1',
      outputText: 'ok',
    });
  });

  it('tool kinds can materialize richer tool rows', () => {
    const p = new AcpTranscriptParser(deps());
    p.push(userChunk('u1', 'use tools'));
    p.push(toolCallUpdate('search-1', "Search for 'symbols'", 'search'));
    p.push(toolCallUpdate('mcp-1', 'linear.searchIssues', 'mcp-tool'));
    p.push(toolCallUpdate('fetch-1', 'https://example.test', 'web-fetch'));
    p.push(toolCallUpdate('subagent-1', 'Investigate failure', 'subagent'));

    const items = p.activeTurn?.items ?? [];
    expect(items.find((i) => i.kind === 'search-tool-call')).toMatchObject({
      id: makeToolId(makeTurnId(CID, 0), 'search-1'),
      query: "for 'symbols'",
      status: 'running',
    });
    expect(items.find((i) => i.kind === 'mcp-tool-call')).toMatchObject({
      tool: 'linear.searchIssues',
    });
    expect(items.find((i) => i.kind === 'web-fetch-tool-call')).toMatchObject({
      url: 'https://example.test',
    });
    expect(items.find((i) => i.kind === 'spawn-subagent-tool-call')).toMatchObject({
      name: 'Investigate failure',
    });
  });

  it('pushEvent can materialize enriched special tool events', () => {
    const p = new AcpTranscriptParser(deps());
    p.push(userChunk('u1', 'search'));
    p.pushEvent({
      kind: 'search',
      toolCallId: 'search-1',
      query: 'search engine optimization',
      scope: 'web',
      status: 'completed',
      parentToolCallId: null,
      matchCount: 3,
    });

    expect(p.activeTurn?.items.find((i) => i.kind === 'search-tool-call')).toMatchObject({
      query: 'search engine optimization',
      scope: 'web',
      status: 'done',
      matchCount: 3,
    });
  });

  it('groups contiguous read tool calls into a deterministic tool group', () => {
    const p = new AcpTranscriptParser(deps());
    p.push(userChunk('u1', 'read files'));
    p.push(toolCallUpdate('read-1', 'Read src/a.ts', 'read'));
    p.push(toolCallUpdate('read-2', 'Read src/b.ts', 'read'));

    const items = p.activeTurn?.items ?? [];
    expect(items.find((i) => i.kind === 'tool-group')).toMatchObject({
      id: makeToolGroupId(makeToolId(makeTurnId(CID, 0), 'read-1')),
      label: '2 file reads',
      groupKind: 'read-batch',
      status: 'running',
      children: [
        { id: makeToolId(makeTurnId(CID, 0), 'read-1') },
        { id: makeToolId(makeTurnId(CID, 0), 'read-2') },
      ],
    });
  });

  it('does not group non-contiguous read tool calls', () => {
    const p = new AcpTranscriptParser(deps());
    p.push(userChunk('u1', 'read files'));
    p.push(toolCallUpdate('read-1', 'Read src/a.ts', 'read'));
    p.push(toolCallUpdate('exec-1', 'echo done', 'execute'));
    p.push(toolCallUpdate('read-2', 'Read src/b.ts', 'read'));

    expect(p.activeTurn?.items.filter((i) => i.kind === 'tool-group')).toHaveLength(0);
  });

  // ── File operation tool calls ─────────────────────────────────────────────

  it('diff arriving on tool_update creates a modify-file tool call', () => {
    const p = new AcpTranscriptParser(deps());
    p.push(userChunk('u1', 'edit file'));
    // Edit tool calls without diff content stay suppressed until file context arrives.
    p.push({
      sessionUpdate: 'tool_call',
      sessionId: 'sess-1',
      toolCallId: 'tc-edit',
      title: 'Edit file',
      kind: 'edit',
      status: 'in_progress',
      content: [],
    } as unknown as SessionUpdate);
    // diff arrives on tool_update
    p.push(toolUpdateWithDiff('tc-edit', 'src/foo.ts', 'old', 'new'));

    const items = p.activeTurn?.items ?? [];
    const turnId = makeTurnId(CID, 0);
    const toolId = makeToolId(turnId, 'tc-edit');
    expect(items.find((i) => i.kind === 'modify-file-tool-call')).toMatchObject({
      id: makeDiffId(toolId, 'src/foo.ts'),
      toolCallId: 'tc-edit',
      path: 'src/foo.ts',
      oldText: 'old',
      newText: 'new',
      status: 'done',
    });
  });

  it('oldText null creates a create-file tool call', () => {
    const p = new AcpTranscriptParser(deps());
    p.push(userChunk('u1', 'create file'));
    p.push(toolUpdateWithDiff('tc-create', 'src/new.ts', null, 'new file'));

    expect(p.activeTurn?.items.find((i) => i.kind === 'create-file-tool-call')).toMatchObject({
      toolCallId: 'tc-create',
      path: 'src/new.ts',
      content: 'new file',
    });
  });

  it('multi-file patch creates one file-operation item per path and fans out status', () => {
    const p = new AcpTranscriptParser(deps());
    p.push(userChunk('u1', 'patch files'));
    p.push({
      sessionUpdate: 'tool_call_update',
      sessionId: 'sess-1',
      toolCallId: 'tc-multi',
      title: 'Apply patch',
      kind: 'edit',
      status: 'in_progress',
      content: [
        { type: 'diff', path: 'src/a.ts', oldText: 'a', newText: 'aa' },
        { type: 'diff', path: 'src/b.ts', oldText: null, newText: 'b' },
      ],
    } as unknown as SessionUpdate);
    p.push(toolUpdateDone('tc-multi'));

    const fileOps =
      p.activeTurn?.items.filter(
        (i) => i.kind === 'modify-file-tool-call' || i.kind === 'create-file-tool-call'
      ) ?? [];
    expect(fileOps).toHaveLength(2);
    expect(fileOps.every((item) => item.toolCallId === 'tc-multi')).toBe(true);
    expect(fileOps.every((item) => item.status === 'done')).toBe(true);
  });

  it('diff-less edit tool_update does not create a placeholder tool call', () => {
    const p = new AcpTranscriptParser(deps());
    p.push(userChunk('u1', 'edit file'));
    p.push({
      sessionUpdate: 'tool_call_update',
      sessionId: 'sess-1',
      toolCallId: 'tc-edit',
      title: null,
      kind: 'edit',
      status: 'in_progress',
      content: [],
    } as unknown as SessionUpdate);

    expect(p.activeTurn?.items.filter((i) => i.kind.endsWith('-file-tool-call'))).toHaveLength(0);
  });

  // ── Plan ──────────────────────────────────────────────────────────────────

  it('plan update creates a plan row', () => {
    const p = new AcpTranscriptParser(deps());
    p.push(userChunk('u1', 'make a plan'));
    p.push(planUpdate([{ content: 'Step 1', status: 'pending', priority: 'high' }]));

    const items = p.activeTurn?.items ?? [];
    const plan = items.find((i) => i.kind === 'create-plan-tool-call');
    expect(plan).toMatchObject({
      kind: 'create-plan-tool-call',
      planId: SESSION_PLAN_ID,
      status: 'done',
    });
    expect(p.plan).toMatchObject({
      id: SESSION_PLAN_ID,
      entries: [
        {
          id: `${SESSION_PLAN_ID}:entry:0`,
          content: 'Step 1',
          status: 'pending',
          priority: 'high',
        },
      ],
    });
  });

  it('idle-phase plan opens an agent turn and updates the session-scoped plan slice', () => {
    const p = new AcpTranscriptParser(deps());
    p.push(planUpdate([{ content: 'Agent step', status: 'in_progress', priority: 'medium' }]), 100);

    expect(p.activeTurn?.initiator).toBe('agent');
    expect(p.activeTurn?.items.find((item) => item.kind === 'create-plan-tool-call')).toMatchObject(
      {
        status: 'running',
        planId: SESSION_PLAN_ID,
      }
    );
    expect(p.plan).toEqual({
      id: SESSION_PLAN_ID,
      entries: [
        {
          id: `${SESSION_PLAN_ID}:entry:0`,
          content: 'Agent step',
          status: 'in_progress',
          priority: 'medium',
        },
      ],
      updatedAt: 100,
    });
  });

  it('subagent events update the agents registry and preserve background rows on commit', () => {
    const p = new AcpTranscriptParser(deps());
    p.pushEvent(
      {
        kind: 'subagent',
        toolCallId: 'toolu_1',
        title: 'Find events',
        status: 'in_progress',
        parentToolCallId: null,
        background: true,
        agentId: 'agent-1',
        outputFile: '/tmp/agent-1.output',
      },
      100
    );
    p.endTurn(200);

    expect(p.agents).toEqual([
      {
        agentId: 'agent-1',
        toolCallId: 'toolu_1',
        launchTurnId: makeTurnId(CID, 0),
        name: 'Find events',
        status: 'running',
        startedAt: 100,
        background: true,
        outputFile: '/tmp/agent-1.output',
      },
    ]);
    expect(
      p.history[0].items.find((item) => item.kind === 'spawn-subagent-tool-call')
    ).toMatchObject({
      status: 'done',
      background: true,
      agentId: 'agent-1',
    });
  });

  it('subagent_update completes a background agent without opening a turn', () => {
    const p = new AcpTranscriptParser(deps());
    p.pushEvent(
      {
        kind: 'subagent',
        toolCallId: 'toolu_1',
        title: 'Find events',
        status: 'in_progress',
        parentToolCallId: null,
        background: true,
        agentId: 'agent-1',
      },
      100
    );
    p.endTurn(150);
    p.pushEvent(
      {
        kind: 'subagent_update',
        toolCallId: 'toolu_1',
        agentId: 'agent-1',
        status: 'completed',
        summary: 'Done',
      },
      300
    );

    expect(p.activeTurn).toBeNull();
    expect(p.agents[0]).toMatchObject({
      status: 'completed',
      completedAt: 300,
      summary: 'Done',
    });
  });

  // ── replay vs push+endTurn parity ─────────────────────────────────────────

  it('replay produces the same committed turns as push+endTurn for two exchanges', () => {
    const updates: SessionUpdate[] = [
      userChunk('u1', 'first prompt'),
      assistantChunk('a1', 'first response'),
      userChunk('u2', 'second prompt'),
      assistantChunk('a2', 'second response'),
    ];

    // Live path
    const live = new AcpTranscriptParser(deps());
    live.push(updates[0]);
    live.push(updates[1]);
    live.endTurn();
    live.push(updates[2]);
    live.push(updates[3]);
    live.endTurn();
    const liveHistory = live.history;

    // Replay path
    const replayResult = AcpTranscriptParser.replay(updates, deps());
    const replayHistory = replayResult.committed;

    expect(replayResult.active).toBeNull();
    expect(replayHistory).toHaveLength(2);
    expect(liveHistory).toHaveLength(2);

    // Same turn count and item counts per turn
    for (let i = 0; i < 2; i++) {
      expect(replayHistory[i].items).toHaveLength(liveHistory[i].items.length);
    }

    // Key invariant: message text is identical
    const liveText = liveHistory.flatMap((t: { items: { kind: string; text?: string }[] }) =>
      t.items.filter((i) => i.kind === 'message').map((i) => (i as { text: string }).text)
    );
    const replayText = replayHistory.flatMap((t: { items: { kind: string; text?: string }[] }) =>
      t.items.filter((i) => i.kind === 'message').map((i) => (i as { text: string }).text)
    );
    expect(replayText).toEqual(liveText);
  });

  it('replay and live preserve the same content while labeling timing provenance', () => {
    const updates = [userChunk('u1', 'hi'), assistantChunk('a1', 'hello')];

    const p = new AcpTranscriptParser(deps());
    p.push(updates[0], 0);
    p.push(updates[1], 1);
    p.endTurn(2);

    const replayResult = AcpTranscriptParser.replay(updates, deps());
    expect(replayResult.committed[0]?.items).toEqual(p.history[0]?.items);
    expect(replayResult.committed[0]?.timingSource).toBe('replay');
    expect(p.history[0]?.timingSource).toBe('live');
  });

  it('records a frozen wall-clock duration for completed live turns', () => {
    const p = new AcpTranscriptParser(deps());
    p.push(userChunk('u1', 'hi'), 1_000);
    p.push(assistantChunk('a1', 'hello'), 1_750);
    p.endTurn(2_250);

    expect(p.history[0]).toMatchObject({
      startedAt: 1_000,
      durationMs: 1_250,
      timingSource: 'live',
    });
  });

  it('beginReplay/endReplay reset and rebuild session-scoped slices idempotently', () => {
    const p = new AcpTranscriptParser(deps());
    const updates = [
      userChunk('u1', 'plan'),
      planUpdate([{ content: 'Step', status: 'pending', priority: 'low' }]),
    ];

    p.beginReplay(0);
    p.push(updates[0], 1);
    p.push(updates[1], 2);
    p.endReplay(3);
    p.beginReplay(4);
    p.push(updates[0], 5);
    p.push(updates[1], 6);
    p.endReplay(7);

    expect(p.history).toHaveLength(1);
    expect(p.plan).toEqual({
      id: SESSION_PLAN_ID,
      entries: [
        { id: `${SESSION_PLAN_ID}:entry:0`, content: 'Step', status: 'pending', priority: 'low' },
      ],
      updatedAt: 6,
    });
  });

  // ── Finalization on commit ────────────────────────────────────────────────

  it('committed turn messages do not expose reducer-owned streaming state', () => {
    const p = new AcpTranscriptParser(deps());
    p.push(userChunk('u1', 'hello'));
    p.push(assistantChunk('a1', 'world'));
    p.endTurn();

    const turn = p.history[0];
    for (const item of turn.items) {
      if (item.kind === 'message') {
        expect(item).not.toHaveProperty('streaming');
      }
    }
  });

  it('active turn messages do not expose reducer-owned streaming state', () => {
    const p = new AcpTranscriptParser(deps());
    p.push(userChunk('u1', 'hello'));
    p.push(assistantChunk('a1', 'world'));

    const activeMsgs = (p.activeTurn?.items ?? []).filter((i) => i.kind === 'message');
    for (const m of activeMsgs) {
      expect(m).not.toHaveProperty('streaming');
    }
  });

  it('assigns monotonic seq values to turns and items', () => {
    const p = new AcpTranscriptParser(deps());
    p.push(userChunk('u1', 'first'));
    p.push(assistantChunk('a1', 'one'));
    p.endTurn();
    p.push(userChunk('u2', 'second'));
    p.push(toolCallUpdate('tc1', 'My Tool'));

    expect(p.history[0].seq).toBe(0);
    expect(p.activeTurn?.seq).toBe(1);
    expect(p.activeTurn?.items.map((item) => item.seq)).toEqual([0, 1]);
  });

  // ── reset ─────────────────────────────────────────────────────────────────

  it('reset clears all state', () => {
    const p = new AcpTranscriptParser(deps());
    p.push(userChunk('u1', 'hello'));
    p.endTurn();
    expect(p.history).toHaveLength(1);

    p.reset();
    expect(p.history).toHaveLength(0);
    expect(p.activeTurn).toBeNull();
  });
});

// ── Session slice tests ──────────────────────────────────────────────────────

function configOptionUpdate(configOptions: unknown[]): SessionUpdate {
  return {
    sessionUpdate: 'config_option_update',
    sessionId: 'sess-1',
    configOptions,
  } as unknown as SessionUpdate;
}

function currentModeUpdate(currentModeId: string): SessionUpdate {
  return {
    sessionUpdate: 'current_mode_update',
    sessionId: 'sess-1',
    currentModeId,
  } as unknown as SessionUpdate;
}

function availableCommandsUpdate(availableCommands: unknown[]): SessionUpdate {
  return {
    sessionUpdate: 'available_commands_update',
    sessionId: 'sess-1',
    availableCommands,
  } as unknown as SessionUpdate;
}

function usageUpdate(
  used: number,
  size: number,
  cost?: { amount: number; currency: string }
): SessionUpdate {
  return {
    sessionUpdate: 'usage_update',
    sessionId: 'sess-1',
    used,
    size,
    cost: cost ?? null,
  } as unknown as SessionUpdate;
}

function sessionInfoUpdate(title: string): SessionUpdate {
  return {
    sessionUpdate: 'session_info_update',
    sessionId: 'sess-1',
    title,
  } as unknown as SessionUpdate;
}

describe('AcpTranscriptParser – session slices', () => {
  // ── Config derivation ──────────────────────────────────────────────────────

  it('config_option_update populates modelOptions, efforts, modeOptions', () => {
    const p = new AcpTranscriptParser(deps());
    p.push(
      configOptionUpdate([
        {
          id: 'model',
          category: 'model',
          type: 'select',
          currentValue: 'opus',
          options: [
            { value: 'opus', name: 'Opus' },
            { value: 'haiku', name: 'Haiku' },
          ],
        },
        {
          id: 'reasoning_effort',
          category: 'thought_level',
          type: 'select',
          currentValue: 'high',
          options: [
            { value: 'low', name: 'Low' },
            { value: 'high', name: 'High' },
          ],
        },
        {
          id: 'mode',
          category: 'mode',
          type: 'select',
          currentValue: 'default',
          options: [
            { value: 'default', name: 'Default' },
            { value: 'plan', name: 'Plan' },
          ],
        },
      ])
    );

    const { modelOptions, efforts, modeOptions } = p.config;

    expect(modelOptions?.configId).toBe('model');
    expect(modelOptions?.selected).toBe('opus');
    expect(modelOptions?.available).toHaveLength(2);
    expect(modelOptions?.available[0]).toEqual({ id: 'opus', name: 'Opus' });

    expect(efforts?.configId).toBe('reasoning_effort');
    expect(efforts?.selected).toBe('high');
    expect(efforts?.available).toHaveLength(2);
    expect(efforts?.available[1]).toEqual({ id: 'high', name: 'High' });

    expect(modeOptions?.configId).toBe('mode');
    expect(modeOptions?.selected).toBe('default');
    expect(modeOptions?.available).toHaveLength(2);
    expect(modeOptions?.available[0]).toEqual({ id: 'default', name: 'Default' });
  });

  it('config_option_update preserves description on options', () => {
    const p = new AcpTranscriptParser(deps());
    p.push(
      configOptionUpdate([
        {
          id: 'model',
          category: 'model',
          type: 'select',
          currentValue: 'opus',
          options: [{ value: 'opus', name: 'Opus', description: 'Most capable' }],
        },
      ])
    );
    expect(p.config.modelOptions?.available[0].description).toBe('Most capable');
  });

  it('unknown category (model_config) is ignored', () => {
    const p = new AcpTranscriptParser(deps());
    p.push(
      configOptionUpdate([
        {
          id: 'fast',
          category: 'model_config',
          type: 'select',
          currentValue: 'off',
          options: [
            { value: 'on', name: 'On' },
            { value: 'off', name: 'Off' },
          ],
        },
      ])
    );
    // No crash; all groups remain null since no recognized category was present
    expect(p.config.modelOptions).toBeNull();
    expect(p.config.efforts).toBeNull();
    expect(p.config.modeOptions).toBeNull();
  });

  // ── current_mode_update ────────────────────────────────────────────────────

  it('current_mode_update sets modeOptions.selected when modeOptions is already populated', () => {
    const p = new AcpTranscriptParser(deps());
    p.push(
      configOptionUpdate([
        {
          id: 'mode',
          category: 'mode',
          type: 'select',
          currentValue: 'default',
          options: [
            { value: 'default', name: 'Default' },
            { value: 'acceptEdits', name: 'Accept Edits' },
          ],
        },
      ])
    );
    expect(p.config.modeOptions?.selected).toBe('default');

    p.push(currentModeUpdate('acceptEdits'));
    expect(p.config.modeOptions?.selected).toBe('acceptEdits');
    // available list unchanged
    expect(p.config.modeOptions?.available).toHaveLength(2);
  });

  it('current_mode_update is a no-op when modeOptions is null', () => {
    const p = new AcpTranscriptParser(deps());
    p.push(currentModeUpdate('acceptEdits'));
    expect(p.config.modeOptions).toBeNull();
  });

  // ── available_commands_update ──────────────────────────────────────────────

  it('available_commands_update populates availableCommands', () => {
    const p = new AcpTranscriptParser(deps());
    p.push(
      availableCommandsUpdate([
        { name: 'review', description: 'Review code' },
        { name: 'debug', description: 'Enable debug', input: { hint: '[issue]' } },
      ])
    );
    expect(p.config.availableCommands).toHaveLength(2);
    expect(p.config.availableCommands[0]).toEqual({
      name: 'review',
      description: 'Review code',
      source: 'provider-command',
    });
    expect(p.config.availableCommands[1]).toEqual({
      name: 'debug',
      description: 'Enable debug',
      source: 'provider-command',
      inputHint: '[issue]',
    });
  });

  it('available_commands_update replaces previous list', () => {
    const p = new AcpTranscriptParser(deps());
    p.push(availableCommandsUpdate([{ name: 'a', description: 'A' }]));
    p.push(
      availableCommandsUpdate([
        { name: 'b', description: 'B' },
        { name: 'c', description: 'C' },
      ])
    );
    expect(p.config.availableCommands).toHaveLength(2);
    expect(p.config.availableCommands[0].name).toBe('b');
  });

  // ── usage_update ───────────────────────────────────────────────────────────

  it('usage_update sets usage fields correctly', () => {
    const p = new AcpTranscriptParser(deps());
    p.push(usageUpdate(1000, 200000, { amount: 0.02, currency: 'USD' }));
    expect(p.usage).toEqual({
      contextUsed: 1000,
      contextSize: 200000,
      cost: { amount: 0.02, currency: 'USD' },
    });
  });

  it('usage_update with no cost sets cost to null', () => {
    const p = new AcpTranscriptParser(deps());
    p.push(usageUpdate(500, 100000));
    expect(p.usage?.cost).toBeNull();
  });

  it('usage_update overwrites previous usage', () => {
    const p = new AcpTranscriptParser(deps());
    p.push(usageUpdate(1000, 200000));
    p.push(usageUpdate(2000, 200000));
    expect(p.usage?.contextUsed).toBe(2000);
  });

  // ── session_info_update ────────────────────────────────────────────────────

  it('session_info_update sets title', () => {
    const p = new AcpTranscriptParser(deps());
    p.push(sessionInfoUpdate('My session title'));
    expect(p.title).toBe('My session title');
  });

  it('session_info_update overwrites previous title', () => {
    const p = new AcpTranscriptParser(deps());
    p.push(sessionInfoUpdate('First'));
    p.push(sessionInfoUpdate('Second'));
    expect(p.title).toBe('Second');
  });

  // ── No turn boundary side-effect ───────────────────────────────────────────

  it('config/usage/title events do NOT open a transcript turn', () => {
    const p = new AcpTranscriptParser(deps());
    p.push(
      configOptionUpdate([
        { id: 'model', category: 'model', type: 'select', currentValue: 'opus', options: [] },
      ])
    );
    p.push(usageUpdate(100, 200000));
    p.push(sessionInfoUpdate('A title'));
    p.push(availableCommandsUpdate([{ name: 'foo', description: 'Foo' }]));

    // None of the above should open a turn
    expect(p.activeTurn).toBeNull();
    expect(p.history).toHaveLength(0);
  });

  // ── reset clears session slices ────────────────────────────────────────────

  it('reset clears config, usage, and title', () => {
    const p = new AcpTranscriptParser(deps());
    p.push(usageUpdate(1000, 200000));
    p.push(sessionInfoUpdate('Some title'));
    p.push(
      configOptionUpdate([
        { id: 'model', category: 'model', type: 'select', currentValue: 'opus', options: [] },
      ])
    );
    p.reset();
    expect(p.usage).toBeNull();
    expect(p.title).toBeNull();
    expect(p.config.modelOptions).toBeNull();
    expect(p.config.availableCommands).toHaveLength(0);
  });

  // ── static replay includes session slices ──────────────────────────────────

  it('static replay returns config, usage, title alongside transcript', () => {
    const updates = [
      configOptionUpdate([
        {
          id: 'model',
          category: 'model',
          type: 'select',
          currentValue: 'haiku',
          options: [{ value: 'haiku', name: 'Haiku' }],
        },
      ]),
      usageUpdate(500, 100000, { amount: 0.001, currency: 'USD' }),
      sessionInfoUpdate('Replay title'),
    ] as unknown as SessionUpdate[];

    const result = AcpTranscriptParser.replay(updates as Iterable<SessionUpdate>, deps());
    expect(result.active).toBeNull();
    expect(result.config.modelOptions?.selected).toBe('haiku');
    expect(result.usage?.contextUsed).toBe(500);
    expect(result.title).toBe('Replay title');
  });
});

describe('foldItem tool results', () => {
  const turnId = 'turn-1';

  it('keeps a bounded text result on non-execute tool rows', () => {
    let items = foldItem(
      [],
      {
        kind: 'search',
        toolCallId: 's1',
        query: 'stopReason',
        scope: 'workspace',
        status: 'in_progress',
        parentToolCallId: null,
      },
      turnId,
      1
    );
    items = foldItem(
      items,
      {
        kind: 'search',
        toolCallId: 's1',
        query: 'stopReason',
        scope: 'workspace',
        status: 'completed',
        parentToolCallId: null,
        outputText: 'src/a.ts\nsrc/b.ts',
      },
      turnId,
      2
    );
    expect(items[0]).toMatchObject({
      kind: 'search-tool-call',
      status: 'done',
      outputText: 'src/a.ts\nsrc/b.ts',
    });
  });

  it('records the first output line as the failure reason', () => {
    let items = foldItem(
      [],
      {
        kind: 'tool_call',
        toolCallId: 'c1',
        title: 'npm test',
        toolKind: 'execute',
        status: 'in_progress',
        parentToolCallId: null,
        diffs: [],
      },
      turnId,
      1
    );
    items = foldItem(
      items,
      {
        kind: 'tool_update',
        toolCallId: 'c1',
        title: null,
        toolKind: 'execute',
        status: 'failed',
        parentToolCallId: null,
        diffs: [],
        outputText: '\nError: 2 tests failed\n  at suite',
      },
      turnId,
      2
    );
    expect(items[0]).toMatchObject({
      kind: 'execute-tool-call',
      status: 'error',
      error: 'Error: 2 tests failed',
    });
  });

  it('folds subagent updates into the spawn row they belong to', () => {
    let items = foldItem(
      [],
      {
        kind: 'subagent',
        toolCallId: 'a1',
        title: 'Codex agent',
        status: 'in_progress',
        parentToolCallId: null,
        agentId: 'thread-9',
        background: true,
      },
      turnId,
      1
    );
    items = foldItem(
      items,
      {
        kind: 'subagent_update',
        agentId: 'thread-9',
        status: 'completed',
        summary: 'Found 3 files',
      },
      turnId,
      2
    );
    expect(items[0]).toMatchObject({
      kind: 'spawn-subagent-tool-call',
      status: 'done',
      outputText: 'Found 3 files',
    });
    expect(
      foldItem(
        items,
        { kind: 'subagent_update', agentId: 'someone-else', status: 'failed' },
        turnId,
        3
      )
    ).toBe(items);
  });
});

describe('foldItem surfaced shapes', () => {
  const turnId = 'turn-2';

  it('adds a row per linked resource and never lists a uri twice', () => {
    const link = { uri: 'file:///repo/models/plate.step', name: 'plate.step' };
    let items = foldItem(
      [],
      { kind: 'message', role: 'assistant', messageId: 'm1', text: 'Here it is:' },
      turnId,
      1
    );
    items = foldItem(
      items,
      { kind: 'message', role: 'assistant', messageId: 'm1', text: '', links: [link] },
      turnId,
      2
    );
    items = foldItem(
      items,
      { kind: 'message', role: 'assistant', messageId: 'm1', text: '', links: [link] },
      turnId,
      3
    );
    expect(items.map((item) => item.kind)).toEqual(['message', 'resource-link']);
    expect(items[1]).toMatchObject({
      uri: link.uri,
      name: 'plate.step',
      target: { kind: 'workspace-file', path: '/repo/models/plate.step' },
    });
  });

  it('never creates an empty message from an image-only chunk without attachments', () => {
    expect(
      foldItem([], { kind: 'message', role: 'assistant', messageId: 'm2', text: '' }, turnId, 1)
    ).toEqual([]);
  });

  it('shows an edit that reported no diff and replaces it once the diff arrives', () => {
    let items = foldItem(
      [],
      {
        kind: 'tool_call',
        toolCallId: 'e1',
        title: 'Edit',
        toolKind: 'edit',
        status: 'in_progress',
        parentToolCallId: null,
        diffs: [],
        locations: [{ path: '/repo/src/a.ts' }],
      },
      turnId,
      1
    );
    expect(items[0]).toMatchObject({
      kind: 'unknown-tool-call',
      name: 'Edit',
      inputSummary: '/repo/src/a.ts',
    });
    items = foldItem(
      items,
      {
        kind: 'tool_update',
        toolCallId: 'e1',
        title: null,
        toolKind: 'edit',
        status: 'completed',
        parentToolCallId: null,
        diffs: [{ path: '/repo/src/a.ts', oldText: 'a', newText: 'b' }],
      },
      turnId,
      2
    );
    expect(items.map((item) => item.kind)).toEqual(['modify-file-tool-call']);
  });

  it('reads the path from Codex titles and from locations', () => {
    const fromTitle = foldItem(
      [],
      {
        kind: 'tool_call',
        toolCallId: 'r1',
        title: "Read file '/repo/src/a.ts'",
        toolKind: 'read',
        status: 'in_progress',
        parentToolCallId: null,
        diffs: [],
      },
      turnId,
      1
    );
    expect(fromTitle[0]).toMatchObject({ kind: 'read-tool-call', path: '/repo/src/a.ts' });
    const fromLocations = foldItem(
      [],
      {
        kind: 'tool_call',
        toolCallId: 'r2',
        title: 'Reading',
        toolKind: 'read',
        status: 'in_progress',
        parentToolCallId: null,
        diffs: [],
        locations: [{ path: '/repo/src/b.ts' }],
      },
      turnId,
      1
    );
    expect(fromLocations[0]).toMatchObject({ kind: 'read-tool-call', path: '/repo/src/b.ts' });
  });

  it('keeps the plan as this turn last saw it on the plan row', () => {
    const items = foldItem(
      [],
      {
        kind: 'plan',
        entries: [{ content: 'Write tests', status: 'in_progress', priority: 'high' }],
      },
      turnId,
      1
    );
    expect(items[0]).toMatchObject({
      kind: 'create-plan-tool-call',
      entries: [{ content: 'Write tests', status: 'in_progress', priority: 'high' }],
    });
  });

  it('records provider progress on a running tool row', () => {
    let items = foldItem(
      [],
      {
        kind: 'tool_call',
        toolCallId: 'p1',
        title: 'linear.search',
        toolKind: 'other',
        status: 'in_progress',
        parentToolCallId: null,
        diffs: [],
      },
      turnId,
      1
    );
    items = foldItem(
      items,
      {
        kind: 'tool_update',
        toolCallId: 'p1',
        title: null,
        toolKind: null,
        status: null,
        parentToolCallId: null,
        diffs: [],
        progress: 'fetching issues (page 2)',
      },
      turnId,
      2
    );
    expect(items[0]).toMatchObject({ status: 'running', progress: 'fetching issues (page 2)' });
  });
});
