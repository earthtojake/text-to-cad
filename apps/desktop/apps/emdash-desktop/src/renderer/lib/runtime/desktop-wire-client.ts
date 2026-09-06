import { client, type Connection } from '@emdash/wire/rpc';
import { desktopWireContract } from '@core/manifests/shared/desktop-wire-contract';
import { getWireConnection } from '@core/primitives/wire/browser/connection';

export type DesktopWireClient = ReturnType<typeof createDesktopWireClientForConnection>;

let clientPromise: Promise<DesktopWireClient> | null = null;

export function getDesktopWireClient(): Promise<DesktopWireClient> {
  clientPromise ??= createDesktopWireClient();
  return clientPromise;
}

export function resetDesktopWireClient(): void {
  clientPromise = null;
}

async function createDesktopWireClient(): Promise<DesktopWireClient> {
  return createDesktopWireClientForConnection(await getWireConnection());
}

function createDesktopWireClientForConnection(connection: Connection) {
  return client(desktopWireContract, connection);
}
