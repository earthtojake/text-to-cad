import type { Result } from '@emdash/shared';
import { noopLogger, type Logger } from '@emdash/shared/logger';
import { systemClock, type Clock } from '@emdash/shared/scheduling';
import type { ContractClient } from '@emdash/wire/rpc';
import type { ConversationReportsContract } from '../api/contract';
import type { ReportProviderSessionIdInput, ReportSessionStartedInput } from '../api/schemas';

export type ConversationReportsClient = ContractClient<ConversationReportsContract>;

/**
 * Fire-and-forget surface the session runtimes use to feed the conversation index
 * (spec §3.3). Reports are one-way, same-host calls; failures are logged and swallowed —
 * a lost report is repaired by the next report or the next resume. Activity reports are
 * throttled per conversation.
 */
export type ConversationLifecycleReporter = {
  sessionStarted(input: ReportSessionStartedInput): void;
  providerSessionId(input: ReportProviderSessionIdInput): void;
  activity(conversationId: string): void;
  sessionEnded(conversationId: string): void;
};

export type CreateConversationLifecycleReporterOptions = {
  client: ConversationReportsClient;
  logger?: Logger;
  clock?: Clock;
  activityDebounceMs?: number;
};

const DEFAULT_ACTIVITY_DEBOUNCE_MS = 15_000;

export function createConversationLifecycleReporter(
  options: CreateConversationLifecycleReporterOptions
): ConversationLifecycleReporter {
  const logger = options.logger ?? noopLogger;
  const clock = options.clock ?? systemClock;
  const debounceMs = options.activityDebounceMs ?? DEFAULT_ACTIVITY_DEBOUNCE_MS;
  const lastActivityReportAt = new Map<string, number>();

  function deliver(label: string, report: Promise<Result<void, unknown>>): void {
    void report
      .then((result) => {
        if (!result.success) {
          logger.warn(`conversation lifecycle report '${label}' rejected by index`, {
            error: result.error,
          });
        }
      })
      .catch((error) => {
        logger.warn(`conversation lifecycle report '${label}' failed`, { error });
      });
  }

  return {
    sessionStarted(input) {
      deliver('session-started', options.client.reports.sessionStarted(input));
    },
    providerSessionId(input) {
      deliver('provider-session-id', options.client.reports.providerSessionId(input));
    },
    activity(conversationId) {
      const now = clock.now();
      const last = lastActivityReportAt.get(conversationId);
      if (last !== undefined && now - last < debounceMs) return;
      lastActivityReportAt.set(conversationId, now);
      deliver('session-activity', options.client.reports.sessionActivity({ conversationId }));
    },
    sessionEnded(conversationId) {
      lastActivityReportAt.delete(conversationId);
      deliver('session-ended', options.client.reports.sessionEnded({ conversationId }));
    },
  };
}

/** A reporter that reports nowhere — the default in tests and detached harnesses. */
export const noopConversationLifecycleReporter: ConversationLifecycleReporter = {
  sessionStarted: () => {},
  providerSessionId: () => {},
  activity: () => {},
  sessionEnded: () => {},
};
