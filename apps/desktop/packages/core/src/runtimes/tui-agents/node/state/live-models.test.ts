import { describe, expect, it } from 'vitest';
import type { TuiAgentState, TuiSessionState } from '#runtimes/tui-agents/api';
import {
  createTuiAgentStatesLiveModel,
  createTuiSessionsLiveModel,
  produceCell,
} from './live-models';

function sessionFixture(conversationId: string): TuiSessionState {
  return {
    conversationId,
    sessionId: null,
    status: 'running',
    cols: 80,
    rows: 24,
    resume: null,
    startedAt: 0,
  };
}

function agentStateFixture(conversationId: string): TuiAgentState {
  return { conversationId, status: 'working', updatedAt: 0 };
}

describe('TUI live models', () => {
  it('executes cell producers once', async () => {
    const liveModel = createTuiSessionsLiveModel();
    let calls = 0;

    produceCell(liveModel.model.states.list, () => {
      calls += 1;
    });

    expect(calls).toBe(1);
    await liveModel.dispose();
  });

  it('serves the current sessions list as the snapshot on subscribe', async () => {
    const liveModel = createTuiSessionsLiveModel();
    produceCell(liveModel.model.states.list, (draft) => {
      draft['conv-1'] = sessionFixture('conv-1');
    });

    const lease = liveModel.acquireState(undefined, 'list');
    const source = await lease.ready();

    expect((await source.snapshot()).data).toEqual({ 'conv-1': sessionFixture('conv-1') });

    await lease.release();
    await liveModel.dispose();
  });

  it('publishes sessions cell writes to live subscribers', async () => {
    const liveModel = createTuiSessionsLiveModel();
    const lease = liveModel.acquireState(undefined, 'list');
    const source = await lease.ready();

    const notified = new Promise<void>((resolve) => {
      source.subscribe(() => resolve());
    });
    produceCell(liveModel.model.states.list, (draft) => {
      draft['conv-2'] = sessionFixture('conv-2');
    });
    await notified;

    expect((await source.snapshot()).data).toEqual({ 'conv-2': sessionFixture('conv-2') });

    await lease.release();
    await liveModel.dispose();
  });

  it('serves and publishes the agent-states list through the exposed provider', async () => {
    const liveModel = createTuiAgentStatesLiveModel();
    produceCell(liveModel.model.states.list, (draft) => {
      draft['conv-1'] = agentStateFixture('conv-1');
    });

    const lease = liveModel.acquireState(undefined, 'list');
    const source = await lease.ready();
    expect((await source.snapshot()).data).toEqual({ 'conv-1': agentStateFixture('conv-1') });

    const notified = new Promise<void>((resolve) => {
      source.subscribe(() => resolve());
    });
    produceCell(liveModel.model.states.list, (draft) => {
      draft['conv-1'] = { ...agentStateFixture('conv-1'), status: 'completed' };
    });
    await notified;

    expect((await source.snapshot()).data).toEqual({
      'conv-1': { ...agentStateFixture('conv-1'), status: 'completed' },
    });

    await lease.release();
    await liveModel.dispose();
  });
});
