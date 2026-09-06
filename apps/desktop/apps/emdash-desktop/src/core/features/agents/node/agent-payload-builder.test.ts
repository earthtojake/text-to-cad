import type { HostDependencyView } from '@emdash/core/services/host-dependencies/node';
import { describe, expect, it } from 'vitest';
import { buildAgentMetadataList, toAgentInstallationStatus } from './agent-payload-builder';

describe('toAgentInstallationStatus', () => {
  it('maps host install options into the renderer status payload', () => {
    const view: HostDependencyView = {
      hostId: 'host-1',
      definition: {
        id: 'fake-agent',
        name: 'Fake Agent',
        category: 'agent',
        binaryNames: ['fake-agent'],
        status: 'active',
      },
      installOptions: [
        {
          method: 'curl',
          command: 'curl -fsSL https://example.test/install.sh | bash',
          recommended: true,
          elevation: 'never',
        },
      ],
      selection: null,
      candidates: [],
      resolved: null,
      status: 'missing',
      checkedAt: 1,
    };

    expect(toAgentInstallationStatus('fake-agent', 'ssh-1', view).installOptions).toEqual(
      view.installOptions
    );
  });
});

describe('buildAgentMetadataList', () => {
  it('copies provider trust capabilities into renderer metadata', () => {
    const claude = buildAgentMetadataList().find((agent) => agent.id === 'claude');

    expect(claude?.capabilities.trust).toEqual({ kind: 'supported' });
  });
});
