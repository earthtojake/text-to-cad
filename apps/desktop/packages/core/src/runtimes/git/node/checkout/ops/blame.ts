import { ok, type Result } from '@emdash/shared';
import { type BlameHunk, type BlameResult, type GitCommandError } from '#runtimes/git/api';
import { commandFailed } from '#runtimes/git/node/exec/errors';
import type { BoundExec } from '#services/exec/api';

const GROUP_HEADER_RE = /^([0-9a-f]{40}) (\d+) (\d+)(?: (\d+))?$/;

type CommitMeta = {
  author: string;
  authorEmail: string;
  /** Author date as epoch milliseconds. */
  date: number;
  summary: string;
};

export async function blame(
  exec: BoundExec,
  filePath: string,
  ref?: string
): Promise<Result<BlameResult, GitCommandError>> {
  try {
    const { stdout } = await exec.exec([
      'blame',
      '--porcelain',
      ...(ref ? [ref] : []),
      '--',
      filePath,
    ]);
    return ok(parseBlamePorcelain(stdout));
  } catch (error) {
    return commandFailed(error);
  }
}

/**
 * Parses `git blame --porcelain` output. Porcelain emits full commit metadata
 * only the first time a commit appears; later groups repeat just the header,
 * so metadata is cached per oid.
 */
export function parseBlamePorcelain(output: string): BlameResult {
  const metaByOid = new Map<string, CommitMeta>();
  const hunks: BlameHunk[] = [];
  let currentOid: string | null = null;
  let groupStartLine = 0;
  let groupLineCount = 0;

  const flush = () => {
    if (currentOid === null || groupLineCount === 0) return;
    const meta = metaByOid.get(currentOid);
    hunks.push({
      oid: currentOid,
      author: meta?.author ?? '',
      authorEmail: meta?.authorEmail ?? '',
      date: meta?.date ?? 0,
      summary: meta?.summary ?? '',
      startLine: groupStartLine,
      lineCount: groupLineCount,
    });
    currentOid = null;
    groupLineCount = 0;
  };

  for (const line of output.split('\n')) {
    const header = GROUP_HEADER_RE.exec(line);
    if (header) {
      const oid = header[1]!;
      const finalLine = Number.parseInt(header[3]!, 10);
      const numLines = header[4] !== undefined ? Number.parseInt(header[4], 10) : undefined;
      if (numLines !== undefined) {
        flush();
        currentOid = oid;
        groupStartLine = finalLine;
        groupLineCount = numLines;
        if (!metaByOid.has(oid)) {
          metaByOid.set(oid, { author: '', authorEmail: '', date: 0, summary: '' });
        }
      }
      continue;
    }

    if (currentOid === null || line.startsWith('\t')) continue;

    const meta = metaByOid.get(currentOid);
    if (!meta) continue;
    if (line.startsWith('author ')) meta.author = line.slice('author '.length);
    else if (line.startsWith('author-mail ')) {
      meta.authorEmail = line.slice('author-mail '.length).replace(/^<|>$/g, '');
    } else if (line.startsWith('author-time ')) {
      const epoch = Number.parseInt(line.slice('author-time '.length), 10);
      if (Number.isFinite(epoch)) meta.date = epoch * 1000;
    } else if (line.startsWith('summary ')) meta.summary = line.slice('summary '.length);
  }
  flush();

  return { hunks };
}
