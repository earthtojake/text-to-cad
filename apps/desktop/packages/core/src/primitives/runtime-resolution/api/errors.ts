import { z } from 'zod';
import { hostRefSchema, type HostRef } from '../../host/api';

export const runtimeUnavailableReasonSchema = z.enum([
  'offline',
  'connection-failed',
  'daemon-start-failed',
  'artifact-download-failed',
  'install-failed',
  'unsupported-platform',
  'protocol-upgrade-client',
  'protocol-upgrade-server',
  'runtime-unavailable',
]);

const runtimeResolveErrorInputSchema = z.discriminatedUnion('type', [
  z.object({
    type: z.literal('host-unavailable'),
    host: hostRefSchema,
    reason: runtimeUnavailableReasonSchema.optional(),
    message: z.string(),
  }),
  z.object({
    type: z.literal('not-configured'),
    host: hostRefSchema,
    message: z.string(),
  }),
  z.object({
    type: z.literal('host-identity-lost'),
    host: hostRefSchema,
    message: z.string(),
  }),
]);

export const runtimeResolveErrorSchema = runtimeResolveErrorInputSchema.transform((error) =>
  error.type === 'host-unavailable'
    ? { ...error, reason: error.reason ?? ('runtime-unavailable' as const) }
    : error
);

export type RuntimeResolveError = z.output<typeof runtimeResolveErrorSchema>;
export type RuntimeUnavailableReason = z.output<typeof runtimeUnavailableReasonSchema>;

export function runtimeHostUnavailable(host: HostRef, message: string): RuntimeResolveError;
export function runtimeHostUnavailable(
  host: HostRef,
  reason: RuntimeUnavailableReason,
  message: string
): RuntimeResolveError;
export function runtimeHostUnavailable(
  host: HostRef,
  reasonOrMessage: RuntimeUnavailableReason | string,
  message?: string
): RuntimeResolveError {
  return {
    type: 'host-unavailable',
    host,
    reason:
      message === undefined ? 'runtime-unavailable' : (reasonOrMessage as RuntimeUnavailableReason),
    message: message ?? reasonOrMessage,
  };
}

export function runtimeHostNotConfigured(host: HostRef, message: string): RuntimeResolveError {
  return { type: 'not-configured', host, message };
}

export function runtimeHostIdentityLost(host: HostRef, message: string): RuntimeResolveError {
  return { type: 'host-identity-lost', host, message };
}

export function isRuntimeResolveError(value: unknown): value is RuntimeResolveError {
  if (!runtimeResolveErrorSchema.safeParse(value).success) return false;
  if (
    typeof value === 'object' &&
    value !== null &&
    'type' in value &&
    value.type === 'host-unavailable'
  ) {
    return 'reason' in value && runtimeUnavailableReasonSchema.safeParse(value.reason).success;
  }
  return true;
}

/**
 * Adapts resolver failures for internal paths that cannot return Result. Wire
 * procedures must return the serializable RuntimeResolveError instead.
 */
export function runtimeResolveErrorAsError(
  error: RuntimeResolveError
): Error & RuntimeResolveError {
  return Object.assign(new Error(error.message), error);
}
