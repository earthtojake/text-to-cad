import {
  defineContract,
  downloadFile,
  fallible,
  liveJob,
  liveModel,
  liveState,
  mutation,
} from '@emdash/wire/rpc';
import { z } from 'zod';
import { gitFileContentStateSchema } from '#runtimes/git/api/checkout/states/content';
import { checkoutHeadStateSchema } from '#runtimes/git/api/checkout/states/head';
import { checkoutStatusStateSchema } from '#runtimes/git/api/checkout/states/status';
import {
  commitErrorSchema,
  downloadErrorSchema,
  gitCommandErrorSchema,
  pullErrorSchema,
  pushErrorSchema,
} from '#runtimes/git/api/errors';
import { transferProgressSchema } from '#runtimes/git/api/schemas';
import { checkoutSelectorSchema } from '#runtimes/git/api/selectors';
import { gitFileContentKeySchema } from './file-content-key';
import {
  blameResultSchema,
  commitFileSchema,
  commitOptionsSchema,
  commitSchema,
  downloadMetaSchema,
  gitChangeSchema,
  gitFilePathSchema,
  gitLogOptionsSchema,
  gitLogResultSchema,
  normalizedDiffTargetSchema,
  pullJobInputSchema,
  publishJobInputSchema,
  pushJobInputSchema,
} from './schemas';

export const gitCheckoutContract = defineContract({
  model: liveModel({
    key: checkoutSelectorSchema,
    states: {
      status: liveState({ data: checkoutStatusStateSchema }),
      head: liveState({ data: checkoutHeadStateSchema }),
    },
    mutations: {
      stage: mutation({
        input: z.object({ paths: z.array(gitFilePathSchema) }),
        data: z.void(),
        error: gitCommandErrorSchema,
      }),
      unstage: mutation({
        input: z.object({ paths: z.array(gitFilePathSchema) }),
        data: z.void(),
        error: gitCommandErrorSchema,
      }),
      stageAll: mutation({ input: z.object({}), data: z.void(), error: gitCommandErrorSchema }),
      unstageAll: mutation({ input: z.object({}), data: z.void(), error: gitCommandErrorSchema }),
      revert: mutation({
        input: z.object({ paths: z.array(gitFilePathSchema) }),
        data: z.void(),
        error: gitCommandErrorSchema,
      }),
      revertAll: mutation({ input: z.object({}), data: z.void(), error: gitCommandErrorSchema }),
      commit: mutation({
        input: z.object({ message: z.string(), options: commitOptionsSchema.optional() }),
        data: z.object({ hash: z.string() }),
        error: commitErrorSchema,
      }),
    },
  }),

  content: liveModel({
    key: gitFileContentKeySchema,
    states: {
      content: liveState({ data: gitFileContentStateSchema }),
    },
    mutations: {},
  }),

  getChangedFiles: fallible({
    input: checkoutSelectorSchema.extend({ target: normalizedDiffTargetSchema }),
    data: z.object({ files: z.array(gitChangeSchema) }),
    error: gitCommandErrorSchema,
  }),
  getFile: fallible({
    input: gitFileContentKeySchema,
    data: z.object({ content: z.string().nullable() }),
    error: gitCommandErrorSchema,
  }),
  download: downloadFile({
    input: gitFileContentKeySchema,
    meta: downloadMetaSchema,
    error: downloadErrorSchema,
  }),
  getLog: fallible({
    input: checkoutSelectorSchema.extend({ options: gitLogOptionsSchema.optional() }),
    data: gitLogResultSchema,
    error: gitCommandErrorSchema,
  }),
  getCommit: fallible({
    input: checkoutSelectorSchema.extend({ hash: z.string() }),
    data: z.object({ commit: commitSchema.nullable() }),
    error: gitCommandErrorSchema,
  }),
  getCommitFiles: fallible({
    input: checkoutSelectorSchema.extend({ hash: z.string() }),
    data: z.object({ files: z.array(commitFileSchema) }),
    error: gitCommandErrorSchema,
  }),
  blame: fallible({
    input: checkoutSelectorSchema.extend({
      path: gitFilePathSchema,
      ref: z.string().optional(),
    }),
    data: blameResultSchema,
    error: gitCommandErrorSchema,
  }),

  push: liveJob({
    input: pushJobInputSchema,
    progress: transferProgressSchema,
    result: z.object({ output: z.string() }),
    error: pushErrorSchema,
  }),
  publish: liveJob({
    input: publishJobInputSchema,
    progress: transferProgressSchema,
    result: z.object({ output: z.string() }),
    error: pushErrorSchema,
  }),
  pull: liveJob({
    input: pullJobInputSchema,
    progress: transferProgressSchema,
    result: z.object({ output: z.string() }),
    error: pullErrorSchema,
  }),
});

export type GitCheckoutContract = typeof gitCheckoutContract;
