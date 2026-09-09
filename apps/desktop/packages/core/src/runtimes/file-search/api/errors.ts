import { z } from 'zod';
import { hostAbsolutePathSchema } from '#primitives/path/api';

export const fileSearchRootUnavailableReasonSchema = z.enum([
  'not-found',
  'not-a-directory',
  'permission-denied',
  'invalid-path',
]);

const fileSearchRootUnavailableErrorSchema = z.object({
  type: z.literal('root-unavailable'),
  root: hostAbsolutePathSchema,
  reason: fileSearchRootUnavailableReasonSchema,
  message: z.string(),
});

const fileSearchRootNotRegisteredErrorSchema = z.object({
  type: z.literal('root-not-registered'),
  root: hostAbsolutePathSchema,
  message: z.string(),
});

const pathSearchIndexNotReadyErrorSchema = z.object({
  type: z.literal('index-not-ready'),
  root: hostAbsolutePathSchema,
  message: z.string(),
});

const fileSearchIoErrorSchema = z.object({
  type: z.literal('io'),
  root: hostAbsolutePathSchema,
  message: z.string(),
});

const contentSearchUnavailableErrorSchema = z.object({
  type: z.literal('content-search-unavailable'),
  message: z.string(),
});

export const fileSearchRegisterRootErrorSchema = z.discriminatedUnion('type', [
  fileSearchRootUnavailableErrorSchema,
  fileSearchIoErrorSchema,
]);

export const fileSearchUnregisterRootErrorSchema = fileSearchIoErrorSchema;

export const pathSearchErrorSchema = z.discriminatedUnion('type', [
  fileSearchRootNotRegisteredErrorSchema,
  fileSearchRootUnavailableErrorSchema,
  pathSearchIndexNotReadyErrorSchema,
  fileSearchIoErrorSchema,
]);

export const contentSearchErrorSchema = z.discriminatedUnion('type', [
  fileSearchRootNotRegisteredErrorSchema,
  fileSearchRootUnavailableErrorSchema,
  contentSearchUnavailableErrorSchema,
  fileSearchIoErrorSchema,
]);

export type FileSearchRootUnavailableReason = z.infer<typeof fileSearchRootUnavailableReasonSchema>;
export type FileSearchRegisterRootError = z.infer<typeof fileSearchRegisterRootErrorSchema>;
export type FileSearchUnregisterRootError = z.infer<typeof fileSearchUnregisterRootErrorSchema>;
export type PathSearchError = z.infer<typeof pathSearchErrorSchema>;
export type ContentSearchError = z.infer<typeof contentSearchErrorSchema>;
