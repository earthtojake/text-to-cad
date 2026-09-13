import type { Logger } from '@emdash/shared/logger';
import type { Clock } from '@emdash/shared/scheduling';
import type { LiveLogSourceOptions } from '@emdash/wire/live';
import type { TuiAgentStartInput } from '#runtimes/tui-agents/api';
import type { AgentPluginHost } from '#services/agent-plugins/api/plugins';
import type { ConversationLifecycleReporter } from '#services/conversation-reports/node';
import type { IExecutionContext } from '#services/exec/api';
import type { PtySpawner } from '#services/pty/api';
import type { SessionIntentStore } from '#services/session-intents/api';
import type { IdlePolicyConfig } from '#services/session-lifecycle/api';

export interface TuiAgentsRuntimeDeps {
  agentHost: AgentPluginHost;
  exec: IExecutionContext;
  spawner: PtySpawner;
  intents: SessionIntentStore;
  /** Lifecycle reports into the conversation index (spec §3.3); defaults to a no-op. */
  conversationReports?: ConversationLifecycleReporter;
  log?: LiveLogSourceOptions;
  clock?: Clock;
  lifecycle?: {
    session?: IdlePolicyConfig;
    sweepIntervalMs?: number;
  };
  logger: Logger;
}

export type TuiStartIntent = 'fresh' | 'resume' | 'stopped';

export type TuiSessionConfig = {
  input: TuiAgentStartInput;
  intent: TuiStartIntent;
  /** A resume was requested but could not be honored; this fresh spawn replaces it. */
  resumeFallback?: boolean;
};
