import { describe, expect, it, vi } from 'vitest';
import { ConfirmRegistry } from './confirm-registry';

describe('ConfirmRegistry', () => {
  it('uses the most recently registered action and removes entries from any position', () => {
    const registry = new ConfirmRegistry();
    const first = { trigger: vi.fn(), isEnabled: () => true };
    const second = { trigger: vi.fn(), isEnabled: () => true };
    const removeFirst = registry.register(first);
    const removeSecond = registry.register(second);

    expect(registry.current).toBe(second);
    removeFirst();
    expect(registry.current).toBe(second);
    removeSecond();
    expect(registry.current).toBeUndefined();
  });
});
