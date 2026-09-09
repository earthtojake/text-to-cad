import { definePluginCapability } from '@emdash/shared/plugins';
import z from 'zod';
import type { PluginFs } from '#primitives/plugin-fs/api';

export type TrustContext = {
  workspacePath: string;
};

export type ITrustBehavior = {
  trustWorkspace(fs: PluginFs, ctx: TrustContext): Promise<void>;
};

export const trustCapability = definePluginCapability<ITrustBehavior>()(
  'trust',
  z.discriminatedUnion('kind', [
    z.object({
      kind: z.literal('supported'),
    }),
    z.object({
      kind: z.literal('none'),
    }),
  ]),
  { kind: 'none' }
);
