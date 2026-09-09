import { randomUUID } from "node:crypto";
import { constants } from "node:fs";
import fs from "node:fs/promises";
import path from "node:path";

import { FsError, toRelative } from "./fs";

/** Source is chosen by main's native dialog, never supplied by the renderer. */
export async function addProjectFile(root: string, source: string): Promise<{ path: string }> {
  const extension = path.extname(source);
  if (!(await fs.stat(source)).isFile()) throw new FsError("Choose a file, not a folder.");
  const realRoot = await fs.realpath(root);
  const directory = realRoot;
  const temporary = path.join(directory, `.file-import-${randomUUID()}`);
  const stem = path.basename(source, extension);
  try {
    await fs.copyFile(source, temporary, constants.COPYFILE_EXCL);
    for (let suffix = 1; suffix <= 1000; suffix++) {
      const name = `${stem}${suffix === 1 ? "" : ` (${suffix})`}${extension}`;
      const destination = path.join(directory, name);
      try {
        // Publish complete bytes atomically, without replacing an existing file.
        await fs.link(temporary, destination);
        return { path: toRelative(realRoot, destination) };
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code !== "EEXIST") throw error;
      }
    }
    throw new FsError("Too many files have this name. Rename the file and try again.");
  } finally {
    await fs.unlink(temporary).catch(() => {});
  }
}
