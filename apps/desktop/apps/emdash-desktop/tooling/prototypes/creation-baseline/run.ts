/**
 * PROTOTYPE — baseline timing of the real createWorktree pipeline (throwaway).
 *
 * Answers .scratch/workspace-activation-speed/issues/05-instrumentation-baseline.md:
 * per-stage baseline numbers for the CURRENT pipeline (inspect → fetch →
 * add-worktree → verify → copy-preserved-files), by invoking the production
 * `executeCreateWorktree` directly. pushBranch is always false — no remote writes.
 *
 * Run from the repo root:
 *   pnpm exec tsx --tsconfig packages/core/tsconfig.json \
 *     apps/emdash-desktop/tooling/prototypes/creation-baseline/run.ts [--runs 2]
 *
 * Creates scratch worktrees next to each target repo and cleans them up (worktree
 * remove + branch -D + prune).
 */
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { executeCreateWorktree } from '../../../../../packages/core/src/runtimes/workspace-registry/node/create-worktree';
import { createRegistryGitContext } from '../../../../../packages/core/src/runtimes/workspace-registry/node/git-context';

interface Target {
  label: string;
  repo: string;
  baseRef: string;
  preservePatterns: string[];
}

const PRESERVE = [
  '.env',
  '.env.keys',
  '.env.local',
  '.env.*.local',
  '.envrc',
  'docker-compose.override.yml',
];

const targets: Target[] = [
  {
    label: 'emdash (~10k tracked files)',
    repo: '/Users/davidkonopka/Documents/repos/emdash',
    baseRef: 'origin/main',
    preservePatterns: PRESERVE,
  },
  {
    label: 'vscode (~16.5k tracked files)',
    repo: '/Users/davidkonopka/Documents/repos/vscode',
    baseRef: 'origin/main',
    preservePatterns: PRESERVE,
  },
];

function git(repo: string, args: string[]): string {
  return execFileSync('git', ['-C', repo, ...args], { encoding: 'utf8' });
}

function fmt(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(2)}s` : `${ms.toFixed(0)}ms`;
}

async function timeOne(target: Target, runIdx: number): Promise<Record<string, number>> {
  const tag = `${Date.now()}-${runIdx}`;
  const branch = `cow-proto/baseline-${tag}`;
  const worktreePath = `${target.repo}-baseline-scratch/${tag}`;
  fs.mkdirSync(path.dirname(worktreePath), { recursive: true });

  const stageStarts: Array<{ stage: string; at: number }> = [];
  const t0 = performance.now();
  const result = await executeCreateWorktree({
    git: createRegistryGitContext(),
    repositoryPath: target.repo,
    worktreePath,
    branch,
    baseRef: target.baseRef,
    onStage: (stage) => stageStarts.push({ stage, at: performance.now() }),
  });
  const tEnd = performance.now();

  const durations: Record<string, number> = {};
  for (let i = 0; i < stageStarts.length; i++) {
    const end = i + 1 < stageStarts.length ? stageStarts[i + 1].at : tEnd;
    durations[stageStarts[i].stage] = end - stageStarts[i].at;
  }
  durations.TOTAL = tEnd - t0;

  if (result.status !== 'succeeded') {
    console.log(`  RUN FAILED at stage ${result.stage}: ${result.message}`);
  } else {
    // Cleanup this run's worktree and branch.
    try {
      git(target.repo, ['worktree', 'remove', '--force', result.finalPath]);
      git(target.repo, ['branch', '-D', branch]);
    } catch (e) {
      console.log(`  cleanup warning: ${(e as Error).message}`);
    }
  }
  return durations;
}

const runsFlagIdx = process.argv.indexOf('--runs');
const runs = runsFlagIdx >= 0 ? Number(process.argv[runsFlagIdx + 1]) : 2;

for (const target of targets) {
  console.log(`\n################ ${target.label} ################`);
  try {
    git(target.repo, ['rev-parse', '--verify', `${target.baseRef}^{commit}`]);
  } catch {
    console.log(`  SKIP: ${target.baseRef} does not resolve in ${target.repo}`);
    continue;
  }
  for (let i = 0; i < runs; i++) {
    console.log(`--- run ${i + 1} (${i === 0 ? 'cold-ish' : 'warm'}) ---`);
    const d = await timeOne(target, i);
    for (const [stage, ms] of Object.entries(d)) {
      console.log(`  ${stage.padEnd(24)} ${fmt(ms).padStart(9)}`);
    }
  }
  git(target.repo, ['worktree', 'prune']);
  fs.rmSync(`${target.repo}-baseline-scratch`, { recursive: true, force: true });
}
console.log('\nDone; scratch cleaned up.');
