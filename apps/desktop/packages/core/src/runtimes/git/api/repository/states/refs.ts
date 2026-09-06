import { z } from 'zod';

export const gitRemoteSchema = z.object({
  name: z.string(),
  url: z.string(),
});
export type GitRemote = z.infer<typeof gitRemoteSchema>;

export const gitLocalBranchRefSchema = z.object({
  type: z.literal('local'),
  branch: z.string(),
  remote: gitRemoteSchema.optional(),
});
export type GitLocalBranchRef = z.infer<typeof gitLocalBranchRefSchema>;

export const gitRemoteBranchRefSchema = z.object({
  type: z.literal('remote'),
  branch: z.string(),
  remote: gitRemoteSchema,
});
export type GitRemoteBranchRef = z.infer<typeof gitRemoteBranchRefSchema>;

export const gitBranchRefSchema = z.union([gitLocalBranchRefSchema, gitRemoteBranchRefSchema]);
export type GitBranchRef = z.infer<typeof gitBranchRefSchema>;

export const gitFullRefSchema = z
  .string()
  .regex(/^refs\/.+/)
  .brand<'GitFullRef'>();
export type GitFullRef = z.infer<typeof gitFullRefSchema>;

export const localBranchRefSchema = gitFullRefSchema
  .refine((ref) => /^refs\/heads\/.+/.test(ref))
  .brand<'LocalBranchRef'>();
export type LocalBranchRef = z.infer<typeof localBranchRefSchema>;

export const remoteBranchRefSchema = gitFullRefSchema
  .refine((ref) => /^refs\/remotes\/.+/.test(ref))
  .brand<'RemoteBranchRef'>();
export type RemoteBranchRef = z.infer<typeof remoteBranchRefSchema>;

export const tagRefSchema = gitFullRefSchema
  .refine((ref) => /^refs\/tags\/.+/.test(ref))
  .brand<'TagRef'>();
export type TagRef = z.infer<typeof tagRefSchema>;

const localBranchSchema = z.object({
  type: z.literal('local'),
  ref: localBranchRefSchema,
  remote: gitRemoteSchema.optional(),
  oid: z.string(),
  divergence: z.object({ ahead: z.number().int(), behind: z.number().int() }).optional(),
});
export type LocalBranch = z.infer<typeof localBranchSchema>;

const remoteBranchSchema = z.object({
  type: z.literal('remote'),
  ref: remoteBranchRefSchema,
  remote: gitRemoteSchema,
  oid: z.string(),
});
export type RemoteBranch = z.infer<typeof remoteBranchSchema>;

export const gitBranchSchema = z.union([localBranchSchema, remoteBranchSchema]);
export type GitBranch = z.infer<typeof gitBranchSchema>;

export const gitTagSchema = z.object({
  ref: tagRefSchema,
  oid: z.string(),
  message: z.string().optional(),
});
export type GitTag = z.infer<typeof gitTagSchema>;

export const gitRemoteHeadSchema = z.object({
  remote: z.string(),
  ref: remoteBranchRefSchema,
});
export type GitRemoteHead = z.infer<typeof gitRemoteHeadSchema>;

export const gitRefsStateSchema = z.object({
  branches: z.array(gitBranchSchema),
  tags: z.array(gitTagSchema),
  remoteHeads: z.array(gitRemoteHeadSchema),
});
export type GitRefsState = z.infer<typeof gitRefsStateSchema>;

export function shortName(ref: LocalBranchRef | TagRef): string {
  if (ref.startsWith('refs/heads/')) return ref.slice('refs/heads/'.length);
  return ref.slice('refs/tags/'.length);
}

export function branchNameOnRemote(ref: RemoteBranchRef, remote: GitRemote): string {
  const prefix = `refs/remotes/${remote.name}/`;
  if (!ref.startsWith(prefix)) {
    throw new Error(`Remote branch ref '${ref}' does not belong to remote '${remote.name}'`);
  }
  return ref.slice(prefix.length);
}

export function toBranchRef(branch: GitBranch): GitBranchRef {
  if (branch.type === 'local') {
    return {
      type: 'local',
      branch: shortName(branch.ref),
      ...(branch.remote ? { remote: branch.remote } : {}),
    };
  }
  return {
    type: 'remote',
    branch: branchNameOnRemote(branch.ref, branch.remote),
    remote: branch.remote,
  };
}
