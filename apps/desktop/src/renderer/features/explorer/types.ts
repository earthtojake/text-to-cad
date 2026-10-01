/**
 * The IPC answers the explorer's components pass around, named locally.
 *
 * Everything here is inferred from the contract's zod schemas rather than
 * restated: a second declaration of "what a text file read looks like" is a
 * second thing to keep in step with `src/shared/ipc/explorer.ts`.
 */
import type { z } from "zod";

import type { TextFileSchema, BinaryFileSchema } from "@shared/ipc/explorer";

export type { DirEntry, FileStat } from "@shared/ipc/explorer";
export type { ChangedFile, FileDiff, GitStatus, ProjectGitInfo, Worktree } from "@shared/ipc/git";

export type TextFileResult = z.infer<typeof TextFileSchema>;
export type BinaryFileResult = z.infer<typeof BinaryFileSchema>;
