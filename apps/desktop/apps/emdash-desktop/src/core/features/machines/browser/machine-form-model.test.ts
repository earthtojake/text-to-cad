import { describe, expect, it } from 'vitest';
import { suggestedAuthTypeForSshConfigHost } from './machine-form-model';

describe('suggestedAuthTypeForSshConfigHost', () => {
  it('uses key auth when an SSH config alias declares an identity file', () => {
    expect(
      suggestedAuthTypeForSshConfigHost({
        host: 'corp-dev',
        identityFile: '~/.ssh/id_rsa',
      })
    ).toBe('key');
  });

  it('uses agent auth when an SSH config alias declares an identity agent', () => {
    expect(
      suggestedAuthTypeForSshConfigHost({
        host: 'corp-dev',
        identityFile: '~/.ssh/id_rsa',
        identityAgent: '/tmp/agent.sock',
      })
    ).toBe('agent');
  });

  it('defaults to agent auth when no auth hint is present', () => {
    expect(
      suggestedAuthTypeForSshConfigHost({
        host: 'corp-dev',
      })
    ).toBe('agent');
  });
});
