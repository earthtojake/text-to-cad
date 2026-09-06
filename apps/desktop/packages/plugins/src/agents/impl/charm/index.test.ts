import { describe, expect, it } from 'vitest';
import { provider } from './index';

const baseContext = {
  cli: 'crush',
  autoApprove: false,
  initialPrompt: undefined,
  sessionId: 'emdash-session-id',
  providerSessionId: undefined,
  isResuming: false,
  model: '',
};

describe('charm provider', () => {
  it('does not advertise auto-approve because Crush rejects --yolo with run', () => {
    expect(provider.capabilities.autoApprove).toEqual({ kind: 'none' });
  });

  it('supports Crush MCP configuration', () => {
    expect(provider.capabilities.mcp).toEqual({
      kind: 'supported',
      scope: 'global',
      supportedTransports: ['stdio', 'http'],
    });
    expect(provider.behavior.mcp).toBeDefined();
  });

  it('runs a fresh prompt through crush run with the prompt as a positional arg', () => {
    const command = provider.behavior.prompt!.buildCommand({
      ...baseContext,
      autoApprove: true,
      initialPrompt: 'implement the task',
    });

    expect(command).toEqual({
      command: 'crush',
      args: ['run', 'implement the task'],
      env: {},
    });
  });

  it('starts an empty fresh session in interactive mode', () => {
    const command = provider.behavior.prompt!.buildCommand(baseContext);

    expect(command).toEqual({
      command: 'crush',
      args: [],
      env: {},
    });
  });

  it('does not pass Emdash ids as Crush session ids', () => {
    const command = provider.behavior.prompt!.buildCommand({
      ...baseContext,
      isResuming: true,
    });

    expect(command).toEqual({
      command: 'crush',
      args: [],
      env: {},
    });
  });
});
