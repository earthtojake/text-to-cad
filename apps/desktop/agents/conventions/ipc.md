# IPC Conventions

## Wire Pattern

All renderer-main application traffic uses `@emdash/wire`:

- **Contracts**: `src/core/features/<domain>/api/` using `defineContract`.
- **Controllers**: `src/core/features/<domain>/node/` using `createController`.
- **Manifest**: `src/core/manifests/shared/desktop-wire-contract.ts`.
- **Gateway**: `src/main/gateway/desktop-wire.ts`.
- **Connection seam**: `src/core/primitives/wire/browser/connection.ts` — the renderer bootstrap
  seeds the connection once (`seedWireConnection`, via
  `src/renderer/lib/runtime/seed-desktop-wire.ts`); core code never acquires a connection itself.
- **Clients**: each slice exports a typed domain client from its `api/`, built on `domainClient`
  and the slice's exported domain constant.

```ts
// Contract (api/contract.ts)
export const exampleDomain = 'example' as const;
export const exampleContract = defineContract({
  doSomething: procedure({
    input: z.object({ id: z.string() }),
    output: z.custom<Result>(),
  }),
});

// Domain client (api/client.ts)
export type ExampleClient = ContractClient<typeof exampleContract>;
export function getExampleClient(): Promise<ExampleClient> {
  return domainClient<ExampleClient>(exampleDomain, exampleContract);
}

// Consumer
const client = await getExampleClient();
const result = await client.doSomething({ id: '123' });
```

## Preload Bridge

The preload bridge in `src/entry/preload.ts` exposes only `requestWirePort` and
`getPathForFile` on `window.electronAPI`. Add renderer-main operations to a Wire contract instead
of extending the bridge.

## Events And State

- Request/response operations use `procedure`.
- Notifications use `eventStream`.
- Resource-backed notifications whose attach acknowledgment must mean ready use
  `resourcedStream`; never encode readiness as a one-shot no-retention event. See the
  [Wire event-stream attachment law](../../packages/wire/docs/README.md#event-stream-attachment-law).
- Broadcast state uses a Wire live model.
- Long-running cancellable work uses a Wire live job.
- Persisted renderer state uses mementos.

## Rules

- Keep contracts in the owning slice's `api/` surface and implementations in `node/`.
- Reach the wire through the owning slice's domain client; the aggregate client in
  `src/renderer/lib/runtime/desktop-wire-client.ts` is renderer-internal only.
- Register contracts and controllers through the desktop Wire manifest and gateway.
- Keep provider-specific adaptation at plugin or slice edges.
- Never import a `node/` surface from browser code.
- Test contracts, controllers, event hosts, and browser stores at their owning boundary.
