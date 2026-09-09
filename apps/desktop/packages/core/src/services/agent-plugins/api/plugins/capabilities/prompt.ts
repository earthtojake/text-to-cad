import { definePluginCapability } from '@emdash/shared/plugins';
import z from 'zod';

export type CommandContext = {
  cli: string; // absolute path to the cli binary
  extraArgs?: string[]; // user-configured in settings
  autoApprove: boolean;
  initialPrompt?: string;
  /** Emdash conversation UUID — used as the session token for providers that track their
   * own session across the emdash lifetime (e.g. claude --session-id, opencode --session). */
  sessionId?: string;
  /** Provider-native session identifier stored by the agent classifier. When present, used
   * for resume on providers that generate their own session IDs (e.g. grok, copilot, kimi,
   * codex, droid). Undefined means the provider has not yet emitted a session ID. */
  providerSessionId?: string;
  isResuming?: boolean;
  model: string;
};

export type AgentCommand = {
  command: string;
  args: string[];
  env: Record<string, string>;
};

type Prompt = {
  buildCommand(ctx: CommandContext): AgentCommand;
};

/**
 * PromptDeliveryOption is used to describe a prompt delivery that an agent supports.
 * @param kind - The kind of prompt delivery option.
 */
export const promptCapability = definePluginCapability<Prompt>()(
  'prompt-delivery',
  z.discriminatedUnion('kind', [
    z.object({
      kind: z.literal('argv'),
      flag: z.string().optional(),
    }),
    z.object({
      kind: z.literal('pty-only'),
    }),
    z.object({
      kind: z.literal('stdin-pipe'),
    }),
    z.object({
      kind: z.literal('none'),
    }),
  ]),
  undefined,
  {
    requiresBehavior: (descriptor) => descriptor.kind !== 'none',
  }
);
