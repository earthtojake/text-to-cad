import type { Scope } from '@emdash/shared/concurrency';
import type { Controller } from '../../api/controller';
import type { Contract, ContractDefinitions } from '../../api/define';
import { createInProcessWire } from '../../rpc/in-process-wire';
import { componentControllerSymbol, type InternalWireComponentInstance } from './internal';

export type CreateWireComponentInstanceOptions<Defs extends ContractDefinitions> = {
  scope: Scope;
  contract: Contract<Defs>;
  controller: Controller;
};

export function createWireComponentInstance<Defs extends ContractDefinitions>({
  scope,
  contract,
  controller,
}: CreateWireComponentInstanceOptions<Defs>): InternalWireComponentInstance<Defs> {
  const wire = createInProcessWire(contract, controller);
  scope.add(async () => {
    await wire.dispose();
  });

  return {
    client: wire.client,
    async dispose() {
      await scope.dispose();
    },
    [componentControllerSymbol]: wire.controller,
  };
}
