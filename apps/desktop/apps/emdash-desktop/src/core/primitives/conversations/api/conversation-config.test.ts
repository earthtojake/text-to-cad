import { describe, expect, it } from 'vitest';
import { conversationConfig } from './conversation-config';

describe('conversation-config v1 schema', () => {
  it('parses a v1 pty config', () => {
    const result = conversationConfig.safeParse({
      version: '1',
      type: 'pty',
      autoApprove: true,
      model: 'claude-sonnet-5',
    });
    expect(result.status).toBe('ok');
    if (result.status === 'ok') {
      expect(result.data).toEqual({
        version: '1',
        type: 'pty',
        autoApprove: true,
        model: 'claude-sonnet-5',
      });
    }
  });

  it('parses a v1 acp config', () => {
    const result = conversationConfig.safeParse({
      version: '1',
      type: 'acp',
      model: 'claude-opus-4-8',
    });
    expect(result.status).toBe('ok');
    if (result.status === 'ok') {
      expect(result.data).toEqual({ version: '1', type: 'acp', model: 'claude-opus-4-8' });
    }
  });

  it('upgrades a v0 legacy row (no version field) to v1 pty', () => {
    const result = conversationConfig.safeParse({
      autoApprove: true,
      model: 'claude-sonnet-5',
    });
    expect(result.status).toBe('ok');
    if (result.status === 'ok') {
      expect(result.data).toEqual({
        version: '1',
        type: 'pty',
        autoApprove: true,
        model: 'claude-sonnet-5',
      });
    }
  });

  it('drops providerSessionId when upgrading v0 -> v1', () => {
    const result = conversationConfig.safeParse({
      autoApprove: false,
      providerSessionId: '31477a03-961a-4451-82d4-efded56947fc',
      model: 'claude',
    });
    expect(result.status).toBe('ok');
    if (result.status === 'ok') {
      expect((result.data as Record<string, unknown>).providerSessionId).toBeUndefined();
      expect(result.data.type).toBe('pty');
    }
  });

  it('round-trips a v1 pty config through serialize and parseJson', () => {
    const config = conversationConfig.safeParse({ version: '1', type: 'pty', model: 'claude' });
    expect(config.status).toBe('ok');
    if (config.status === 'ok') {
      const json = conversationConfig.serialize(config.data);
      expect(conversationConfig.parseJson(json)).toEqual(config.data);
    }
  });

  it('round-trips a v1 acp config through serialize and parseJson', () => {
    const config = conversationConfig.safeParse({
      version: '1',
      type: 'acp',
      initialPrompt: 'hello',
    });
    expect(config.status).toBe('ok');
    if (config.status === 'ok') {
      const json = conversationConfig.serialize(config.data);
      expect(conversationConfig.parseJson(json)).toEqual(config.data);
    }
  });

  it('round-trips modeId on a v1 acp config', () => {
    const config = conversationConfig.safeParse({
      version: '1',
      type: 'acp',
      modeId: 'agent-full-access',
    });
    expect(config.status).toBe('ok');
    if (config.status === 'ok') {
      expect(config.data.type === 'acp' && config.data.modeId).toBe('agent-full-access');
      const json = conversationConfig.serialize(config.data);
      expect(conversationConfig.parseJson(json)).toEqual(config.data);
    }
  });

  it('returns invalid for non-object input', () => {
    expect(conversationConfig.safeParse('not-json')).toMatchObject({ status: 'invalid' });
    expect(conversationConfig.safeParse(null)).toMatchObject({ status: 'invalid' });
  });

  it('parseJson returns null for invalid JSON', () => {
    expect(conversationConfig.parseJson('not-json')).toBeNull();
  });

  it('parseJson returns null for null input', () => {
    expect(conversationConfig.parseJson(null)).toBeNull();
  });

  it('parses and round-trips model field on v0 input (upgraded to v1)', () => {
    const result = conversationConfig.safeParse({ model: 'claude-sonnet-5' });
    expect(result.status).toBe('ok');
    if (result.status === 'ok') {
      expect(result.data.model).toBe('claude-sonnet-5');
    }
  });
});
