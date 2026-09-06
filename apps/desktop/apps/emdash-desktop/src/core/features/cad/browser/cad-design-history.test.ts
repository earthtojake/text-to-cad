import type { TranscriptTurn } from '@emdash/chat-ui';
import { describe, expect, it } from 'vitest';
import {
  cadOutputPath,
  formatWorkedDuration,
  summarizeCadTurns,
  visibleCadPrompt,
} from './cad-design-history-model';

describe('visibleCadPrompt', () => {
  it('removes the internal CAD workspace context from the visible request', () => {
    expect(
      visibleCadPrompt(
        "Increase the radius.\nYou are working from Hardcore's integrated CAD workspace.\nThe current CAD target is: part.step"
      )
    ).toBe('Increase the radius.');
  });
});

describe('cadOutputPath', () => {
  it('labels a STEP generator with the artifact it produces', () => {
    expect(cadOutputPath('examples/cad/plate.step.py')).toBe('examples/cad/plate.step');
    expect(cadOutputPath('examples/cad/plate.stp.py')).toBe('examples/cad/plate.stp');
    expect(cadOutputPath('examples/cad/plate.py')).toBe('examples/cad/plate.step');
    expect(cadOutputPath('examples/cad/plate.step')).toBe('examples/cad/plate.step');
  });
});

describe('formatWorkedDuration', () => {
  it('formats completed turn durations in a compact disclosure label', () => {
    expect(formatWorkedDuration(200)).toBe('Worked for <1s');
    expect(formatWorkedDuration(74_050)).toBe('Worked for 1m 14s');
    expect(formatWorkedDuration(4_489_900)).toBe('Worked for 1h 14m 49s');
  });

  it('keeps legacy untimed turns useful', () => {
    expect(formatWorkedDuration()).toBe('Work details');
  });
});

describe('summarizeCadTurns', () => {
  it('keeps the design request and conclusion primary while grouping execution', () => {
    const turn = {
      id: 'turn-1',
      seq: 1,
      initiator: 'user',
      outcome: { kind: 'done' },
      startedAt: 1_700_000_000_000,
      durationMs: 74_000,
      items: [
        {
          kind: 'message',
          id: 'user-1',
          seq: 0,
          role: 'user',
          text: 'Increase the boss radius to 16 mm.',
        },
        {
          kind: 'execute-tool-call',
          id: 'tool-1',
          seq: 1,
          toolCallId: 'call-1',
          title: 'Validate the regenerated STEP file',
          status: 'done',
          command: 'python inspect.py hardcore-demo.step',
        },
        {
          kind: 'message',
          id: 'assistant-1',
          seq: 2,
          role: 'assistant',
          text: 'Updated the boss radius and validated the solid.',
        },
      ],
    } satisfies TranscriptTurn;

    expect(summarizeCadTurns([turn], null, 'hardcore-demo.step')).toEqual([
      expect.objectContaining({
        id: 'turn-1',
        userText: 'Increase the boss radius to 16 mm.',
        assistantText: 'Updated the boss radius and validated the solid.',
        state: 'completed',
        durationMs: 74_000,
        thinkingTokens: 0,
        activities: [
          expect.objectContaining({
            title: 'Validate the regenerated STEP file',
            detail: 'python inspect.py hardcore-demo.step',
          }),
        ],
        artifacts: [{ path: 'hardcore-demo.step', operation: 'model' }],
      }),
    ]);
  });

  it('prefers a persisted duration over synthetic replay timing', () => {
    const turn = {
      id: 'turn-replayed',
      seq: 1,
      initiator: 'user',
      startedAt: 0,
      durationMs: 2,
      timingSource: 'replay',
      outcome: { kind: 'done' },
      items: [
        {
          kind: 'execute-tool-call',
          id: 'tool-replayed',
          seq: 0,
          toolCallId: 'call-replayed',
          title: 'Inspect model',
          status: 'done',
        },
      ],
    } satisfies TranscriptTurn;

    expect(
      summarizeCadTurns([turn], null, 'model.step', { 'turn-replayed': 20_000 })[0]?.durationMs
    ).toBe(20_000);
    expect(
      summarizeCadTurns([turn], null, 'model.step', { 'turn-replayed': 2 })[0]?.durationMs
    ).toBeUndefined();
    expect(summarizeCadTurns([turn], null, 'model.step')[0]?.durationMs).toBeUndefined();
  });

  it('surfaces files changed by the turn and omits reasoning from the activity list', () => {
    const turn = {
      id: 'turn-2',
      seq: 2,
      initiator: 'user',
      outcome: { kind: 'done' },
      items: [
        {
          kind: 'thinking',
          id: 'thinking-1',
          seq: 0,
          segmentId: 'segment-1',
          text: 'Checking the feature tree.',
          status: 'done',
          startedAt: 1,
        },
        {
          kind: 'modify-file-tool-call',
          id: 'tool-2',
          seq: 1,
          toolCallId: 'call-2',
          title: 'Update generator',
          status: 'done',
          path: 'hardcore-demo.step.py',
          oldText: 'boss_radius = 15',
          newText: 'boss_radius = 16',
        },
      ],
    } satisfies TranscriptTurn;

    const [summary] = summarizeCadTurns([turn], null, 'hardcore-demo.step');

    expect(summary?.activities).toHaveLength(1);
    expect(summary?.thinkingTokens).toBeGreaterThan(0);
    expect(summary?.artifacts).toEqual([
      { path: 'hardcore-demo.step.py', operation: 'updated' },
      { path: 'hardcore-demo.step', operation: 'model' },
    ]);
  });

  it('keeps the active turn open without claiming the model is finished', () => {
    const activeTurn = {
      id: 'turn-active',
      seq: 3,
      initiator: 'user',
      items: [
        {
          kind: 'execute-tool-call',
          id: 'tool-active',
          seq: 0,
          toolCallId: 'call-active',
          title: 'Generate STEP',
          status: 'running',
          command: 'python hardcore-demo.step.py',
        },
      ],
    } satisfies TranscriptTurn;

    const [summary] = summarizeCadTurns([activeTurn], 'turn-active', 'hardcore-demo.step');

    expect(summary?.state).toBe('working');
    expect(summary?.artifacts).toEqual([]);
  });
});
