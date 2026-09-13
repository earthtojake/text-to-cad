import { err, ok, type Result } from '@emdash/shared';
import { ManualClock } from '@emdash/shared/testing';
import { describe, expect, it, vi } from 'vitest';
import type { ConversationReportError } from '../api/schemas';
import { createConversationLifecycleReporter } from './reporter';

type Report = Promise<Result<void, ConversationReportError>>;

// The lifecycle reporter is the feeders' half of conv.sole-writer: session runtimes report
// facts through it into the index and tolerate report failure (log-and-continue) — a lost
// report is repaired by the next report or the next resume (spec §3.4).

function makeClient() {
  return {
    reports: {
      sessionStarted: vi.fn(async (): Report => ok(undefined)),
      providerSessionId: vi.fn(async (): Report => ok(undefined)),
      sessionActivity: vi.fn(async (): Report => ok(undefined)),
      sessionEnded: vi.fn(async (): Report => ok(undefined)),
    },
  };
}

describe('conversation lifecycle reporter', () => {
  it('forwards started, provider-id, and ended reports', async () => {
    const client = makeClient();
    const reporter = createConversationLifecycleReporter({ client });

    reporter.sessionStarted({
      conversationId: 'conv-1',
      providerSessionId: 'session-1',
      resumeOutcome: 'loaded',
    });
    reporter.providerSessionId({ conversationId: 'conv-1', providerSessionId: 'session-2' });
    reporter.sessionEnded('conv-1');

    await vi.waitFor(() => {
      expect(client.reports.sessionStarted).toHaveBeenCalledWith({
        conversationId: 'conv-1',
        providerSessionId: 'session-1',
        resumeOutcome: 'loaded',
      });
      expect(client.reports.providerSessionId).toHaveBeenCalledWith({
        conversationId: 'conv-1',
        providerSessionId: 'session-2',
      });
      expect(client.reports.sessionEnded).toHaveBeenCalledWith({ conversationId: 'conv-1' });
    });
  });

  it('throttles activity reports per conversation', async () => {
    const client = makeClient();
    const clock = new ManualClock(0);
    const reporter = createConversationLifecycleReporter({
      client,
      clock,
      activityDebounceMs: 10_000,
    });

    reporter.activity('conv-1');
    reporter.activity('conv-1');
    reporter.activity('conv-2');
    await vi.waitFor(() => {
      expect(client.reports.sessionActivity).toHaveBeenCalledTimes(2);
    });

    await clock.advanceBy(9_999);
    reporter.activity('conv-1');
    expect(client.reports.sessionActivity).toHaveBeenCalledTimes(2);

    await clock.advanceBy(1);
    reporter.activity('conv-1');
    await vi.waitFor(() => {
      expect(client.reports.sessionActivity).toHaveBeenCalledTimes(3);
    });
  });

  it('never throws when the index rejects or errors — log-and-continue', async () => {
    const warn = vi.fn();
    const client = makeClient();
    client.reports.sessionStarted.mockImplementation(async () =>
      err({
        type: 'conversation-not-found' as const,
        conversationId: 'conv-1',
        message: 'gone',
      })
    );
    client.reports.sessionEnded.mockImplementation(async () => {
      throw new Error('wire transport down');
    });
    const reporter = createConversationLifecycleReporter({
      client,
      logger: { warn } as never,
    });

    expect(() => {
      reporter.sessionStarted({
        conversationId: 'conv-1',
        providerSessionId: null,
        resumeOutcome: null,
      });
      reporter.sessionEnded('conv-1');
    }).not.toThrow();

    await vi.waitFor(() => {
      expect(warn).toHaveBeenCalledTimes(2);
    });
  });
});
