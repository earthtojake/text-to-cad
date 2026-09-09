import { defineContract, fallible, liveJob } from '@emdash/wire/rpc';
import { z } from 'zod';
import {
  contentSearchErrorSchema,
  fileSearchRegisterRootErrorSchema,
  fileSearchUnregisterRootErrorSchema,
  pathSearchErrorSchema,
} from './errors';
import {
  contentSearchInputSchema,
  contentSearchProgressSchema,
  contentSearchResultSchema,
  fileSearchRootInputSchema,
  pathSearchInputSchema,
  pathSearchResultSchema,
} from './schemas';

export const fileSearchContract = defineContract({
  registerRoot: fallible({
    input: fileSearchRootInputSchema,
    data: z.void(),
    error: fileSearchRegisterRootErrorSchema,
  }),
  unregisterRoot: fallible({
    input: fileSearchRootInputSchema,
    data: z.void(),
    error: fileSearchUnregisterRootErrorSchema,
  }),
  searchPaths: fallible({
    input: pathSearchInputSchema,
    data: pathSearchResultSchema,
    error: pathSearchErrorSchema,
  }),
  searchContent: liveJob({
    input: contentSearchInputSchema,
    progress: contentSearchProgressSchema,
    result: contentSearchResultSchema,
    error: contentSearchErrorSchema,
  }),
});

export type FileSearchContract = typeof fileSearchContract;
