import { err, ok, type Result } from '@emdash/shared';
import semver from 'semver';
import { z } from 'zod';
import { protocolMajor } from './versions';

// Core is intentionally stricter than install.sh until its validator is tightened. The regex
// rejects normalized inputs and build metadata; semver.valid rejects forms with leading zeroes.
// Build metadata is excluded because SemVer ignores it when deciding update precedence.
const releaseVersionPattern = /^[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?$/;

export const releaseChannelSchema = z.enum(['stable', 'canary']);
export type ReleaseChannel = z.infer<typeof releaseChannelSchema>;

export const releaseVersionSchema = z
  .string()
  .regex(releaseVersionPattern, 'Release version must be a full SemVer string')
  .refine((version) => semver.valid(version) !== null, 'Release version must be valid SemVer');

export const channelPointerSchema = z.object({
  artifactVersion: releaseVersionSchema,
  protocolVersion: releaseVersionSchema,
});
export type ChannelPointer = z.infer<typeof channelPointerSchema>;

export type ChannelPointerParseError =
  | { type: 'invalid'; reason: string }
  | {
      type: 'protocol-major-mismatch';
      expected: number;
      actual: number;
    };

export function channelPointerPath(channel: ReleaseChannel, major: number): string {
  assertPositiveProtocolMajor(major);
  return `channels/${channel}/protocol-${major}.json`;
}

export function isNewerRelease(candidate: string, installed: string): boolean {
  if (semver.valid(candidate) === null || semver.valid(installed) === null) return false;
  return semver.gt(candidate, installed);
}

export function parseChannelPointer(
  text: string,
  expectedProtocolMajor: number
): Result<ChannelPointer, ChannelPointerParseError> {
  assertPositiveProtocolMajor(expectedProtocolMajor);

  let value: unknown;
  try {
    value = JSON.parse(text) as unknown;
  } catch (error) {
    return err({
      type: 'invalid',
      reason: error instanceof Error ? error.message : String(error),
    });
  }

  const parsed = channelPointerSchema.safeParse(value);
  if (!parsed.success) {
    return err({ type: 'invalid', reason: z.prettifyError(parsed.error) });
  }

  const actualProtocolMajor = protocolMajor(parsed.data.protocolVersion);
  if (actualProtocolMajor !== expectedProtocolMajor) {
    return err({
      type: 'protocol-major-mismatch',
      expected: expectedProtocolMajor,
      actual: actualProtocolMajor,
    });
  }

  return ok(parsed.data);
}

export function serializeChannelPointer(pointer: ChannelPointer): string {
  const parsed = channelPointerSchema.parse(pointer);
  return `${JSON.stringify(
    {
      artifactVersion: parsed.artifactVersion,
      protocolVersion: parsed.protocolVersion,
    },
    undefined,
    2
  )}\n`;
}

function assertPositiveProtocolMajor(major: number): void {
  if (!Number.isSafeInteger(major) || major <= 0) {
    throw new Error('Protocol major must be a positive safe integer');
  }
}
