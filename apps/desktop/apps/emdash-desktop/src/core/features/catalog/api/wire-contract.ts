import { mcpCatalogEntrySchema } from '@emdash/core/primitives/mcp/api';
import {
  catalogIndexSchema,
  catalogSkillSchema,
  skillInstallPayloadSchema,
} from '@emdash/core/primitives/skills/api';
import { defineContract, fallible } from '@emdash/wire/rpc';
import { z } from 'zod';

export const catalogErrorSchema = z.object({
  type: z.enum(['io', 'network', 'not-found', 'invalid-state']),
  message: z.string(),
  statusCode: z.number().int().optional(),
});

export const catalogVoidInputSchema = z.void().optional();

export const skillSearchInputSchema = z.object({
  query: z.string(),
});

export const skillIdInputSchema = z.object({
  skillId: z.string(),
});

export const mcpCatalogInputSchema = z
  .object({
    registryBaseUrl: z.url().optional(),
    search: z.string().optional(),
    featuredOnly: z.boolean().optional(),
  })
  .optional();

export const catalogDomain = 'catalog' as const;

export const catalogWireContract = defineContract({
  getSkillsCatalog: fallible({
    input: catalogVoidInputSchema,
    data: catalogIndexSchema,
    error: catalogErrorSchema,
  }),
  refreshSkillsCatalog: fallible({
    input: catalogVoidInputSchema,
    data: catalogIndexSchema,
    error: catalogErrorSchema,
  }),
  searchSkillSh: fallible({
    input: skillSearchInputSchema,
    data: z.array(catalogSkillSchema),
    error: catalogErrorSchema,
  }),
  resolveSkillInstall: fallible({
    input: skillIdInputSchema,
    data: skillInstallPayloadSchema,
    error: catalogErrorSchema,
  }),
  getSkillContent: fallible({
    input: skillIdInputSchema,
    data: catalogSkillSchema,
    error: catalogErrorSchema,
  }),
  getMcpCatalog: fallible({
    input: mcpCatalogInputSchema,
    data: z.array(mcpCatalogEntrySchema),
    error: catalogErrorSchema,
  }),
});

export type CatalogError = z.infer<typeof catalogErrorSchema>;
export type McpCatalogInput = z.infer<typeof mcpCatalogInputSchema>;
export type CatalogWireContract = typeof catalogWireContract;
