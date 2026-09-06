import { z } from 'zod';
import {
  gitFullRefSchema,
  localBranchRefSchema,
  remoteBranchRefSchema,
} from '#runtimes/git/api/repository/states/refs';

const unresolvedTrackingSchema = z.object({ kind: z.literal('unresolved') });

const localCheckoutTrackingSchema = z.discriminatedUnion('kind', [
  z.object({
    kind: z.literal('resolved'),
    ref: localBranchRefSchema,
    oid: z.string().min(1),
    ahead: z.number().int().nonnegative(),
    behind: z.number().int().nonnegative(),
  }),
  unresolvedTrackingSchema,
]);

const remoteCheckoutTrackingSchema = z.discriminatedUnion('kind', [
  z.object({
    kind: z.literal('resolved'),
    ref: remoteBranchRefSchema,
    oid: z.string().min(1),
    ahead: z.number().int().nonnegative(),
    behind: z.number().int().nonnegative(),
  }),
  unresolvedTrackingSchema,
]);

export const checkoutTrackingSchema = z.union([
  localCheckoutTrackingSchema,
  remoteCheckoutTrackingSchema,
]);
export type CheckoutTracking = z.infer<typeof checkoutTrackingSchema>;

export const checkoutUpstreamSchema = z.discriminatedUnion('kind', [
  z.object({ kind: z.literal('none') }),
  z.object({
    kind: z.literal('local'),
    mergeRef: localBranchRefSchema,
    tracking: localCheckoutTrackingSchema,
  }),
  z.object({
    kind: z.literal('remote'),
    remote: z.string().min(1),
    mergeRef: gitFullRefSchema,
    tracking: remoteCheckoutTrackingSchema,
  }),
]);
export type CheckoutUpstream = z.infer<typeof checkoutUpstreamSchema>;

export const checkoutHeadStateSchema = z.discriminatedUnion('kind', [
  z.object({
    kind: z.literal('branch'),
    ref: localBranchRefSchema,
    oid: z.string(),
    upstream: checkoutUpstreamSchema,
  }),
  z.object({ kind: z.literal('detached'), shortHash: z.string(), oid: z.string() }),
  z.object({
    kind: z.literal('unborn'),
    ref: localBranchRefSchema,
    upstream: checkoutUpstreamSchema,
  }),
]);

export type CheckoutHeadState = z.infer<typeof checkoutHeadStateSchema>;
