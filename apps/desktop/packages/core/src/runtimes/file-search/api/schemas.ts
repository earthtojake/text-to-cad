import { z } from 'zod';
import { hostAbsolutePathSchema, portableRelativePathSchema } from '#primitives/path/api';
import { pathEntryKinds } from './path-entry-kind';

export const PATH_SEARCH_MAX_LIMIT = 200;
export const PATH_SEARCH_DEFAULT_LIMIT = 20;
export const CONTENT_SEARCH_MAX_LIMIT = 10_000;
export const CONTENT_SEARCH_DEFAULT_LIMIT = 1_000;
export const CONTENT_SEARCH_MAX_PREVIEW_LENGTH = 16_384;
export const FILE_SEARCH_MAX_QUERY_LENGTH = 512;

export const fileSearchRootInputSchema = z.object({
  root: hostAbsolutePathSchema,
  exclusions: z.array(z.string()).optional(),
});

export const pathEntryKindSchema = z.enum(pathEntryKinds);

export const pathSearchInputSchema = fileSearchRootInputSchema.extend({
  query: z.string().max(FILE_SEARCH_MAX_QUERY_LENGTH),
  kinds: z
    .array(pathEntryKindSchema)
    .min(1)
    .max(pathEntryKindSchema.options.length)
    .refine((kinds) => new Set(kinds).size === kinds.length, {
      message: 'Path entry kinds must be unique',
    }),
  limit: z.number().int().positive().max(PATH_SEARCH_MAX_LIMIT).optional(),
});

export const pathSearchHitSchema = z.object({
  path: portableRelativePathSchema,
  kind: pathEntryKindSchema,
});

export const pathSearchResultSchema = z.object({
  hits: z.array(pathSearchHitSchema).max(PATH_SEARCH_MAX_LIMIT),
});

export const contentSearchInputSchema = fileSearchRootInputSchema.extend({
  query: z
    .string()
    .min(1)
    .max(FILE_SEARCH_MAX_QUERY_LENGTH)
    .refine((query) => !/[\0\r\n]/u.test(query), {
      message: 'Content search is line-oriented and cannot contain NUL or newline characters',
    }),
  under: portableRelativePathSchema.optional(),
  limit: z.number().int().positive().max(CONTENT_SEARCH_MAX_LIMIT).optional(),
});

export const contentSearchRangeSchema = z
  .object({
    startColumn: z.number().int().positive(),
    endColumn: z.number().int().positive(),
  })
  .refine(({ startColumn, endColumn }) => endColumn > startColumn, {
    message: 'endColumn must be greater than startColumn',
    path: ['endColumn'],
  });

export const contentSearchLocationSchema = z.object({
  sourceRange: contentSearchRangeSchema,
  previewRange: contentSearchRangeSchema,
});

export const contentSearchLineMatchSchema = z.object({
  lineNumber: z.number().int().positive(),
  previewText: z.string().max(CONTENT_SEARCH_MAX_PREVIEW_LENGTH),
  locations: z.array(contentSearchLocationSchema).min(1).max(CONTENT_SEARCH_MAX_LIMIT),
});

export const contentSearchFileResultSchema = z.object({
  path: portableRelativePathSchema,
  matches: z.array(contentSearchLineMatchSchema).min(1).max(CONTENT_SEARCH_MAX_LIMIT),
});

const contentSearchFilesSchema = z
  .array(contentSearchFileResultSchema)
  .max(CONTENT_SEARCH_MAX_LIMIT);

export const contentSearchProgressSchema = z.object({ files: contentSearchFilesSchema });

export const contentSearchResultSchema = z.object({
  files: contentSearchFilesSchema,
  complete: z.boolean(),
});

export type FileSearchRootInput = z.infer<typeof fileSearchRootInputSchema>;
export type PathEntryKind = z.infer<typeof pathEntryKindSchema>;
export type PathSearchInput = z.infer<typeof pathSearchInputSchema>;
export type PathSearchHit = z.infer<typeof pathSearchHitSchema>;
export type PathSearchResult = z.infer<typeof pathSearchResultSchema>;
export type ContentSearchInput = z.infer<typeof contentSearchInputSchema>;
export type ContentSearchRange = z.infer<typeof contentSearchRangeSchema>;
export type ContentSearchLocation = z.infer<typeof contentSearchLocationSchema>;
export type ContentSearchLineMatch = z.infer<typeof contentSearchLineMatchSchema>;
export type ContentSearchFileResult = z.infer<typeof contentSearchFileResultSchema>;
export type ContentSearchProgress = z.infer<typeof contentSearchProgressSchema>;
export type ContentSearchResult = z.infer<typeof contentSearchResultSchema>;
