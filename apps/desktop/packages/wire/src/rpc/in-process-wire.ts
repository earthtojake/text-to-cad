import type { ContractClient } from '../api/client';
import { connect, type Connection } from '../api/connect';
import { isController, type Controller } from '../api/controller';
import type { Contract, ContractDefinitions } from '../api/define';
import { serve } from '../api/serve';
import { memoryTransportPair, type MemoryTransportPair } from '../api/transports';
import type { ValidatePolicy } from '../api/validation';
import { client } from './client';
import { createController, type ContractImpl } from './controller';

export type InProcessWire<Defs extends ContractDefinitions> = {
  client: ContractClient<Defs>;
  connection: Connection;
  controller: Controller;
  pair: MemoryTransportPair;
  dispose(): Promise<void>;
};

export type CreateInProcessWireOptions = {
  /**
   * Validation policy used when a contract implementation is supplied. Ignored
   * when a pre-built controller is passed: controllers carry their validation
   * from `createController`.
   */
  validate?: ValidatePolicy;
};

/**
 * Assembles the canonical in-process wire stack: memory transport pair →
 * controller (validated via `createController`) → serve → connect → client.
 * Underlies both component instances and `createTestWire`.
 */
export function createInProcessWire<Defs extends ContractDefinitions>(
  contract: Contract<Defs>,
  implOrController: ContractImpl<Defs> | Controller,
  options: CreateInProcessWireOptions = {}
): InProcessWire<Defs> {
  const pair = memoryTransportPair();
  const controller = isController(implOrController)
    ? implOrController
    : createController(contract, implOrController, { validate: options.validate });
  const stopServing = serve(pair.right, controller);
  const connection = connect(pair.left);

  return {
    client: client(contract, connection),
    connection,
    controller,
    pair,
    async dispose() {
      stopServing();
      pair.disconnect();
      await controller.dispose?.();
    },
  };
}
