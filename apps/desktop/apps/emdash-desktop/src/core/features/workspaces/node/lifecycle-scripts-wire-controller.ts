import type { HostRef } from '@emdash/core/primitives/host/api';
import type { ScriptRunNotFoundError } from '@emdash/core/runtimes/scripts/api';
import type { WorkspaceNotFoundError } from '@emdash/core/runtimes/workspace-registry/api';
import type {
  HostRuntimesClient,
  RuntimeBroker,
  RuntimeResolveError,
} from '@emdash/core/services/runtime-broker/api';
import { runtimeResolveErrorAsError } from '@emdash/core/services/runtime-broker/api';
import { err, type Result } from '@emdash/shared';
import type { LiveModelProvider, LiveSource } from '@emdash/wire/rpc';
import { createController, type Controller } from '@emdash/wire/rpc';
import {
  lifecycleScriptsWireContract,
  type LifecycleScriptsWireContract,
} from '@core/features/workspaces/api/lifecycle-scripts-wire-contract';
import { forwardLiveModel } from '@core/services/runtime-clients/node/forward-live-model';

export type LifecycleScriptsIdentity = Readonly<{
  workspaceId: string;
  host: HostRef;
  path: string;
}>;

export type CreateLifecycleScriptsWireControllerOptions = Readonly<{
  runtimes: RuntimeBroker;
  workspaceIdentity: {
    resolve(workspaceId: string): Promise<LifecycleScriptsIdentity | null>;
  };
}>;

/**
 * Pass-through to the host scripts plane (spec: activation-scripts-via-terminals):
 * resolves workspace ids to host paths and forwards. `start` goes through the host
 * registry's runScript so the request is built from the record; everything else
 * talks to the scripts runtime directly. No env, settings, or command assembly
 * happens on the desktop.
 */
export function createLifecycleScriptsWireController(
  options: CreateLifecycleScriptsWireControllerOptions
): Controller {
  return createController(lifecycleScriptsWireContract, {
    runs: createRunsProvider(options),
    output: async (key) =>
      resolveRuntimeSource(options, key.workspaceId, (client, identity) =>
        client.scripts.output
          .handle({ workspacePath: identity.path, script: key.script })
          .asLiveSource()
      ),
    start: ({ workspaceId, script, provenance }) =>
      withRuntime(options, workspaceId, missingWorkspace, (client) =>
        client.workspaceRegistry.runScript({ workspaceId, script, provenance })
      ),
    stop: ({ workspaceId, script }) =>
      withRuntime(options, workspaceId, missingRun, (client, identity) =>
        client.scripts.stop({ workspacePath: identity.path, script })
      ),
    sendInput: ({ workspaceId, script, data }) =>
      withRuntime(options, workspaceId, missingRun, (client, identity) =>
        client.scripts.sendInput({ workspacePath: identity.path, script, data })
      ),
    resize: ({ workspaceId, script, cols, rows }) =>
      withRuntime(options, workspaceId, missingRun, (client, identity) =>
        client.scripts.resize({ workspacePath: identity.path, script, cols, rows })
      ),
  });
}

function missingWorkspace(workspaceId: string): WorkspaceNotFoundError {
  return { type: 'workspace-not-found', workspaceId };
}

function missingRun(workspaceId: string): ScriptRunNotFoundError {
  return { type: 'not-found', message: `Workspace ${workspaceId} was not found` };
}

function createRunsProvider(
  options: CreateLifecycleScriptsWireControllerOptions
): LiveModelProvider<LifecycleScriptsWireContract['runs']> {
  return forwardLiveModel(lifecycleScriptsWireContract.runs, (key, name) =>
    resolveRuntimeSource(options, key.workspaceId, (client, identity) =>
      client.scripts.runs.state({ workspacePath: identity.path }, name).asLiveSource()
    )
  );
}

async function withRuntime<T, E, Missing>(
  options: CreateLifecycleScriptsWireControllerOptions,
  workspaceId: string,
  missing: (workspaceId: string) => Missing,
  work: (client: HostRuntimesClient, identity: LifecycleScriptsIdentity) => Promise<Result<T, E>>
): Promise<Result<T, E | Missing | RuntimeResolveError>> {
  const identity = await options.workspaceIdentity.resolve(workspaceId);
  if (!identity) return err(missing(workspaceId));
  const runtime = await options.runtimes.client(identity.host);
  if (!runtime.success) return err(runtime.error);
  return work(runtime.data, identity);
}

async function resolveRuntimeSource(
  options: CreateLifecycleScriptsWireControllerOptions,
  workspaceId: string,
  source: (client: HostRuntimesClient, identity: LifecycleScriptsIdentity) => LiveSource
): Promise<LiveSource> {
  const identity = await options.workspaceIdentity.resolve(workspaceId);
  if (!identity) throw new Error(`Workspace ${workspaceId} was not found`);
  const runtime = await options.runtimes.client(identity.host);
  if (!runtime.success) throw runtimeResolveErrorAsError(runtime.error);
  return source(runtime.data, identity);
}
