import { z } from 'zod';

export const rawServerEntrySchema = z.record(z.string(), z.unknown());

export const credentialKeySchema = z.object({
  key: z.string(),
  required: z.boolean(),
});

export const mcpCatalogEntrySchema = z.object({
  key: z.string(),
  name: z.string(),
  description: z.string(),
  docsUrl: z.string(),
  defaultConfig: rawServerEntrySchema,
  credentialKeys: z.array(credentialKeySchema),
  _meta: z.record(z.string(), z.unknown()).optional(),
});

export const mcpServerSchema = z.object({
  name: z.string(),
  transport: z.enum(['stdio', 'http']),
  command: z.string().optional(),
  args: z.array(z.string()).optional(),
  url: z.string().optional(),
  headers: z.record(z.string(), z.string()).optional(),
  env: z.record(z.string(), z.string()).optional(),
  enabled: z.boolean().optional(),
  cwd: z.string().optional(),
  timeout: z.number().optional(),
  oauth: z.union([z.record(z.string(), z.unknown()), z.literal(false)]).optional(),
  providers: z.array(z.string()),
});

export type McpServer = z.infer<typeof mcpServerSchema>;
export type RawServerEntry = z.infer<typeof rawServerEntrySchema>;
export type CredentialKey = z.infer<typeof credentialKeySchema>;
export type McpCatalogEntry = z.infer<typeof mcpCatalogEntrySchema>;

export interface McpLoadAllResponse {
  installed: McpServer[];
  catalog: McpCatalogEntry[];
}

export interface McpProvidersResponse {
  id: string;
  name: string;
  installed: boolean;
}
