import { describe, expect, it } from 'vitest';
import {
  channelPointerPath,
  channelPointerSchema,
  isNewerRelease,
  parseChannelPointer,
  releaseChannelSchema,
  releaseVersionSchema,
  serializeChannelPointer,
} from './releases';
import { protocolMajor, PROTOCOL_VERSION } from './versions';

describe('workspace-server release contracts', () => {
  const pointer = {
    artifactVersion: '0.1.0',
    protocolVersion: '1.0.0',
  };

  it('round-trips a channel pointer with byte-stable serialization', () => {
    const serialized = serializeChannelPointer(pointer);

    expect(serialized).toBe('{\n  "artifactVersion": "0.1.0",\n  "protocolVersion": "1.0.0"\n}\n');
    expect(
      serializeChannelPointer({
        protocolVersion: pointer.protocolVersion,
        artifactVersion: pointer.artifactVersion,
      })
    ).toBe(serialized);
    expect(parseChannelPointer(serialized, 1)).toEqual({ success: true, data: pointer });
  });

  it('rejects a pointer for another protocol major', () => {
    expect(
      parseChannelPointer(JSON.stringify({ artifactVersion: '0.2.0', protocolVersion: '2.0.0' }), 1)
    ).toEqual({
      success: false,
      error: {
        type: 'protocol-major-mismatch',
        expected: 1,
        actual: 2,
      },
    });
  });

  it('ignores unknown pointer fields for append-only evolution', () => {
    const result = parseChannelPointer(
      JSON.stringify({ ...pointer, publishedAt: '2026-08-14T00:00:00Z' }),
      1
    );

    expect(result).toEqual({ success: true, data: pointer });
  });

  it.each([
    ['invalid JSON', '{'],
    ['a missing field', JSON.stringify({ artifactVersion: '0.1.0' })],
    [
      'an invalid artifact version',
      JSON.stringify({ artifactVersion: 'v0.1.0', protocolVersion: '1.0.0' }),
    ],
    [
      'an invalid protocol version',
      JSON.stringify({ artifactVersion: '0.1.0', protocolVersion: '01.0.0' }),
    ],
  ])('returns an invalid result for %s', (_label, contents) => {
    expect(parseChannelPointer(contents, 1)).toEqual({
      success: false,
      error: { type: 'invalid', reason: expect.any(String) },
    });
  });

  it('rejects invalid data before serialization', () => {
    expect(() =>
      serializeChannelPointer({ artifactVersion: 'v0.1.0', protocolVersion: '1.0.0' })
    ).toThrow();
  });

  it('constructs relative channel pointer paths', () => {
    expect(channelPointerPath('stable', 1)).toBe('channels/stable/protocol-1.json');
    expect(channelPointerPath('canary', 2)).toBe('channels/canary/protocol-2.json');
  });

  it.each([
    ['a newer prerelease line', '0.1.1-canary.42', '0.1.0', true],
    ['a stable release over its prerelease', '0.1.1', '0.1.1-canary.42', true],
    ['a stable downgrade from an installed canary', '0.1.0', '0.1.1-canary.42', false],
    ['equal releases', '0.1.0', '0.1.0', false],
    ['candidate build metadata only', '0.1.0+candidate', '0.1.0+installed', false],
    ['invalid candidate input', 'not-a-version', '0.1.0', false],
    ['invalid installed input', '0.1.0', 'not-a-version', false],
  ])('compares %s by SemVer precedence', (_label, candidate, installed, expected) => {
    expect(isNewerRelease(candidate, installed)).toBe(expected);
  });

  it.each([0, -1, 1.5, Number.NaN, Number.POSITIVE_INFINITY, 2 ** 53])(
    'rejects invalid protocol major %s in a channel pointer path',
    (major) => {
      expect(() => channelPointerPath('stable', major)).toThrow('positive safe integer');
    }
  );

  it('extracts a protocol major and rejects invalid protocol versions', () => {
    expect(PROTOCOL_VERSION).toBe('3.0.0');
    expect(protocolMajor()).toBe(3);
    expect(protocolMajor('2.3.4')).toBe(2);
    expect(() => protocolMajor('not-a-version')).toThrow(
      "Invalid protocol version 'not-a-version'"
    );
  });

  it.each(['stable', 'canary'])('accepts the %s release channel', (channel) => {
    expect(releaseChannelSchema.safeParse(channel).success).toBe(true);
  });

  it('rejects an unknown release channel', () => {
    expect(releaseChannelSchema.safeParse('preview').success).toBe(false);
  });

  it.each(['0.1.0', '1.2.3-canary.42', '0.1.0-dev.abc123.1234567890'])(
    'accepts strict release semver %s',
    (version) => {
      expect(releaseVersionSchema.safeParse(version).success).toBe(true);
    }
  );

  it.each(['1.2', 'v1.2.3', '1.2.3 ', '01.2.3', '1.02.3', '1.2.03', '1.2.3-01', '1.2.3+build.42'])(
    'rejects non-orderable or non-strict semver %s',
    (version) => {
      expect(releaseVersionSchema.safeParse(version).success).toBe(false);
    }
  );

  it('defines the pointer as separate artifact and protocol versions', () => {
    expect(channelPointerSchema.parse(pointer)).toEqual(pointer);
  });
});
