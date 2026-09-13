import { gitContract } from '@emdash/core/runtimes/git/api';
import type { Result } from '@emdash/shared';
import {
  defineContract,
  downloadFile,
  liveJob,
  liveModel,
  liveState,
  procedure,
  type MutationDef,
} from '@emdash/wire/rpc';
import { z } from 'zod';
import {
  projectAttachmentErrorSchema,
  type ProjectAttachmentError,
} from '@core/features/projects/api';
import {
  runtimeFallibleMutations,
  runtimeFallibleProcedure,
  runtimeResolveErrorUnion,
} from '@core/primitives/desktop-runtime/api/fallible-contract';

const projectKeySchema = z.object({ projectId: z.string() });
const workspaceKeySchema = z.object({ workspaceId: z.string() });

const repository = gitContract.repository;
const checkout = gitContract.checkout;

const projectAttachmentFailureSchema = z.object({
  success: z.literal(false),
  error: projectAttachmentErrorSchema,
});

type AttachmentFallibleResult<OutputSchema extends z.ZodTypeAny> =
  z.output<OutputSchema> extends Result<infer Data, infer Error>
    ? Result<Data, Error | ProjectAttachmentError>
    : never;

function attachmentFallibleProcedure<
  InputSchema extends z.ZodTypeAny,
  OutputSchema extends z.ZodTypeAny,
>(input: InputSchema, output: OutputSchema) {
  return procedure({
    input,
    output: z.union([output, projectAttachmentFailureSchema]) as z.ZodType<
      AttachmentFallibleResult<OutputSchema>
    >,
  });
}

function attachmentErrorUnion<ErrorSchema extends z.ZodTypeAny>(error: ErrorSchema) {
  return z.union([error, projectAttachmentErrorSchema]);
}

type AttachmentFallibleMutation<Definition extends MutationDef> =
  Definition extends MutationDef<infer InputSchema, infer DataSchema, infer ErrorSchema>
    ? MutationDef<InputSchema, DataSchema, ReturnType<typeof attachmentErrorUnion<ErrorSchema>>>
    : never;

function attachmentFallibleMutations<Definitions extends Record<string, MutationDef>>(
  definitions: Definitions
): { [Name in keyof Definitions]: AttachmentFallibleMutation<Definitions[Name]> } {
  return Object.fromEntries(
    Object.entries(definitions).map(([name, definition]) => [
      name,
      {
        ...definition,
        error: attachmentErrorUnion(definition.error),
      },
    ])
  ) as { [Name in keyof Definitions]: AttachmentFallibleMutation<Definitions[Name]> };
}

const sourceControlRepositoryContract = defineContract({
  model: liveModel({
    key: projectKeySchema,
    states: {
      refs: liveState({ data: repository.model.states.refs.dataSchema }),
      remotes: liveState({ data: repository.model.states.remotes.dataSchema }),
    },
    mutations: attachmentFallibleMutations(repository.model.mutations),
  }),
  listWorktrees: attachmentFallibleProcedure(projectKeySchema, repository.listWorktrees.output),
  getDefaultBranch: attachmentFallibleProcedure(
    repository.getDefaultBranch.input.omit({ repository: true }).extend(projectKeySchema.shape),
    repository.getDefaultBranch.output
  ),
  fetch: liveJob({
    input: repository.fetch.input.omit({ repository: true }).extend(projectKeySchema.shape),
    progress: repository.fetch.progress,
    result: repository.fetch.result,
    error: attachmentErrorUnion(repository.fetch.error),
  }),
  fetchPrForReview: liveJob({
    input: repository.fetchPrForReview.input
      .omit({ repository: true })
      .extend(projectKeySchema.shape),
    progress: repository.fetchPrForReview.progress,
    result: repository.fetchPrForReview.result,
    error: attachmentErrorUnion(repository.fetchPrForReview.error),
  }),
});

const sourceControlCheckoutContract = defineContract({
  model: liveModel({
    key: workspaceKeySchema,
    states: {
      status: liveState({ data: checkout.model.states.status.dataSchema }),
      head: liveState({ data: checkout.model.states.head.dataSchema }),
    },
    mutations: runtimeFallibleMutations(checkout.model.mutations),
  }),
  getChangedFiles: runtimeFallibleProcedure(
    checkout.getChangedFiles.input.omit({ checkout: true }).extend(workspaceKeySchema.shape),
    checkout.getChangedFiles.output
  ),
  getFile: runtimeFallibleProcedure(
    checkout.getFile.input.omit({ checkout: true }).extend(workspaceKeySchema.shape),
    checkout.getFile.output
  ),
  download: downloadFile({
    input: checkout.download.input.omit({ checkout: true }).extend(workspaceKeySchema.shape),
    meta: checkout.download.meta,
    error: runtimeResolveErrorUnion(checkout.download.error),
  }),
  getLog: runtimeFallibleProcedure(
    checkout.getLog.input.omit({ checkout: true }).extend(workspaceKeySchema.shape),
    checkout.getLog.output
  ),
  getCommit: runtimeFallibleProcedure(
    checkout.getCommit.input.omit({ checkout: true }).extend(workspaceKeySchema.shape),
    checkout.getCommit.output
  ),
  getCommitFiles: runtimeFallibleProcedure(
    checkout.getCommitFiles.input.omit({ checkout: true }).extend(workspaceKeySchema.shape),
    checkout.getCommitFiles.output
  ),
  blame: runtimeFallibleProcedure(
    checkout.blame.input.omit({ checkout: true }).extend(workspaceKeySchema.shape),
    checkout.blame.output
  ),
  push: liveJob({
    input: checkout.push.input.omit({ checkout: true }).extend(workspaceKeySchema.shape),
    progress: checkout.push.progress,
    result: checkout.push.result,
    error: runtimeResolveErrorUnion(checkout.push.error),
  }),
  publish: liveJob({
    input: checkout.publish.input.omit({ checkout: true }).extend(workspaceKeySchema.shape),
    progress: checkout.publish.progress,
    result: checkout.publish.result,
    error: runtimeResolveErrorUnion(checkout.publish.error),
  }),
  pull: liveJob({
    input: checkout.pull.input.omit({ checkout: true }).extend(workspaceKeySchema.shape),
    progress: checkout.pull.progress,
    result: checkout.pull.result,
    error: runtimeResolveErrorUnion(checkout.pull.error),
  }),
});

export const sourceControlDomain = 'sourceControl' as const;

export const sourceControlContract = defineContract({
  repository: sourceControlRepositoryContract,
  checkout: sourceControlCheckoutContract,
});

export type SourceControlContract = typeof sourceControlContract;
