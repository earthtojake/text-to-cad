import { asAgentProviderId, type AgentProviderId } from '@emdash/plugins/agents/types';
import { z } from 'zod';
import { defineSettingsContribution } from '@core/primitives/settings/api';

export const DEFAULT_AGENT_ID = asAgentProviderId('claude');

const defaultAgentSchema = z
  .string()
  .trim()
  .min(1)
  .transform(asAgentProviderId)
  .optional()
  .default(DEFAULT_AGENT_ID);

export const defaultAgentSettingsContribution = defineSettingsContribution<
  'defaultAgent',
  AgentProviderId
>({
  key: 'defaultAgent',
  schema: defaultAgentSchema,
  defaults: DEFAULT_AGENT_ID,
});
