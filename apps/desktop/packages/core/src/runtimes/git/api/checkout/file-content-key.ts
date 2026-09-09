import { z } from 'zod';
import { checkoutSelectorSchema } from '#runtimes/git/api/selectors';
import { gitFilePathSchema, gitFileSourceSchema } from './schemas';

export const boundGitFileContentKeySchema = z.object({
  path: gitFilePathSchema,
  source: gitFileSourceSchema,
});
export type BoundGitFileContentKey = z.infer<typeof boundGitFileContentKeySchema>;

export const gitFileContentKeySchema = checkoutSelectorSchema.extend(
  boundGitFileContentKeySchema.shape
);
export type GitFileContentKey = z.infer<typeof gitFileContentKeySchema>;
