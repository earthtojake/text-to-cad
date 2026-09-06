import {
  gitFullRefSchema,
  localBranchRefSchema,
  remoteBranchRefSchema,
  shortName,
  type CheckoutHeadState,
  type CheckoutUpstream,
  type LocalBranchRef,
} from '#runtimes/git/api';
import { checkoutFailures } from '#runtimes/git/node/checkout/errors';
import type { BoundExec } from '#services/exec/api';

/** Throws when the path is not a git repository; callers keep the previous state. */
export async function computeHeadState(exec: BoundExec): Promise<CheckoutHeadState> {
  try {
    const { stdout } = await exec.exec(['symbolic-ref', 'HEAD']);
    const ref = localBranchRefSchema.parse(stdout.trim());
    const upstream = await computeUpstream(exec, ref);
    try {
      const { stdout: oid } = await exec.exec(['rev-parse', '--verify', 'HEAD']);
      return { kind: 'branch', ref, oid: oid.trim(), upstream };
    } catch (error) {
      if (!checkoutFailures.isUnbornHead(error)) throw error;
      return { kind: 'unborn', ref, upstream };
    }
  } catch (error) {
    if (!checkoutFailures.isDetachedHead(error)) throw error;
    const [short, oid] = await Promise.all([
      exec.exec(['rev-parse', '--short', 'HEAD']),
      exec.exec(['rev-parse', '--verify', 'HEAD']),
    ]);
    return { kind: 'detached', shortHash: short.stdout.trim(), oid: oid.stdout.trim() };
  }
}

async function computeUpstream(exec: BoundExec, ref: LocalBranchRef): Promise<CheckoutUpstream> {
  const branch = shortName(ref);
  let stdout: string;
  try {
    ({ stdout } = await exec.exec([
      'config',
      '-z',
      '--get-regexp',
      `^branch\\.${escapeConfigRegexp(branch)}\\.(remote|merge)$`,
    ]));
  } catch {
    return { kind: 'none' };
  }

  const prefix = `branch.${branch}.`;
  let remote: string | null = null;
  let mergeRef: string | null = null;
  for (const entry of stdout.split('\0')) {
    if (!entry) continue;
    const separator = entry.indexOf('\n');
    const key = separator === -1 ? entry : entry.slice(0, separator);
    const value = separator === -1 ? '' : entry.slice(separator + 1);
    if (!key.startsWith(prefix)) continue;
    const name = key.slice(prefix.length);
    if (name === 'remote') remote = value;
    if (name === 'merge') mergeRef = value;
  }
  if (!remote || !mergeRef) return { kind: 'none' };

  if (remote === '.') {
    const localMergeRef = localBranchRefSchema.parse(mergeRef);
    try {
      const [trackingRef, trackingOid, divergence] = await readTracking(exec);
      const [aheadRaw, behindRaw] = divergence.split(/\s+/u);
      return {
        kind: 'local',
        mergeRef: localMergeRef,
        tracking: {
          kind: 'resolved',
          ref: localBranchRefSchema.parse(trackingRef),
          oid: trackingOid,
          ahead: Number.parseInt(aheadRaw ?? '0', 10) || 0,
          behind: Number.parseInt(behindRaw ?? '0', 10) || 0,
        },
      };
    } catch {
      return { kind: 'local', mergeRef: localMergeRef, tracking: { kind: 'unresolved' } };
    }
  }

  const remoteMergeRef = gitFullRefSchema.parse(mergeRef);

  try {
    const [trackingRef, trackingOid, divergence] = await readTracking(exec);
    const [aheadRaw, behindRaw] = divergence.split(/\s+/u);
    return {
      kind: 'remote',
      remote,
      mergeRef: remoteMergeRef,
      tracking: {
        kind: 'resolved',
        ref: remoteBranchRefSchema.parse(trackingRef),
        oid: trackingOid,
        ahead: Number.parseInt(aheadRaw ?? '0', 10) || 0,
        behind: Number.parseInt(behindRaw ?? '0', 10) || 0,
      },
    };
  } catch {
    return {
      kind: 'remote',
      remote,
      mergeRef: remoteMergeRef,
      tracking: { kind: 'unresolved' },
    };
  }
}

async function readTracking(exec: BoundExec): Promise<[string, string, string]> {
  const [trackingRef, trackingOid, divergence] = await Promise.all([
    exec.exec(['rev-parse', '--symbolic-full-name', '@{upstream}']),
    exec.exec(['rev-parse', '--verify', '@{upstream}']),
    exec.exec(['rev-list', '--left-right', '--count', 'HEAD...@{upstream}']),
  ]);
  return [trackingRef.stdout.trim(), trackingOid.stdout.trim(), divergence.stdout.trim()];
}

/** Escapes ERE metacharacters so the branch name matches literally in --get-regexp. */
function escapeConfigRegexp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
