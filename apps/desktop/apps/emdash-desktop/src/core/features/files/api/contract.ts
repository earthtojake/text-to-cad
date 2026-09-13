import { resourceUriSchema } from '@emdash/core/primitives/path/api';
import {
  exclusionPatternsSchema,
  filesContract,
  MAX_FILE_UPLOAD_BYTES,
  readFileOptionsSchema,
} from '@emdash/core/runtimes/files/api';
import { diffModeSchema, gitObjectRefSchema } from '@emdash/core/runtimes/git/api';
import { defineContract, downloadFile, liveModel, liveState, uploadFile } from '@emdash/wire/rpc';
import { z } from 'zod';
import {
  runtimeFallibleMutations,
  runtimeFallibleProcedure,
  runtimeResolveErrorUnion,
} from '@core/primitives/desktop-runtime/api/fallible-contract';

// Every key in this domain is a ResourceUri — a serialized HostFileRef carrying
// the host and the absolute path (spec §2/§8). Workspace→root resolution happens
// at the renderer edge; no workspaceId reaches the wire.
const uriKeySchema = z.object({ uri: resourceUriSchema });

// The wire form of the GitRef vocabulary (`DiffMode | GitObjectRef`, spec §6),
// composed from the git runtime's schemas rather than duplicated here.
const gitRefSchema = z.union([diffModeSchema, gitObjectRefSchema]);

// Disk content is live-watched and writable; a git source serves the file's
// read-only snapshot at that ref through the git runtime (spec §6/§8). The
// checkout root is resolved at the seam and never part of the key.
const contentSourceSchema = z.union([z.literal('disk'), z.object({ ref: gitRefSchema })]);

const contentKeySchema = z.object({
  uri: resourceUriSchema,
  source: contentSourceSchema,
});

// `sessionId` keeps two consumers of the same root (e.g. two windows) from
// sharing one server-side tree resource and its expansion state.
const treeKeySchema = z.object({
  root: resourceUriSchema,
  sessionId: z.string(),
  exclusions: exclusionPatternsSchema,
});

const readOptionsShape = { options: readFileOptionsSchema.optional() };

// Two-endpoint mutations address source and target as URIs on the same host.
const fromToUriKeySchema = z.object({ from: resourceUriSchema, to: resourceUriSchema });

const filesFsContract = defineContract({
  exists: runtimeFallibleProcedure(uriKeySchema, filesContract.fs.exists.output),
  realPath: runtimeFallibleProcedure(uriKeySchema, filesContract.fs.realPath.output),
  readText: runtimeFallibleProcedure(
    uriKeySchema.extend(readOptionsShape),
    filesContract.fs.readText.output
  ),
  readBytes: downloadFile({
    input: uriKeySchema.extend(readOptionsShape),
    meta: filesContract.fs.readBytes.meta,
    error: runtimeResolveErrorUnion(filesContract.fs.readBytes.error),
  }),
  upload: uploadFile({
    input: uriKeySchema.extend({ overwrite: z.boolean().optional() }),
    maxSize: MAX_FILE_UPLOAD_BYTES,
    result: filesContract.fs.upload.result,
    error: runtimeResolveErrorUnion(filesContract.fs.upload.error),
  }),
  createFile: runtimeFallibleProcedure(uriKeySchema, filesContract.fs.createFile.output),
  createDirectory: runtimeFallibleProcedure(uriKeySchema, filesContract.fs.createDirectory.output),
  rename: runtimeFallibleProcedure(fromToUriKeySchema, filesContract.fs.rename.output),
  move: runtimeFallibleProcedure(fromToUriKeySchema, filesContract.fs.move.output),
  copy: runtimeFallibleProcedure(fromToUriKeySchema, filesContract.fs.copy.output),
  delete: runtimeFallibleProcedure(
    uriKeySchema.extend({ recursive: z.boolean().optional() }),
    filesContract.fs.delete.output
  ),
});

export const filesDomain = 'files' as const;

export const filesWireContract = defineContract({
  fs: filesFsContract,
  tree: defineContract({
    model: liveModel({
      key: treeKeySchema,
      states: {
        tree: liveState({ data: filesContract.tree.model.states.tree.dataSchema }),
      },
      mutations: runtimeFallibleMutations(filesContract.tree.model.mutations),
    }),
  }),
  content: liveModel({
    key: contentKeySchema,
    states: {
      content: liveState({ data: filesContract.content.states.content.dataSchema }),
    },
    mutations: runtimeFallibleMutations(filesContract.content.mutations),
  }),
});

export type FilesWireContract = typeof filesWireContract;
export type FilesContentKey = z.infer<typeof filesWireContract.content.keySchema>;
export type FilesContentModel = z.infer<typeof filesWireContract.content.states.content.dataSchema>;
export type FilesTreeKey = z.infer<typeof filesWireContract.tree.model.keySchema>;
export type FilesTreeModel = z.infer<typeof filesWireContract.tree.model.states.tree.dataSchema>;
