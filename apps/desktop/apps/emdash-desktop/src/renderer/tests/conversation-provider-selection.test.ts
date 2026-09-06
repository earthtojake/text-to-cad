import { asAgentProviderId } from '@emdash/plugins/agents/types';
import { describe, expect, it } from 'vitest';
import { resolveConversationProviderSelection } from '@core/features/conversations/browser/provider-selection';

const agent = asAgentProviderId;
const orderedProviderIds = [agent('codex'), agent('claude'), agent('qwen')];

describe('resolveConversationProviderSelection', () => {
  it('keeps default provider while availability is unknown', () => {
    const selection = resolveConversationProviderSelection({
      orderedProviderIds,
      defaultProviderId: agent('claude'),
      providerOverride: null,
      installedProviderIds: [],
      availabilityKnown: false,
    });

    expect(selection.providerId).toBe('claude');
    expect(selection.createDisabled).toBe(false);
  });

  it('falls back to the first installed provider when default is unavailable', () => {
    const selection = resolveConversationProviderSelection({
      orderedProviderIds,
      defaultProviderId: agent('claude'),
      providerOverride: null,
      installedProviderIds: [agent('codex'), agent('qwen')],
      availabilityKnown: true,
    });

    expect(selection.providerId).toBe('codex');
    expect(selection.createDisabled).toBe(false);
  });

  it('disables creation when no agents are installed', () => {
    const selection = resolveConversationProviderSelection({
      orderedProviderIds,
      defaultProviderId: agent('claude'),
      providerOverride: null,
      installedProviderIds: [],
      availabilityKnown: true,
    });

    expect(selection.providerId).toBeNull();
    expect(selection.createDisabled).toBe(true);
  });

  it('honors an explicit provider override', () => {
    const selection = resolveConversationProviderSelection({
      orderedProviderIds,
      defaultProviderId: agent('claude'),
      providerOverride: agent('codex'),
      installedProviderIds: [agent('codex')],
      availabilityKnown: true,
    });

    expect(selection.providerId).toBe('codex');
    expect(selection.createDisabled).toBe(false);
  });
});
