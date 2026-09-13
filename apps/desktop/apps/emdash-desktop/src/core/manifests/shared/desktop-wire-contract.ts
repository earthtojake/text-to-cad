import { defineContract } from '@emdash/wire/rpc';
import { desktopDomainContracts } from './domain-contracts';

export const desktopWireContract = defineContract(desktopDomainContracts);

export type DesktopWireContract = typeof desktopWireContract;
