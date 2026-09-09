import { describe, expect, it } from 'vitest';
import {
  defaultEmdashConfig,
  EMDASH_CONFIG_FILE,
  isEmdashConfigPath,
  parseEmdashConfig,
} from './emdash-config';

describe('isEmdashConfigPath', () => {
  it('matches root config paths across path styles', () => {
    expect(isEmdashConfigPath(`/repo/${EMDASH_CONFIG_FILE}`)).toBe(true);
    expect(isEmdashConfigPath(EMDASH_CONFIG_FILE)).toBe(true);
    expect(isEmdashConfigPath('C:\\repo\\.emdash.json')).toBe(true);
  });

  it('does not match unrelated files', () => {
    expect(isEmdashConfigPath('/repo/src/index.ts')).toBe(false);
    expect(isEmdashConfigPath('/repo/.emdash.json.bak')).toBe(false);
  });
});

describe('parseEmdashConfig', () => {
  it('filters the config file from preserve patterns', () => {
    expect(
      parseEmdashConfig(JSON.stringify({ preservePatterns: ['.env', EMDASH_CONFIG_FILE] }))
    ).toEqual({
      success: true,
      data: { preservePatterns: ['.env'] },
    });
  });

  it('silently ignores stale keys from retired features (excludePatterns)', () => {
    expect(
      parseEmdashConfig(JSON.stringify({ excludePatterns: ['**'], preservePatterns: ['.env'] }))
    ).toEqual({
      success: true,
      data: { preservePatterns: ['.env'] },
    });
  });

  it('has no built-in preserve defaults', () => {
    expect(defaultEmdashConfig()).toEqual({});
    expect(parseEmdashConfig('{}')).toEqual({ success: true, data: {} });
  });

  it('returns defaults and the parse error for invalid content', () => {
    const result = parseEmdashConfig('{');
    expect(result.success).toBe(false);
    expect(result.data).toEqual(defaultEmdashConfig());
    if (!result.success) {
      expect(result.error).toBeInstanceOf(Error);
    }
  });
});
