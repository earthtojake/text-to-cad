import {
  defineContract,
  fallible,
  liveLog,
  liveModel,
  liveState,
  procedure,
} from '@emdash/wire/rpc';
import { z } from 'zod';
import { agentAuthStatusSchema } from '#services/agent-plugins/api/plugins/capabilities/auth';
import {
  agentConfigAuthErrorSchema,
  agentConfigListSchema,
  agentConfigMcpErrorSchema,
  agentConfigSkillsErrorSchema,
  createSkillInputSchema,
  installedSkillsSchema,
  hooksStatusSchema,
  markUrlHandledCommandSchema,
  mcpServerListSchema,
  mcpServerSchema,
  providerCommandSchema,
  resizeLoginCommandSchema,
  sendLoginInputCommandSchema,
  skillInstallPayloadSchema,
  startLoginCommandSchema,
} from './schemas';

export const agentConfigContract = defineContract({
  agents: liveModel({
    key: z.void().optional(),
    states: {
      list: liveState({ data: agentConfigListSchema }),
    },
  }),
  hooksStatus: procedure({
    input: providerCommandSchema,
    output: hooksStatusSchema,
  }),

  startLogin: fallible({
    input: startLoginCommandSchema,
    data: z.void(),
    error: agentConfigAuthErrorSchema,
  }),
  cancelLogin: fallible({
    input: providerCommandSchema,
    data: z.void(),
    error: agentConfigAuthErrorSchema,
  }),
  sendLoginInput: fallible({
    input: sendLoginInputCommandSchema,
    data: z.void(),
    error: agentConfigAuthErrorSchema,
  }),
  resizeLogin: fallible({
    input: resizeLoginCommandSchema,
    data: z.void(),
    error: agentConfigAuthErrorSchema,
  }),
  markUrlHandled: fallible({
    input: markUrlHandledCommandSchema,
    data: z.void(),
    error: agentConfigAuthErrorSchema,
  }),
  refreshAuthStatus: fallible({
    input: providerCommandSchema,
    data: agentAuthStatusSchema,
    error: agentConfigAuthErrorSchema,
  }),
  loginOutput: liveLog({ key: providerCommandSchema }),

  mcpServers: liveModel({
    key: z.void().optional(),
    states: {
      list: liveState({ data: mcpServerListSchema }),
    },
  }),
  saveMcpServer: fallible({
    input: z.object({ server: mcpServerSchema }),
    data: z.void(),
    error: agentConfigMcpErrorSchema,
  }),
  removeMcpServer: fallible({
    input: z.object({ name: z.string() }),
    data: z.void(),
    error: agentConfigMcpErrorSchema,
  }),
  removeMcpForAgent: fallible({
    input: providerCommandSchema.extend({ name: z.string() }),
    data: z.void(),
    error: agentConfigMcpErrorSchema,
  }),
  listMcpForAgent: fallible({
    input: providerCommandSchema,
    data: z.object({ servers: mcpServerListSchema }),
    error: agentConfigMcpErrorSchema,
  }),

  skills: liveModel({
    key: z.void().optional(),
    states: {
      list: liveState({ data: installedSkillsSchema }),
    },
  }),
  installSkill: fallible({
    input: z.object({ skill: skillInstallPayloadSchema }),
    data: z.object({ skills: installedSkillsSchema }),
    error: agentConfigSkillsErrorSchema,
  }),
  removeSkill: fallible({
    input: z.object({ name: z.string() }),
    data: z.object({ skills: installedSkillsSchema }),
    error: agentConfigSkillsErrorSchema,
  }),
  createSkill: fallible({
    input: createSkillInputSchema,
    data: z.object({ skills: installedSkillsSchema }),
    error: agentConfigSkillsErrorSchema,
  }),
});

export type AgentConfigContract = typeof agentConfigContract;
