import { describe, expect, it } from 'vitest';
import { translator } from '@text-to-cad/ui/i18n';
import { hostDisplayName } from './hostName';

describe('the host\'s display name', () => {
  it('maps what a host calls itself at ui/initialize to the name a person knows, however it is spelled', () => {
    expect(['codex', 'Codex', 'codex-mcp-client', 'OpenAI Codex'].map(hostDisplayName)).toEqual(['Codex', 'Codex', 'Codex', 'Codex']);
    expect(['claude-desktop', 'Claude', 'claude-ai', 'claude-code'].map(hostDisplayName)).toEqual(['Claude', 'Claude', 'Claude', 'Claude']);
    expect(['cursor', 'gemini-cli', 'grok-build', 'chatgpt', 'vscode', 'GitHub Copilot', 'windsurf', 'goose'].map(hostDisplayName))
      .toEqual(['Cursor', 'Gemini', 'Grok', 'ChatGPT', 'VS Code', 'VS Code', 'Windsurf', 'Goose']);
  });

  it('names no host it does not know, so the notice falls back to "this app"', () => {
    expect(['basic-host', 'ext-apps reference host', '', '   ', null, undefined].map(hostDisplayName)).toEqual([null, null, null, null, null, null]);
    const t = translator('en');
    const host = hostDisplayName('acme-agent') ?? t('cad.lost.thisApp');
    expect(t('cad.lost.tabs', { host })).toBe('The CAD plugin stopped responding in this thread. Quit and reopen this app to restart it.');
    expect(t('cad.lost.tabs', { host: hostDisplayName('codex-mcp-client') })).toBe('The CAD plugin stopped responding in this thread. Quit and reopen Codex to restart it.');
    expect(t('cad.lost.inline', { host: hostDisplayName('Claude') })).toBe('The CAD plugin stopped responding. Quit and reopen Claude to restart it, then ask your agent to show the model again.');
  });
});
