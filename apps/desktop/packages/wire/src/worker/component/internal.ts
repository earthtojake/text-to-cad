import type { Controller } from '../../api/controller';
import type { ContractDefinitions } from '../../api/define';
import type { WireComponentInstance } from './types';

export const componentControllerSymbol: unique symbol = Symbol('wire.component.controller');

export type InternalWireComponentInstance<Defs extends ContractDefinitions> =
  WireComponentInstance<Defs> & {
    readonly [componentControllerSymbol]: Controller;
  };
