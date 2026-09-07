/**
 * `dialogs.*`: the native choosers Settings needs.
 *
 * `projects.add` already opens a folder chooser, but it adds what it finds as a
 * project. Four settings rows — the default project folder, the worktree root,
 * a notification sound, a Python interpreter — want the path and nothing else,
 * and a chooser that answers with a path is the smallest thing that serves all
 * four.
 *
 * Cancelling answers `null`, not an error: a cancelled dialog is an ordinary
 * outcome.
 */
import { z } from "zod";

import { invoke } from "./define";

/** A file-type filter, in Electron's shape. */
const FileFilterSchema = z.object({
  name: z.string(),
  /** Extensions without the dot; `["*"]` for everything. */
  extensions: z.array(z.string()),
});

const Chosen = z.object({ path: z.string() }).nullable();

export const dialogsContract = {
  dialogs: {
    chooseDirectory: invoke(
      z.object({
        title: z.string().optional(),
        /** Where the chooser opens. Ignored if it no longer exists. */
        defaultPath: z.string().optional(),
      }),
      Chosen,
    ),
    chooseFile: invoke(
      z.object({
        title: z.string().optional(),
        defaultPath: z.string().optional(),
        filters: z.array(FileFilterSchema).optional(),
      }),
      Chosen,
    ),
  },
} as const;
