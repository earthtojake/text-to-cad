import { describe, expect, it } from 'vitest';
import { desktopWireContract } from '../shared/desktop-wire-contract';
import { desktopDomainContracts } from '../shared/domain-contracts';
import { desktopNodeControllers } from './controllers';

describe('desktop node controller manifest', () => {
  it('provides exactly one controller for every desktop wire domain', () => {
    expect(Object.keys(desktopNodeControllers).sort()).toEqual(
      Object.keys(desktopDomainContracts).sort()
    );
    expect(Object.keys(desktopWireContract).sort()).toEqual(
      Object.keys(desktopDomainContracts).sort()
    );
  });
});
