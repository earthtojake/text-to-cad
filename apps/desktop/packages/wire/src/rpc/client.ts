import { buildClient, type ClientOptions, type ContractClient } from '../api/client';
import type { Connection } from '../api/connect';
import type { Contract, ContractDefinitions } from '../api/define';
import { liveEndpointKinds } from '../live/endpoint-kinds';

export function client<Defs extends ContractDefinitions>(
  contract: Contract<Defs>,
  connection: Connection,
  options: ClientOptions = {}
): ContractClient<Defs> {
  return buildClient(contract, connection, { ...options, liveEndpoints: liveEndpointKinds });
}
