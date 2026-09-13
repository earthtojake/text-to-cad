export type AutomationRunStatus =
  | 'scheduled'
  | 'queued'
  | 'provisioning_workspace'
  | 'starting_session'
  | 'done'
  | 'failed'
  | 'skipped'
  | 'cancelled';

export type AutomationRunTriggerKind = 'cron' | 'manual';
