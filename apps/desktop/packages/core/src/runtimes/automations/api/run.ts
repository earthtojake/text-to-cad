// Retained only for the retired automation database schema.
export const automationRunStatuses = [
  'scheduled',
  'queued',
  'provisioning_workspace',
  'starting_session',
  'done',
  'failed',
  'skipped',
  'cancelled',
] as const;
