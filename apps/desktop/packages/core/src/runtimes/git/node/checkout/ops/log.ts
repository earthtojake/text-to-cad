import type { PortableRelativePath } from '#primitives/path/api';
import {
  toRefString,
  type Commit,
  type CommitFile,
  type GitLogOptions,
  type GitLogResult,
} from '#runtimes/git/api';
import { checkoutFailures } from '#runtimes/git/node/checkout/errors';
import type { BoundExec } from '#services/exec/api';
import { mapGitChangeStatus } from './status';

export type Numstat = Map<string, { additions: number; deletions: number }>;

const FIELD_SEP = '\x1f';
const RECORD_SEP = '\x1e';
// `%at` is the author date as unix epoch seconds; the wire carries epoch ms.
export const LOG_FORMAT = `%H${FIELD_SEP}%P${FIELD_SEP}%s${FIELD_SEP}%b${FIELD_SEP}%an${FIELD_SEP}%at${FIELD_SEP}%D${RECORD_SEP}`;

export async function getLog(exec: BoundExec, options: GitLogOptions = {}): Promise<GitLogResult> {
  const maxCount = typeof options.limit === 'number' ? Math.max(1, Math.floor(options.limit)) : 50;
  const skip = typeof options.skip === 'number' ? Math.max(0, Math.floor(options.skip)) : 0;
  const head = options.head ? toRefString(options.head) : 'HEAD';
  const range = options.base ? `${toRefString(options.base)}..${head}` : head;
  const [{ stdout }, { stdout: countOutput }, remoteReachable] = await Promise.all([
    exec.exec([
      'log',
      `--max-count=${maxCount}`,
      `--skip=${skip}`,
      '--decorate=full',
      `--format=${LOG_FORMAT}`,
      range,
      '--',
    ]),
    exec.exec(['rev-list', '--count', range, '--']),
    getRemoteReachableCommits(exec),
  ]);
  return {
    commits: parseLogRecords(stdout, remoteReachable),
    totalCount: Number.parseInt(countOutput.trim(), 10) || 0,
  };
}

export async function getCommit(exec: BoundExec, hash: string): Promise<Commit | null> {
  try {
    const { stdout } = await exec.exec([
      'log',
      '--max-count=1',
      '--decorate=full',
      `--format=${LOG_FORMAT}`,
      hash,
      '--',
    ]);
    const remoteReachable = await getRemoteReachableCommits(exec);
    return parseLogRecords(stdout, remoteReachable)[0] ?? null;
  } catch (error) {
    if (!checkoutFailures.isUnknownRevision(error)) throw error;
    return null;
  }
}

export async function getCommitFiles(
  exec: BoundExec,
  hash: string,
  toPortablePath: (filePath: string) => PortableRelativePath
): Promise<CommitFile[]> {
  const [numstatRes, nameStatusRes] = await Promise.all([
    exec.exec(['diff-tree', '--root', '--no-commit-id', '--numstat', '-r', hash]),
    exec.exec(['diff-tree', '--root', '--no-commit-id', '--name-status', '-r', hash]),
  ]);
  const numstat = parseNumstat(numstatRes.stdout);
  const statusByPath = new Map<string, ReturnType<typeof mapGitChangeStatus>>();
  for (const line of nameStatusRes.stdout.trim().split('\n').filter(Boolean)) {
    const [code = '', ...parts] = line.split('\t');
    const filePath = parts[parts.length - 1];
    if (filePath) statusByPath.set(filePath, mapGitChangeStatus(code));
  }
  return [...numstat.entries()].map(([filePath, stat]) => ({
    path: toPortablePath(filePath),
    status: statusByPath.get(filePath) ?? 'modified',
    additions: stat.additions,
    deletions: stat.deletions,
  }));
}

export function parseLogRecords(stdout: string, remoteReachable: Set<string>): Commit[] {
  return stdout
    .split(RECORD_SEP)
    .map((record) => record.replace(/^\n/, '').trimEnd())
    .filter(Boolean)
    .map((record) => {
      const [
        hash = '',
        parents = '',
        subject = '',
        body = '',
        author = '',
        date = '',
        decorations = '',
      ] = record.split(FIELD_SEP);
      return {
        hash,
        parents: parents ? parents.split(' ').filter(Boolean) : [],
        subject,
        body: body.trim(),
        author,
        date: (Number.parseInt(date, 10) || 0) * 1000,
        isPushed: remoteReachable.has(hash),
        tags: parseDecoratedTags(decorations),
      };
    });
}

export function parseDecoratedTags(decorations: string): string[] {
  return decorations
    .split(',')
    .map((decoration) => decoration.trim())
    .filter((decoration) => decoration.startsWith('tag: '))
    .map((decoration) => decoration.slice('tag: '.length).replace(/^refs\/tags\//, ''))
    .filter(Boolean);
}

export function parseNumstat(stdout: string): Numstat {
  const map: Numstat = new Map();
  for (const line of stdout.trim().split('\n').filter(Boolean)) {
    const [addStr, delStr, ...pathParts] = line.split('\t');
    const filePath = pathParts.join('\t');
    if (!filePath) continue;
    const current = map.get(filePath) ?? { additions: 0, deletions: 0 };
    current.additions += addStr === '-' ? 0 : Number.parseInt(addStr ?? '0', 10) || 0;
    current.deletions += delStr === '-' ? 0 : Number.parseInt(delStr ?? '0', 10) || 0;
    map.set(filePath, current);
  }
  return map;
}

async function getRemoteReachableCommits(exec: BoundExec): Promise<Set<string>> {
  const { stdout } = await exec.exec(['rev-list', '--remotes', '--max-count=10000']);
  return new Set(
    stdout
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean)
  );
}
