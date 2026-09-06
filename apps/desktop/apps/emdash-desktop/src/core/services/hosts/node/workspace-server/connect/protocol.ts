import {
  protocolUpgradeMessage,
  PROTOCOL_VERSION,
  workspaceWireContract,
  type WireInitializeResult,
  type WireProtocolIncompatible,
} from '@emdash/core/workspace-server';
import { client as createClient, connect, type WireTransport } from '@emdash/wire/rpc';

export class WorkspaceServerProtocolError extends Error {
  readonly name = 'WorkspaceServerProtocolError';

  constructor(readonly details: WireProtocolIncompatible) {
    super(protocolUpgradeMessage(details.action));
  }
}

export async function initializeWorkspaceServerTransport(
  transport: WireTransport,
  protocolVersion: string = PROTOCOL_VERSION,
  client: { id: string; appVersion: string } = { id: 'hardcore-desktop', appVersion: '0.0.0' }
): Promise<WireInitializeResult> {
  const handshakeConnection = connect(transport);
  const handshakeClient = createClient(workspaceWireContract, handshakeConnection);
  try {
    const initialized = await handshakeClient.initialize({ protocolVersion, client });
    if (!initialized.success) throw new WorkspaceServerProtocolError(initialized.error);
    return initialized.data;
  } catch (error) {
    transport.close?.();
    throw error;
  } finally {
    handshakeConnection.dispose();
  }
}
