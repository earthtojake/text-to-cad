import type { Scope } from '@emdash/shared/concurrency';
import type { Controller } from '@emdash/wire/rpc';
import {
  desktopNodeControllers,
  type DesktopControllerContext,
} from '@core/manifests/node/controllers';
import { desktopDomainContracts } from '@core/manifests/shared/domain-contracts';
import type { DesktopRuntimes } from '@main/gateway/desktop-runtimes';
import { appScope } from '../../core/app-scope';
import { createDesktopWireOptions } from '../wiring';
import type { DatabaseBundle } from './database';
import type { InfrastructureBundle } from './infrastructure';
import type { ServicesBundle } from './services';

export type ControllersBundle = {
  readonly controllers: Record<string, Controller>;
  readonly scope: Scope;
};

export async function bootControllers(
  database: DatabaseBundle,
  infrastructure: InfrastructureBundle,
  runtimes: DesktopRuntimes,
  services: ServicesBundle
): Promise<ControllersBundle> {
  if (import.meta.env.DEV) assertDomainKeyParity();
  const options = createDesktopWireOptions(database, services, runtimes);
  const scope = appScope.child('desktop-controllers');
  try {
    const entries = await Promise.all(
      Object.entries(desktopNodeControllers).map(async ([domain, contribution]) => {
        const controllerScope = scope.child(`controller:${domain}`);
        const context: DesktopControllerContext = {
          ...options,
          hosts: infrastructure.hosts,
          runtimes: runtimes.broker,
          scope: controllerScope,
          ssh: infrastructure.ssh,
        };
        const controller = await contribution.create(context);
        if (controller.dispose) controllerScope.add(() => controller.dispose?.());
        return [domain, controller] as const;
      })
    );
    return { controllers: Object.fromEntries(entries), scope };
  } catch (error) {
    await scope.dispose(error);
    throw error;
  }
}

function assertDomainKeyParity(): void {
  const contractDomains = Object.keys(desktopDomainContracts).sort();
  const controllerDomains = Object.keys(desktopNodeControllers).sort();
  if (
    contractDomains.length === controllerDomains.length &&
    contractDomains.every((domain, index) => domain === controllerDomains[index])
  ) {
    return;
  }

  const contractSet = new Set(contractDomains);
  const controllerSet = new Set(controllerDomains);
  const missingControllers = contractDomains.filter((domain) => !controllerSet.has(domain));
  const unknownControllers = controllerDomains.filter((domain) => !contractSet.has(domain));
  throw new Error(
    `Desktop Wire domain mismatch: missing controllers [${missingControllers.join(
      ', '
    )}], unknown controllers [${unknownControllers.join(', ')}]`
  );
}
