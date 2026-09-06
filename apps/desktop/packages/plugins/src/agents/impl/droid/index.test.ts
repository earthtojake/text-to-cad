import { describe, expect, it } from 'vitest';
import { provider } from './index';

const baseContext = {
  cli: 'droid',
  autoApprove: false,
  initialPrompt: undefined,
  sessionId: 'emdash-session-id',
  providerSessionId: undefined,
  isResuming: false,
  model: '',
};

describe('droid provider', () => {
  it('advertises auto-approve support', () => {
    expect(provider.capabilities.autoApprove).toEqual({ kind: 'supported' });
  });

  it('passes --auto high when auto-approve is enabled', () => {
    const command = provider.behavior.prompt!.buildCommand({
      ...baseContext,
      autoApprove: true,
      initialPrompt: 'Fix the bug',
    });

    expect(command).toEqual({
      command: 'droid',
      args: ['--auto', 'high', 'Fix the bug'],
      env: {},
    });
  });

  it('omits the autonomy flag when auto-approve is disabled', () => {
    const command = provider.behavior.prompt!.buildCommand({
      ...baseContext,
      initialPrompt: 'Fix the bug',
    });

    expect(command.args).not.toContain('--auto');
    expect(command.args).toEqual(['Fix the bug']);
  });

  it('resumes a stored provider session id with --resume', () => {
    const command = provider.behavior.prompt!.buildCommand({
      ...baseContext,
      providerSessionId: '31477a03-961a-4451-82d4-efded56947fc',
      isResuming: true,
    });

    expect(command.args).toEqual(['--resume', '31477a03-961a-4451-82d4-efded56947fc']);
  });

  it('passes --auto high on resume when auto-approve is enabled', () => {
    const command = provider.behavior.prompt!.buildCommand({
      ...baseContext,
      autoApprove: true,
      providerSessionId: '31477a03-961a-4451-82d4-efded56947fc',
      isResuming: true,
    });

    expect(command.args).toEqual([
      '--resume',
      '31477a03-961a-4451-82d4-efded56947fc',
      '--auto',
      'high',
    ]);
  });
});
