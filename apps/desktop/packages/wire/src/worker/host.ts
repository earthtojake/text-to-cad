import { systemClock } from '@emdash/shared/scheduling';
import type { ContractClient } from '../api/client';
import type { ContractDefinitions } from '../api/define';
import type { WireComponentDefinition, WireComponentRequirements } from './component';
import { setupComponentWorkerGeneration } from './component-bridge';
import type {
  WireWorker,
  WireComponentWorkerCreateOptions,
  WireWorkerDefinition,
  WireWorkerHost,
  WireWorkerHostOptions,
} from './types';
import { WORKER_NAME_ENV_VAR } from './types';
import { WorkerSlot } from './worker-slot';

export function createWireWorkerHost(options: WireWorkerHostOptions): WireWorkerHost {
  return new WireWorkerHostImpl(options);
}

class WireWorkerHostImpl implements WireWorkerHost {
  private readonly workers = new Map<string, WireWorker<ContractDefinitions>>();

  constructor(private readonly options: WireWorkerHostOptions) {}

  get scope() {
    return this.options.scope;
  }

  private defineSlot<Defs extends ContractDefinitions>(
    definition: WireWorkerDefinition<Defs>
  ): WireWorker<Defs> {
    if (this.workers.has(definition.name)) {
      throw new Error(`Wire worker '${definition.name}' is already defined`);
    }

    const scope = this.options.scope.child(`worker:${definition.name}`);
    const logger = (this.options.logger ?? scope.log).child({ worker: definition.name });
    const slot = new WorkerSlot({
      definition,
      scope,
      processSpawner: this.options.processSpawner,
      clock: this.options.clock ?? systemClock,
      logger,
      defaultSupervision: this.options.defaults?.supervision,
      defaultReadyTimeoutMs: this.options.defaults?.readyTimeoutMs,
      defaultShutdownGraceMs: this.options.defaults?.shutdownGraceMs,
    });

    this.workers.set(definition.name, slot as WireWorker<ContractDefinitions>);
    scope.add(() => {
      this.workers.delete(definition.name);
    });

    return slot;
  }

  create<
    Id extends string,
    Defs extends ContractDefinitions,
    Requirements extends WireComponentRequirements,
    Config,
  >(
    component: WireComponentDefinition<Id, Defs, Requirements, Config>,
    options: WireComponentWorkerCreateOptions<Requirements, Config>
  ): WireWorker<Defs> {
    const name = options.name ?? component.id;

    return this.defineSlot({
      name,
      contract: component.contract,
      process: () => ({
        entry: options.executable,
        args: options.args,
        env: {
          ...options.env,
          [WORKER_NAME_ENV_VAR]: name,
        },
        cwd: options.cwd,
      }),
      setup: ({ process, scope }) => {
        setupComponentWorkerGeneration({
          component,
          dependencies: options.dependencies,
          config: options.config,
          process,
          scope,
        });
      },
      supervision: options.supervision,
      readyTimeoutMs: options.readyTimeoutMs,
      shutdownGraceMs: options.shutdownGraceMs,
      instrumentation: options.instrumentation,
    });
  }

  async spawn<
    Id extends string,
    Defs extends ContractDefinitions,
    Requirements extends WireComponentRequirements,
    Config,
  >(
    component: WireComponentDefinition<Id, Defs, Requirements, Config>,
    options: WireComponentWorkerCreateOptions<Requirements, Config>
  ): Promise<ContractClient<Defs>> {
    const worker = this.create(component, options);
    return await worker.ready();
  }

  dispose(): Promise<void> {
    return this.options.scope.dispose(new Error('Wire worker host disposed'));
  }
}
