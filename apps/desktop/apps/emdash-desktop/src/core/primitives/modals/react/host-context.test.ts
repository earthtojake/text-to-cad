import { describe, expect, it, vi } from 'vitest';
import { assertModalHost, type ModalHostController } from './host-context';

const controller: ModalHostController = {
  complete: vi.fn(),
  dismiss: vi.fn(),
  setCloseGuard: vi.fn(),
  hasActiveCloseGuard: false,
};

describe('assertModalHost', () => {
  it('returns the controller for the active modal', () => {
    expect(assertModalHost({ id: 'exampleModal', controller }, 'exampleModal')).toBe(controller);
  });

  it('rejects usage outside a modal host', () => {
    expect(() => assertModalHost(undefined, 'exampleModal')).toThrow(
      'useModalController must be used inside a modal host'
    );
  });

  it('rejects a controller requested for a different modal', () => {
    expect(() => assertModalHost({ id: 'otherModal', controller }, 'exampleModal')).toThrow(
      "Active modal is 'otherModal', not 'exampleModal'"
    );
  });
});
