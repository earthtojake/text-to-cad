import { z } from 'zod';
import { hostAbsolutePathSchema } from '#primitives/path/api';

/** A host-local, reconnect-stable path supplied by the client. */
export const gitPathSelectorSchema = z.object({ path: hostAbsolutePathSchema });
export type GitPathSelector = z.infer<typeof gitPathSelectorSchema>;

export const repositorySelectorSchema = z.object({ repository: hostAbsolutePathSchema });
export type RepositorySelector = z.infer<typeof repositorySelectorSchema>;

export const checkoutSelectorSchema = z.object({ checkout: hostAbsolutePathSchema });
export type CheckoutSelector = z.infer<typeof checkoutSelectorSchema>;

export const gitSelectorSchema = z.union([repositorySelectorSchema, checkoutSelectorSchema]);
export type GitSelector = z.infer<typeof gitSelectorSchema>;
