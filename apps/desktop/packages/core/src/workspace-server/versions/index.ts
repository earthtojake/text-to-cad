import semver from 'semver';

export const PROTOCOL_VERSION = '3.0.0';

export function protocolMajor(version: string = PROTOCOL_VERSION): number {
  const parsed = semver.parse(version);
  if (!parsed) throw new Error(`Invalid protocol version '${version}'`);
  return parsed.major;
}

export type ProtocolNegotiation =
  | { compatible: true; agreedVersion: string; agreedMinor: number }
  | {
      compatible: false;
      action: 'upgrade-client' | 'upgrade-server';
      clientProtocolVersion: string;
      serverProtocolVersion: string;
    };

/**
 * Determines protocol compatibility between a client and server.
 *
 * Compatibility rule: same major version implies compatible. The agreed feature
 * level is min(client.minor, server.minor), so old clients connecting to a newer
 * server get the features available at their minor, and vice versa.
 *
 * On a major mismatch the lower major is the stale side and drives the upgrade
 * prompt. Unparseable versions are treated as incompatible with action
 * 'upgrade-client', since a well-formed server always emits a valid semver.
 *
 * Runs on the server against the client's reported version; also used in tests.
 */
export function negotiateProtocol(
  clientProtocolVersion: string,
  serverProtocolVersion: string = PROTOCOL_VERSION
): ProtocolNegotiation {
  const client = semver.parse(clientProtocolVersion);
  const server = semver.parse(serverProtocolVersion);

  if (!client || !server) {
    return {
      compatible: false,
      action: 'upgrade-client',
      clientProtocolVersion,
      serverProtocolVersion,
    };
  }

  if (client.major !== server.major) {
    return {
      compatible: false,
      action: client.major < server.major ? 'upgrade-client' : 'upgrade-server',
      clientProtocolVersion,
      serverProtocolVersion,
    };
  }

  const agreedMinor = Math.min(client.minor, server.minor);
  return {
    compatible: true,
    agreedVersion: `${client.major}.${agreedMinor}.0`,
    agreedMinor,
  };
}

/**
 * Returns a human-readable upgrade message for the given action.
 * Lives in core so every client (desktop, future mobile) surfaces the same text.
 */
export function protocolUpgradeMessage(action: 'upgrade-client' | 'upgrade-server'): string {
  if (action === 'upgrade-client') {
    return 'This version of Hardcore is too old for the remote workspace server. Please update Hardcore.';
  }
  return 'The remote workspace server is out of date. Please upgrade the workspace server on the remote machine.';
}
