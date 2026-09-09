import type { HostRef } from '@emdash/core/primitives/host/api';
import type { AgentConfigList, AuthStatusModelState } from '@emdash/core/runtimes/agent-config/api';
import type { Result } from '@emdash/shared';
import { createScope, type Run, type Scope } from '@emdash/shared/concurrency';
import { ReplicaLog } from '@emdash/wire/live';
import { observe, remote, whenReady, type Readable } from '@emdash/wire/state';
import type { Terminal } from '@xterm/xterm';
import { agentsContract } from '@core/features/agents/api';
import { getAgentsClient, type AgentsRpcClient } from '@core/features/agents/api/browser/client';
import { createXtermLogSink } from '@core/features/terminals/api/browser/pty/xterm-log-sink';

type AuthStatusHandle = {
  readonly ready: Promise<void>;
  current(): AuthStatusModelState;
  dispose(): Promise<void>;
};

export class AcpAuthLoginBinding {
  private constructor(
    private readonly scope: Scope,
    private readonly client: AgentsRpcClient,
    readonly host: HostRef,
    readonly providerId: string,
    readonly status: AuthStatusHandle,
    private readonly cancellation: { cancelOnDispose: boolean }
  ) {}

  private resizeRun: Run<unknown> | undefined;

  static async create(args: {
    host: HostRef;
    providerId: string;
    methodId: string;
    terminal: Pick<Terminal, 'reset' | 'write'>;
    /**
     * Grid measured from the mounted terminal, so the login PTY spawns at the
     * right size instead of emitting a burst of wrongly-wrapped output at the
     * server default. Omitted when the terminal could not be measured yet;
     * the post-attach resize then converges the PTY.
     */
    initialDims?: { cols: number; rows: number };
  }): Promise<AcpAuthLoginBinding> {
    const scope = createScope({ label: `auth-login:${args.providerId}` });
    const cancellation = { cancelOnDispose: true };
    try {
      const client = await getAgentsClient();
      // Registered before startLogin: if the call succeeds server-side but
      // throws client-side (e.g. response validation), disposal must still
      // cancel the login PTY on the host. Cancelling a login that never
      // started is a harmless no-op error.
      scope.add(() => {
        if (!cancellation.cancelOnDispose) return;
        return client
          .cancelLogin({ host: args.host, providerId: args.providerId })
          .then(() => undefined);
      });
      const result = await client.startLogin(
        {
          host: args.host,
          providerId: args.providerId,
          methodId: args.methodId,
          ...(args.initialDims ?? {}),
        },
        { signal: scope.signal }
      );
      if (!result.success) throw new Error(errorMessage(result));

      const key = { host: args.host, providerId: args.providerId };
      const auth = remote(agentsContract.auth, client.auth, {
        scope,
        lingerMs: 15_000,
      });
      const status = createAuthStatusHandle(
        args.providerId,
        auth({ host: args.host }).states.list,
        scope
      );
      const output = new ReplicaLog(client.loginOutput.handle(key), {
        store: createXtermLogSink(args.terminal),
      });
      scope.add(() => output.dispose());

      await scope
        .run('attach-replicas', async () => {
          await Promise.all([status.ready, output.ready]);
        })
        .value();

      return new AcpAuthLoginBinding(
        scope,
        client,
        args.host,
        args.providerId,
        status,
        cancellation
      );
    } catch (error) {
      await scope.dispose(error);
      throw error;
    }
  }

  sendInput(data: string): void {
    if (this.scope.disposed) return;
    this.scope.run('send-login-input', (signal) =>
      this.client.sendLoginInput({ host: this.host, providerId: this.providerId, data }, { signal })
    );
  }

  resize(cols: number, rows: number): void {
    if (this.scope.disposed) return;
    this.resizeRun?.cancel(new Error('Login resize superseded'));
    const run = this.scope.run('resize-login', (signal) =>
      this.client.resizeLogin(
        { host: this.host, providerId: this.providerId, cols, rows },
        { signal }
      )
    );
    this.resizeRun = run;
    void run.exit.then(() => {
      if (this.resizeRun === run) this.resizeRun = undefined;
    });
  }

  markUrlHandled(urlId: string): void {
    if (this.scope.disposed) return;
    this.scope.run('mark-url-handled', (signal) =>
      this.client.markUrlHandled(
        { host: this.host, providerId: this.providerId, urlId },
        { signal }
      )
    );
  }

  dispose(cancel = true): Promise<void> {
    this.cancellation.cancelOnDispose = cancel;
    return this.scope.dispose();
  }
}

function createAuthStatusHandle(
  providerId: string,
  agents: Readable<AgentConfigList | undefined>,
  parentScope: Scope
): AuthStatusHandle {
  const scope = parentScope.child(`auth-status:${providerId}`);
  let current: AgentConfigList = {};
  observe(
    agents,
    (snapshot) => {
      current = snapshot.value ?? {};
    },
    { scope }
  );
  return {
    ready: whenReady(agents, { scope }).then(() => undefined),
    current: () => current[providerId]?.auth ?? { status: { kind: 'unknown' }, login: null },
    dispose: () => scope.dispose(),
  };
}

function errorMessage(result: Result<unknown, { type: string; message?: string }>): string {
  if (result.success) return '';
  return result.error.message ?? result.error.type;
}
