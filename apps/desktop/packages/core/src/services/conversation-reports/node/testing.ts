import type { ReportProviderSessionIdInput, ReportSessionStartedInput } from '../api/schemas';
import type { ConversationLifecycleReporter } from './reporter';

export type RecordingConversationLifecycleReporter = ConversationLifecycleReporter & {
  started: ReportSessionStartedInput[];
  providerIds: ReportProviderSessionIdInput[];
  activities: string[];
  ended: string[];
};

/** Records every lifecycle report for assertions in session-runtime tests. */
export function createRecordingConversationLifecycleReporter(): RecordingConversationLifecycleReporter {
  const started: ReportSessionStartedInput[] = [];
  const providerIds: ReportProviderSessionIdInput[] = [];
  const activities: string[] = [];
  const ended: string[] = [];
  return {
    started,
    providerIds,
    activities,
    ended,
    sessionStarted: (input) => {
      started.push(input);
    },
    providerSessionId: (input) => {
      providerIds.push(input);
    },
    activity: (conversationId) => {
      activities.push(conversationId);
    },
    sessionEnded: (conversationId) => {
      ended.push(conversationId);
    },
  };
}
