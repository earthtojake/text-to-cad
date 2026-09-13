import { LOCAL_HOST_REF } from '@emdash/core/primitives/host/api';
import type * as WireLiveModule from '@emdash/wire/live';
import type * as WireStateModule from '@emdash/wire/state';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AcpAuthLoginBinding } from '@core/features/agents/api/browser/auth-login-binding';

const runtimeClient = vi.hoisted(() => ({
  current: undefined as unknown,
}));

vi.mock('@core/features/agents/api/browser/client', () => ({
  getAgentsClient: () => Promise.resolve(runtimeClient.current),
}));

vi.mock('@emdash/wire/state', async (importOriginal) => {
  const actual = await importOriginal<typeof WireStateModule>();
  return {
    ...actual,
    remote: vi.fn(() => {
      const list = {
        __stateNode: {
          observe(listener: (snapshot: unknown) => void) {
            listener({
              status: 'ready',
              value: {
                provider: {
                  auth: { status: { kind: 'unknown' }, login: null },
                },
              },
            });
            return () => {};
          },
        },
        refresh: vi.fn(async () => {}),
      };
      return Object.assign(() => ({ states: { list } }), { dispose: vi.fn(async () => {}) });
    }),
  };
});

vi.mock('@emdash/wire/live', async (importOriginal) => {
  const actual = await importOriginal<typeof WireLiveModule>();
  return {
    ...actual,
    ReplicaLog: class {
      readonly ready = Promise.resolve();
      readonly dispose = vi.fn(async () => {});
    },
  };
});

describe('AcpAuthLoginBinding', () => {
  beforeEach(() => {
    runtimeClient.current = createClient();
  });

  it('routes login calls through the explicit host', async () => {
    const client = runtimeClient.current as ReturnType<typeof createClient>;
    const binding = await AcpAuthLoginBinding.create(createArgs());

    expect(client.startLogin).toHaveBeenCalledWith(
      {
        host: LOCAL_HOST_REF,
        providerId: 'provider',
        methodId: 'browser',
      },
      expect.anything()
    );
    expect(client.loginOutput.handle).toHaveBeenCalledWith({
      host: LOCAL_HOST_REF,
      providerId: 'provider',
    });
    await binding.dispose();
  });

  it('passes the measured initial grid through startLogin', async () => {
    const client = runtimeClient.current as ReturnType<typeof createClient>;
    const binding = await AcpAuthLoginBinding.create({
      ...createArgs(),
      initialDims: { cols: 137, rows: 41 },
    });

    expect(client.startLogin).toHaveBeenCalledWith(
      {
        host: LOCAL_HOST_REF,
        providerId: 'provider',
        methodId: 'browser',
        cols: 137,
        rows: 41,
      },
      expect.anything()
    );
    await binding.dispose();
  });

  it('cancels login once during idempotent disposal', async () => {
    const client = runtimeClient.current as ReturnType<typeof createClient>;
    const binding = await AcpAuthLoginBinding.create(createArgs());

    await Promise.all([binding.dispose(), binding.dispose()]);

    expect(client.cancelLogin).toHaveBeenCalledTimes(1);
    expect(client.cancelLogin).toHaveBeenCalledWith({
      host: LOCAL_HOST_REF,
      providerId: 'provider',
    });
  });

  it('cancels the login when startLogin throws client-side', async () => {
    // A client-side failure (e.g. response validation) after the server
    // already started the login must not leak a running login PTY.
    const client = runtimeClient.current as ReturnType<typeof createClient>;
    client.startLogin.mockRejectedValue(new Error('client-side validation failed'));

    await expect(AcpAuthLoginBinding.create(createArgs())).rejects.toThrow(
      'client-side validation failed'
    );

    expect(client.cancelLogin).toHaveBeenCalledTimes(1);
    expect(client.cancelLogin).toHaveBeenCalledWith({
      host: LOCAL_HOST_REF,
      providerId: 'provider',
    });
  });

  it('honors dispose(false) without cancelling the login', async () => {
    const client = runtimeClient.current as ReturnType<typeof createClient>;
    const binding = await AcpAuthLoginBinding.create(createArgs());

    await binding.dispose(false);

    expect(client.cancelLogin).not.toHaveBeenCalled();
  });

  it('keeps resize latest-wins by cancelling the previous resize run', async () => {
    const client = runtimeClient.current as ReturnType<typeof createClient>;
    const signals: AbortSignal[] = [];
    client.resizeLogin.mockImplementation((_input: unknown, meta?: RpcMeta) => {
      if (!meta) throw new Error('Expected resize metadata');
      signals.push(meta.signal as AbortSignal);
      return new Promise<{ success: boolean; data: undefined }>((resolve, reject) => {
        meta.signal?.addEventListener('abort', () => reject(meta.signal?.reason), { once: true });
        if (signals.length === 2) resolve({ success: true, data: undefined });
      });
    });
    const binding = await AcpAuthLoginBinding.create(createArgs());

    binding.resize(80, 24);
    await Promise.resolve();
    binding.resize(120, 40);
    await Promise.resolve();

    expect(signals).toHaveLength(2);
    expect(signals[0]?.aborted).toBe(true);
    expect(signals[1]?.aborted).toBe(false);
    await binding.dispose();
  });
});

function createArgs(): Parameters<typeof AcpAuthLoginBinding.create>[0] {
  return {
    host: LOCAL_HOST_REF,
    providerId: 'provider',
    methodId: 'browser',
    terminal: {
      reset: vi.fn(),
      write: vi.fn(),
    },
  };
}

function createClient() {
  return {
    startLogin: vi.fn(async (_input: unknown, _meta?: RpcMeta) => ({
      success: true,
      data: undefined,
    })),
    cancelLogin: vi.fn(async (_input: unknown) => ({ success: true, data: undefined })),
    sendLoginInput: vi.fn(async (_input: unknown, _meta?: RpcMeta) => ({
      success: true,
      data: undefined,
    })),
    resizeLogin: vi.fn(async (_input: unknown, _meta?: RpcMeta) => ({
      success: true,
      data: undefined,
    })),
    markUrlHandled: vi.fn(async (_input: unknown, _meta?: RpcMeta) => ({
      success: true,
      data: undefined,
    })),
    auth: {
      state: vi.fn(() => ({})),
    },
    loginOutput: {
      handle: vi.fn(() => ({})),
    },
  };
}

type RpcMeta = {
  signal?: AbortSignal;
};
