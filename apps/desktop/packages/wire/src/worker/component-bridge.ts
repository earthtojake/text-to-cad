import type { Scope } from '@emdash/shared/concurrency';
import type { ContractClient } from '../api/client';
import { isController, type Controller } from '../api/controller';
import type { Contract, ContractDefinitions } from '../api/define';
import { serve } from '../api/serve';
import { forwardController } from '../rpc/forward';
import {
  isWireComponentBootstrapRequest,
  workerProcessChannelTransport,
  type WireComponentBootstrapResponse,
} from './component-protocol';
import { assertExactRequirementKeys } from './component/requirements';
import type {
  ProvidedWireComponentRequirements,
  WireComponentDefinition,
  WireComponentRequirements,
} from './component/types';
import type { WorkerProcess } from './types';

export function setupComponentWorkerGeneration<
  Id extends string,
  Defs extends ContractDefinitions,
  Requirements extends WireComponentRequirements,
  Config,
>({
  component,
  dependencies,
  config,
  process,
  scope,
}: {
  component: WireComponentDefinition<Id, Defs, Requirements, Config>;
  dependencies: ProvidedWireComponentRequirements<Requirements>;
  config: unknown;
  process: WorkerProcess;
  scope: Scope;
}): void {
  assertExactRequirementKeys(
    component.id,
    component.requirements,
    dependencies as Record<string, unknown>
  );

  let response: WireComponentBootstrapResponse | undefined;

  scope.add(
    process.onMessage((message) => {
      if (!isWireComponentBootstrapRequest(message) || message.componentId !== component.id) return;
      response ??= createBootstrapResponse({ component, dependencies, config, process, scope });
      process.send(response);
    })
  );
}

function createBootstrapResponse<
  Id extends string,
  Defs extends ContractDefinitions,
  Requirements extends WireComponentRequirements,
  Config,
>({
  component,
  dependencies,
  config,
  process,
  scope,
}: {
  component: WireComponentDefinition<Id, Defs, Requirements, Config>;
  dependencies: ProvidedWireComponentRequirements<Requirements>;
  config: unknown;
  process: WorkerProcess;
  scope: Scope;
}): WireComponentBootstrapResponse {
  const response: WireComponentBootstrapResponse = {
    kind: 'wire-component-bootstrap',
    event: 'ready',
    componentId: component.id,
    config,
    dependencies: {},
  };

  for (const [key, requirement] of Object.entries(component.requirements)) {
    const supplied = (dependencies as Record<string, unknown>)[key];
    const channel = `dep:${key}`;
    const controller = asController(requirement.contract, supplied);
    const stop = serve(workerProcessChannelTransport(process, channel), controller);
    scope.add(stop);
    response.dependencies[key] = { kind: 'contract', channel };
  }

  return response;
}

function asController<Defs extends ContractDefinitions>(
  contract: Contract<Defs>,
  supplied: unknown
): Controller {
  if (isController(supplied)) return supplied;
  return forwardController(contract, supplied as ContractClient<Defs>);
}
