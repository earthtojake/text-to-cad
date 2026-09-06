import { describe, expect, it } from 'vitest';
import { PROTOCOL_VERSION, negotiateProtocol, protocolUpgradeMessage } from '.';

describe('negotiateProtocol', () => {
  describe('compatible cases', () => {
    it('returns compatible for equal versions', () => {
      const result = negotiateProtocol('1.0.0', '1.0.0');
      expect(result.compatible).toBe(true);
      if (!result.compatible) return;
      expect(result.agreedVersion).toBe('1.0.0');
      expect(result.agreedMinor).toBe(0);
    });

    it('negotiates down to client minor when server minor is higher', () => {
      const result = negotiateProtocol('1.0.0', '1.3.0');
      expect(result.compatible).toBe(true);
      if (!result.compatible) return;
      expect(result.agreedMinor).toBe(0);
      expect(result.agreedVersion).toBe('1.0.0');
    });

    it('negotiates down to server minor when client minor is higher', () => {
      const result = negotiateProtocol('1.5.0', '1.2.0');
      expect(result.compatible).toBe(true);
      if (!result.compatible) return;
      expect(result.agreedMinor).toBe(2);
      expect(result.agreedVersion).toBe('1.2.0');
    });

    it('agrees on equal minor', () => {
      const result = negotiateProtocol('2.4.1', '2.4.7');
      expect(result.compatible).toBe(true);
      if (!result.compatible) return;
      expect(result.agreedMinor).toBe(4);
    });

    it('ignores patch version differences', () => {
      const result = negotiateProtocol('1.0.0', '1.0.99');
      expect(result.compatible).toBe(true);
    });
  });

  describe('incompatible cases', () => {
    it('returns upgrade-client when client major is lower', () => {
      const result = negotiateProtocol('1.9.0', '2.0.0');
      expect(result.compatible).toBe(false);
      if (result.compatible) return;
      expect(result.action).toBe('upgrade-client');
      expect(result.clientProtocolVersion).toBe('1.9.0');
      expect(result.serverProtocolVersion).toBe('2.0.0');
    });

    it('returns upgrade-server when client major is higher', () => {
      const result = negotiateProtocol('3.0.0', '2.5.0');
      expect(result.compatible).toBe(false);
      if (result.compatible) return;
      expect(result.action).toBe('upgrade-server');
    });

    it('returns upgrade-client for an unparseable client version', () => {
      const result = negotiateProtocol('not-a-version', '1.0.0');
      expect(result.compatible).toBe(false);
      if (result.compatible) return;
      expect(result.action).toBe('upgrade-client');
    });

    it('returns upgrade-client for an empty client version string', () => {
      const result = negotiateProtocol('', '1.0.0');
      expect(result.compatible).toBe(false);
      if (result.compatible) return;
      expect(result.action).toBe('upgrade-client');
    });
  });

  describe('uses PROTOCOL_VERSION default for serverProtocolVersion', () => {
    it('accepts the current protocol version without a second argument', () => {
      // Re-importing PROTOCOL_VERSION directly avoids hardcoding the string.
      // This test will catch an unintentional default change.
      const result = negotiateProtocol(PROTOCOL_VERSION);
      expect(result.compatible).toBe(true);
    });

    it('rejects pre-1.0 clients against the default with upgrade-client', () => {
      const result = negotiateProtocol('0.9.0');
      expect(result).toEqual({
        compatible: false,
        action: 'upgrade-client',
        clientProtocolVersion: '0.9.0',
        serverProtocolVersion: PROTOCOL_VERSION,
      });
    });

    it('requires older major clients to upgrade for breaking contract changes', () => {
      const result = negotiateProtocol('2.0.0');

      expect(result).toEqual({
        compatible: false,
        action: 'upgrade-client',
        clientProtocolVersion: '2.0.0',
        serverProtocolVersion: PROTOCOL_VERSION,
      });
    });
  });
});

describe('protocolUpgradeMessage', () => {
  it('returns a desktop app upgrade message for upgrade-client', () => {
    const msg = protocolUpgradeMessage('upgrade-client');
    expect(msg).toContain('Hardcore');
    expect(msg.length).toBeGreaterThan(0);
  });

  it('returns a workspace server upgrade message for upgrade-server', () => {
    const msg = protocolUpgradeMessage('upgrade-server');
    expect(msg).toContain('workspace server');
    expect(msg.length).toBeGreaterThan(0);
  });
});
