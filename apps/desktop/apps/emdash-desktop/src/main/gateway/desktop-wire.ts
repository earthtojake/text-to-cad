import type { PendingLease } from '@emdash/shared';
import { exposeWireToWindows, WireError, type Controller, type LiveSource } from '@emdash/wire/rpc';
import { ipcMain, MessageChannelMain } from 'electron';
import { DESKTOP_WIRE_CHANNEL } from '@core/manifests/shared/wire-channels';
import type { ControllersBundle } from '@main/bootstrap/boot/phases/controllers';
import { appScope } from '@main/bootstrap/core/app-scope';

const scope = appScope.child('desktop-wire');
let installed = false;
let registeredControllers: Record<string, Controller> | undefined;
let resolveControllers: ((controllers: Record<string, Controller>) => void) | undefined;
const controllersPromise = new Promise<Record<string, Controller>>((resolve) => {
  resolveControllers = resolve;
});

/**
 * Installs the renderer-facing wire port handler. Safe to call before the
 * controllers bundle exists: port requests are granted immediately and any
 * traffic queues inside the lazy routing controller until
 * `registerDesktopWireControllers` provides the bundle.
 */
export function installDesktopWire(): void {
  if (installed || typeof ipcMain?.handle !== 'function') return;
  installed = true;

  // Validation happens inside each routed controller: `createController`
  // applies the environment default at every controller site.
  scope.add(
    exposeWireToWindows({ ipcMain, createMessageChannel }, createLazyRoutingController(), {
      channel: DESKTOP_WIRE_CHANNEL,
    })
  );
}

/** Provides the controllers bundle; releases any wire traffic queued so far. */
export function registerDesktopWireControllers(bundle: ControllersBundle): void {
  if (registeredControllers) return;
  registeredControllers = bundle.controllers;
  scope.add(() => bundle.scope.dispose());
  resolveControllers?.(bundle.controllers);
}

function createMessageChannel() {
  const channel = new MessageChannelMain();
  return { port1: channel.port1, port2: channel.port2 };
}

function createLazyRoutingController(): Controller {
  return {
    async call(path, input, meta) {
      const controllers = registeredControllers ?? (await controllersPromise);
      const routed = route(path, controllers);
      return await routed.controller.call(routed.path, input, meta);
    },
    resolveLive(topic) {
      if (registeredControllers) {
        const routed = route(topic, registeredControllers);
        return routed.controller.resolveLive(routed.path);
      }
      return deferredLiveSource(topic);
    },
    acquireLive(topic) {
      if (registeredControllers) {
        const routed = route(topic, registeredControllers);
        return routed.controller.acquireLive(routed.path);
      }
      return deferredLiveLease(topic);
    },
  };
}

/**
 * A live source for a topic requested before controllers registered: traffic
 * waits for registration and then delegates to the routed source. An unknown
 * topic surfaces as NOT_FOUND at first use, matching the routed behavior.
 */
function deferredLiveSource(topic: string): LiveSource {
  const resolved = controllersPromise.then((controllers) => {
    const routed = route(topic, controllers);
    const source = routed.controller.resolveLive(routed.path);
    if (!source) throw new WireError('NOT_FOUND', `Unknown live topic '${topic}'`);
    return source;
  });
  resolved.catch(() => {});
  return {
    async snapshot() {
      return await (await resolved).snapshot();
    },
    async subscribe(cb, options) {
      return await (await resolved).subscribe(cb, options);
    },
  };
}

/**
 * Lease-style counterpart of {@link deferredLiveSource}. An unknown topic
 * surfaces as UNKNOWN_TOPIC, matching `requireLiveLease` in the wire server —
 * the two deferred variants intentionally mirror their routed counterparts'
 * error codes.
 */
function deferredLiveLease(topic: string): PendingLease<LiveSource> {
  let inner: PendingLease<LiveSource> | null | undefined;
  const acquired = controllersPromise.then((controllers) => {
    const routed = route(topic, controllers);
    inner = routed.controller.acquireLive(routed.path);
    if (!inner) throw new WireError('UNKNOWN_TOPIC', `Unknown live topic '${topic}'`);
    return inner;
  });
  acquired.catch(() => {});
  return {
    ready: async () => await (await acquired).ready(),
    release: async () => {
      const lease = await acquired.catch(() => undefined);
      await lease?.release();
    },
  };
}

function route(path: string, controllers: Record<string, Controller>) {
  const [prefix, ...rest] = path.split('.');
  const controller = controllers[prefix];
  if (!controller || rest.length === 0) {
    throw new Error(`Unknown desktop wire path '${path}'`);
  }
  return { controller, path: rest.join('.') };
}
