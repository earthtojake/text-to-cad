import { z } from 'zod';
import { gitRemoteSchema } from './refs';

export const gitRemotesStateSchema = z.object({ remotes: z.array(gitRemoteSchema) });
export type GitRemotesState = z.infer<typeof gitRemotesStateSchema>;
