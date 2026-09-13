import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { runInNewContext } from 'node:vm';
import type { SessionUpdate } from '@agentclientprotocol/sdk';
import { AcpTranscriptParser, decodeSessionUpdate } from '@emdash/core/runtimes/acp/api';
import { describe, expect, it } from 'vitest';
import { enrichCodexUpdate } from './acp-transform';

const require = createRequire(import.meta.url);
const adapter = readFileSync(
  require.resolve('@agentclientprotocol/codex-acp/dist/index.js'),
  'utf8'
);

// Exercise the patched dependency's actual pure helpers. It exports only its
// CLI entry point, which otherwise starts a real provider process on import.
function between(start: string, end: string): string {
  const from = adapter.indexOf(start);
  const to = adapter.indexOf(end, from);
  if (from < 0 || to < 0) throw new Error('Codex adapter changed; review the lifecycle patch');
  return adapter.slice(from, to);
}

const { activity, merge } = runInNewContext(
  `${between('function createSubAgentActivityUpdate(', 'function createCollabAgentToolCallUpdate(')}
   ${between('function mergeHistoryUpdates(', 'function getRequestedMcpServerNames(')}
   ({ activity: createSubAgentActivityUpdate, merge: mergeHistoryUpdates })`
) as {
  activity: (item: Record<string, string>) => SessionUpdate;
  merge: (fallback: SessionUpdate[], typed: SessionUpdate[]) => SessionUpdate[];
};

describe('Codex typed child history', () => {
  it('keeps two named child lifecycles over same-id raw tool fallbacks on replay', () => {
    const started = ['dimensions', 'slot'].map((name) =>
      activity({
        type: 'subAgentActivity',
        id: `spawn-${name}`,
        kind: 'started',
        agentThreadId: `child-${name}`,
        agentPath: `/root/${name}`,
      })
    );
    const completed = ['dimensions', 'slot'].map((name) =>
      activity({
        type: 'subAgentActivity',
        id: `done-${name}`,
        kind: 'completed',
        agentThreadId: `child-${name}`,
        agentPath: `/root/${name}`,
      })
    );
    const fallback = [...started, ...completed].flatMap((update) => [
      { ...update, title: 'spawn_agent', rawInput: { task_name: 'opaque raw tool' } },
      {
        sessionUpdate: 'tool_call_update',
        toolCallId: 'toolCallId' in update ? update.toolCallId : '',
        status: 'completed',
      },
    ]) as SessionUpdate[];
    const updates = merge(fallback, [...started, ...completed]);
    expect(updates).toHaveLength(4);
    const parser = new AcpTranscriptParser({ conversationId: 'reopened' });
    parser.beginReplay();
    for (const update of updates) {
      const event = decodeSessionUpdate(update);
      expect(event).not.toBeNull();
      if (event) parser.pushEvent(enrichCodexUpdate(event, update));
    }
    parser.endReplay();
    expect(parser.agents.map(({ name, status }) => ({ name, status }))).toEqual([
      { name: 'dimensions', status: 'completed' },
      { name: 'slot', status: 'completed' },
    ]);
  });
});
