import type { CommandContext } from '@emdash/core/services/agent-plugins/api/plugins';
import { describe, expect, it } from 'vitest';
import { pluginRegistry } from '../registry';

const PROMPT_TOKEN = 'PROMPT_TOKEN_eng1546';

function freshCtx(overrides: Partial<CommandContext> = {}): CommandContext {
  return {
    cli: 'agent',
    autoApprove: true,
    initialPrompt: PROMPT_TOKEN,
    sessionId: 'conv-1',
    isResuming: false,
    model: '',
    ...overrides,
  };
}

function buildArgs(id: string, ctx: CommandContext): string[] {
  const plugin = pluginRegistry.get(id);
  if (!plugin) throw new Error(`missing plugin: ${id}`);
  return plugin.behavior.prompt!.buildCommand(ctx).args;
}

describe('prompt delivery (ENG-1546 regression)', () => {
  it('kilocode passes the prompt via --prompt, never as a bare positional path', () => {
    const plugin = pluginRegistry.get('kilocode')!;
    expect(plugin.capabilities.prompt).toMatchObject({ kind: 'argv', flag: '--prompt' });

    const args = buildArgs('kilocode', freshCtx());
    const flagIndex = args.indexOf('--prompt');
    expect(flagIndex).toBeGreaterThanOrEqual(0);
    expect(args[flagIndex + 1]).toBe(PROMPT_TOKEN);
    // The prompt must appear exactly once, and only as the value of --prompt.
    expect(args.filter((a) => a === PROMPT_TOKEN)).toHaveLength(1);
  });

  it('does not pass the prompt positionally on resume for kilocode', () => {
    const args = buildArgs('kilocode', freshCtx({ initialPrompt: undefined, isResuming: true }));
    expect(args).toContain('--continue');
    expect(args).not.toContain('--prompt');
  });

  // PTY-only agents accept manual input in the TUI; prompts must never leak into
  // argv (their CLIs reject/parse a bare positional differently).
  it.each(['jules', 'freebuff'])('%s uses PTY-only delivery and no argv prompt', (id) => {
    const plugin = pluginRegistry.get(id)!;
    expect(plugin.capabilities.prompt.kind).toBe('pty-only');

    const args = buildArgs(id, freshCtx());
    expect(args).not.toContain(PROMPT_TOKEN);
  });
});
