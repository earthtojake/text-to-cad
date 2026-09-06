import type { TranscriptTurn } from '@emdash/core/runtimes/acp/api/client';
import { describe, expect, it } from 'vitest';
import { deriveAgentProgress } from './agent-progress';

function turn(items: TranscriptTurn['items']): TranscriptTurn {
  return { id: 'turn-1', seq: 1, initiator: 'user', items };
}

describe('deriveAgentProgress', () => {
  it('shows startup before the provider emits transcript content', () => {
    expect(deriveAgentProgress(null, false)).toEqual({ phase: 'Starting', thinkingTokens: 0 });
  });

  it('counts streamed reasoning and reports the thinking phase', () => {
    expect(
      deriveAgentProgress(
        turn([
          {
            kind: 'thinking',
            id: 'thinking-1',
            seq: 1,
            segmentId: 'segment-1',
            status: 'thinking',
            text: '12345678',
            startedAt: 10,
          },
        ]),
        false
      )
    ).toEqual({ phase: 'Thinking', thinkingTokens: 2 });
  });

  it('makes permission waits explicit', () => {
    expect(deriveAgentProgress(turn([]), true).phase).toBe('Waiting for approval');
  });

  it('uses plain-language phases for model work and responses', () => {
    expect(
      deriveAgentProgress(
        turn([
          {
            kind: 'modify-file-tool-call',
            id: 'tool-1',
            seq: 1,
            toolCallId: 'call-1',
            title: 'Edit source',
            status: 'running',
            path: 'part.step.py',
            oldText: 'a',
            newText: 'b',
          },
        ]),
        false
      ).phase
    ).toBe('Updating model files');

    expect(
      deriveAgentProgress(
        turn([{ kind: 'message', id: 'message-1', seq: 1, role: 'assistant', text: 'Done' }]),
        false
      ).phase
    ).toBe('Writing response');
  });

  it('names visible external-tool activity instead of calling everything CAD work', () => {
    expect(
      deriveAgentProgress(
        turn([
          {
            kind: 'search-tool-call',
            id: 'search-1',
            seq: 1,
            toolCallId: 'call-search',
            title: 'current STEP standard',
            status: 'running',
            query: 'current STEP standard',
            scope: 'web',
          },
        ]),
        false
      ).phase
    ).toBe('Searching the web');

    expect(
      deriveAgentProgress(
        turn([
          {
            kind: 'unknown-tool-call',
            id: 'image-1',
            seq: 1,
            toolCallId: 'call-image',
            title: 'Image generation',
            status: 'running',
            name: 'Image generation',
            toolKind: 'image-generation',
          },
        ]),
        false
      ).phase
    ).toBe('Generating image');
  });
});
