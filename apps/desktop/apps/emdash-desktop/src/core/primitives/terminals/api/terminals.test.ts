import { describe, expect, it } from 'vitest';
import { createLifecycleScriptTerminalId, lifecycleScriptNodeIdFromTerminalId } from './terminals';

describe('createLifecycleScriptTerminalId', () => {
  it('returns stable delimiter-safe lifecycle script terminal ids', () => {
    expect(createLifecycleScriptTerminalId('prepare')).toBe('script-lifecycle-prepare');
    expect(createLifecycleScriptTerminalId('setup')).toBe('script-lifecycle-setup');
    expect(createLifecycleScriptTerminalId('run')).toBe('script-lifecycle-run');
    expect(createLifecycleScriptTerminalId('teardown')).toBe('script-lifecycle-teardown');
  });
});

describe('lifecycleScriptNodeIdFromTerminalId', () => {
  it('extracts the runtime workflow node id from lifecycle script terminal ids', () => {
    expect(lifecycleScriptNodeIdFromTerminalId('script-lifecycle-setup')).toBe('setup');
    expect(lifecycleScriptNodeIdFromTerminalId('script-lifecycle-run')).toBe('run');
  });

  it('returns null for non-lifecycle terminal ids', () => {
    expect(lifecycleScriptNodeIdFromTerminalId('terminal-1')).toBeNull();
    expect(lifecycleScriptNodeIdFromTerminalId('script-lifecyclesetup')).toBeNull();
  });
});
