import { createInProcessWire, defineContract } from '@emdash/wire/rpc';
import { resetWireConnection, seedWireConnection } from './connection';

/**
 * Slice-level test setup: serve ONLY this slice's contract (nested under its domain
 * key, so paths match production routing) and seed the seam with the in-process
 * connection. The slice's browser code then runs unmodified — no renderer host,
 * no Electron, no other slices.
 */
export function seedSliceWire(
  domain: string,
  contract: object,
  impl: object
): { dispose: () => Promise<void> } {
  const wire = createInProcessWire(
    // oxlint-disable-next-line typescript/no-explicit-any -- generic harness over any slice contract
    defineContract({ [domain]: contract } as any),
    { [domain]: impl },
    // Explicit policy: slice tests always validate fully, and the default
    // policy reads process.env, which does not exist in real-browser tests.
    { validate: 'full' }
  );
  resetWireConnection();
  seedWireConnection(async () => wire.connection);
  return {
    async dispose() {
      resetWireConnection();
      await wire.dispose();
    },
  };
}
