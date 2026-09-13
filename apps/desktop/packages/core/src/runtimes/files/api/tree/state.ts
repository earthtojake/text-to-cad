import { z } from 'zod';
import { hostAbsolutePathSchema, portableRelativePathSchema } from '#primitives/path/api';

export const fileEntryKindSchema = z.enum(['file', 'directory', 'symlink']);
export const symlinkTargetKindSchema = z.enum([
  'file',
  'directory',
  'other',
  'missing',
  'outside-root',
]);

export const fileEntrySchema = z.object({
  path: portableRelativePathSchema,
  name: z.string(),
  parentPath: portableRelativePathSchema.nullable(),
  kind: fileEntryKindSchema,
  childrenLoaded: z.boolean(),
  children: z.array(portableRelativePathSchema),
  hasChildren: z.boolean().optional(),
  etag: z.string().optional(),
  size: z.number().int().nonnegative().optional(),
  mtimeMs: z.number().optional(),
  symlinkTarget: z.string().nullable().optional(),
  symlinkTargetKind: symlinkTargetKindSchema.optional(),
});

export const fileTreeModelSchema = z
  .object({
    root: hostAbsolutePathSchema,
    entries: z.record(z.string(), fileEntrySchema),
  })
  .superRefine((model, context) => {
    const root = model.entries[''];
    if (!root || root.kind !== 'directory' || root.parentPath !== null || root.path !== '') {
      context.addIssue({
        code: 'custom',
        path: ['entries', ''],
        message: 'The root entry must be a directory at the empty path',
      });
    }

    for (const [entryPath, entry] of Object.entries(model.entries)) {
      if (entry.path !== entryPath) {
        context.addIssue({
          code: 'custom',
          path: ['entries', entryPath, 'path'],
          message: 'Entry path must match its record key',
        });
      }
      if (!entry.childrenLoaded && entry.children.length > 0) {
        context.addIssue({
          code: 'custom',
          path: ['entries', entryPath, 'children'],
          message: 'An unloaded entry cannot contain children',
        });
      }
      if (!isExpandableFileEntry(entry) && (entry.childrenLoaded || entry.children.length > 0)) {
        context.addIssue({
          code: 'custom',
          path: ['entries', entryPath, 'childrenLoaded'],
          message: 'Only directories and in-root directory symlinks can load children',
        });
      }
      if (entry.kind === 'symlink' && entry.symlinkTargetKind === undefined) {
        context.addIssue({
          code: 'custom',
          path: ['entries', entryPath, 'symlinkTargetKind'],
          message: 'A symlink entry must describe its target kind',
        });
      }
      if (entry.kind !== 'symlink' && entry.symlinkTargetKind !== undefined) {
        context.addIssue({
          code: 'custom',
          path: ['entries', entryPath, 'symlinkTargetKind'],
          message: 'Only symlink entries can describe a symlink target kind',
        });
      }
      if (new Set(entry.children).size !== entry.children.length) {
        context.addIssue({
          code: 'custom',
          path: ['entries', entryPath, 'children'],
          message: 'An entry cannot contain the same child more than once',
        });
      }
      for (const childPath of entry.children) {
        if (model.entries[childPath]?.parentPath !== entryPath) {
          context.addIssue({
            code: 'custom',
            path: ['entries', entryPath, 'children'],
            message: 'Every child must exist and point back to its parent',
          });
        }
      }
      if (entryPath !== '') {
        const parent = entry.parentPath === null ? undefined : model.entries[entry.parentPath];
        if (!parent?.children.some((childPath) => childPath === entryPath)) {
          context.addIssue({
            code: 'custom',
            path: ['entries', entryPath, 'parentPath'],
            message: 'Every non-root entry must be listed by an existing parent',
          });
        }
      }
    }
  });

export type FileEntryKind = z.infer<typeof fileEntryKindSchema>;
export type SymlinkTargetKind = z.infer<typeof symlinkTargetKindSchema>;
export type FileEntry = z.infer<typeof fileEntrySchema>;
export type FileTreeModel = z.infer<typeof fileTreeModelSchema>;

export function isExpandableFileEntry(
  entry: Pick<FileEntry, 'kind' | 'symlinkTargetKind'>
): boolean {
  return (
    entry.kind === 'directory' ||
    (entry.kind === 'symlink' && entry.symlinkTargetKind === 'directory')
  );
}

export function isOpenableFileEntry(entry: Pick<FileEntry, 'kind' | 'symlinkTargetKind'>): boolean {
  return entry.kind === 'file' || (entry.kind === 'symlink' && entry.symlinkTargetKind === 'file');
}
