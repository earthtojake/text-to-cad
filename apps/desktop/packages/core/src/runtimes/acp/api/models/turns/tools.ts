import { z } from 'zod';

export const toolStatusSchema = z.enum(['running', 'done', 'error']);
export type ToolStatus = z.infer<typeof toolStatusSchema>;

export const toolCallGroupKindSchema = z.enum(['read-batch']);
export type ToolCallGroupKind = z.infer<typeof toolCallGroupKindSchema>;
