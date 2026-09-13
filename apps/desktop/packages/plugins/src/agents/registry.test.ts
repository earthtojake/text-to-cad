import { describe, expect, it } from 'vitest';
import { pluginRegistry } from './registry';

const GLOBAL_HOOK_PROVIDERS = [
  'amp',
  'auggie',
  'claude',
  'codex',
  'commandcode',
  'copilot',
  'devin',
  'droid',
  'goose',
  'grok',
  'kilocode',
  'kimi',
  'kiro',
  'mimocode',
  'mistral',
  'oh-my-pi',
  'opencode',
  'pi',
  'qoder',
  'qwen',
].sort();

describe('agent plugin registry', () => {
  it('keeps every shipped hook integration user-global', () => {
    const hookProviders = pluginRegistry
      .getAll()
      .filter((provider) => provider.capabilities.hooks.kind !== 'none');

    expect(hookProviders.map((provider) => provider.metadata.id).sort()).toEqual(
      GLOBAL_HOOK_PROVIDERS
    );
    for (const provider of hookProviders) {
      expect(provider.capabilities.hooks).toMatchObject({ scope: 'global' });
    }
  });
});
