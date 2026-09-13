import {
  createController,
  type Contract,
  type ContractImpl,
  type Controller,
} from '@emdash/wire/rpc';
import { loggingWireContract } from '@core/primitives/logging/api/wire-contract';

type ContractDefinitionsOf<TContract> =
  TContract extends Contract<infer Definitions> ? Definitions : never;
export type LoggingControllerOperations = ContractImpl<
  ContractDefinitionsOf<typeof loggingWireContract>
>;

export function createLoggingWireController(operations: LoggingControllerOperations): Controller {
  return createController(loggingWireContract, operations);
}
