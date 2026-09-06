/**
 * PROTOTYPE — CoW worktree materialization benchmark (throwaway, do not ship).
 *
 * Answers .scratch/workspace-activation-speed/issues/01-cow-recipe-prototype.md:
 * does clone -> read-tree -> update-index --refresh -> reset --hard -> clean -fd
 * work end to end, and how does it compare to plain `git worktree add`?
 *
 * Run from the repo root:
 *   pnpm --dir apps/emdash-desktop exec tsx tooling/prototypes/cow-worktree/run.ts
 *
 * Flags:
 *   --repo <path>      source repo (default: this repo)
 *   --synthetic <n>    also run against a generated repo with n tracked files
 *   --keep             skip cleanup (inspect the scratch worktrees afterwards)
 *
 * Writes only to a scratch dir next to the source repo (same volume, required for
 * CoW) and to the repo's .git/worktrees + temporary cow-proto/* branches; all of it
 * is removed at the end unless --keep.
 */
import { execFileSync, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const isDarwin = process.platform === 'darwin';

interface Timing {
  label: string;
  ms: number;
  note?: string;
}

function run(cmd: string, args: string[], cwd: string, allowFail = false): string {
  const res = spawnSync(cmd, args, { cwd, encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 });
  if (res.status !== 0 && !allowFail) {
    throw new Error(`${cmd} ${args.join(' ')} failed (${res.status}):\n${res.stderr}`);
  }
  return res.stdout ?? '';
}

function timed(timings: Timing[], label: string, fn: () => string | void): string | void {
  const t0 = performance.now();
  const out = fn();
  timings.push({ label, ms: performance.now() - t0 });
  return out;
}

type CloneEngine = 'cp' | 'clonefile';

function cloneEntry(from: string, to: string, engine: CloneEngine): void {
  if (isDarwin && engine === 'clonefile') {
    // Kernel-recursive directory clone. Prototype shells to python3/ctypes; a real
    // implementation would use a tiny native binding or helper binary.
    const res = spawnSync('python3', [
      '-c',
      `import ctypes, sys
libc = ctypes.CDLL('/usr/lib/libSystem.dylib', use_errno=True)
rc = libc.clonefile(sys.argv[1].encode(), sys.argv[2].encode(), 0)
sys.exit(0 if rc == 0 else ctypes.get_errno())`,
      from,
      to,
    ]);
    if (res.status === 0) return;
    // Fall through to cp on any failure (EEXIST, ENOTSUP, dataless files, ...).
  }
  if (isDarwin) {
    execFileSync('cp', ['-c', '-R', from, to]);
  } else {
    execFileSync('cp', ['-a', '--reflink=auto', from, to]);
  }
}

function cloneTree(src: string, dst: string, engine: CloneEngine): void {
  // Clone every top-level entry except .git into the (already existing) worktree dir.
  for (const entry of fs.readdirSync(src)) {
    if (entry === '.git') continue;
    cloneEntry(path.join(src, entry), path.join(dst, entry), engine);
  }
}

function countEntries(dir: string): number {
  let n = 0;
  const stack = [dir];
  while (stack.length) {
    const d = stack.pop()!;
    for (const e of fs.readdirSync(d, { withFileTypes: true })) {
      n++;
      if (e.isDirectory()) stack.push(path.join(d, e.name));
    }
  }
  return n;
}

function fmt(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(2)}s` : `${ms.toFixed(0)}ms`;
}

function report(title: string, timings: Timing[]): void {
  console.log(`\n=== ${title} ===`);
  let total = 0;
  for (const t of timings) {
    total += t.ms;
    console.log(`  ${t.label.padEnd(46)} ${fmt(t.ms).padStart(9)}${t.note ? `  (${t.note})` : ''}`);
  }
  console.log(`  ${'TOTAL'.padEnd(46)} ${fmt(total).padStart(9)}`);
}

interface ScenarioResult {
  timings: Timing[];
  worktree: string;
  branch: string;
}

function baselineScenario(repo: string, scratch: string, tag: string): ScenarioResult {
  const timings: Timing[] = [];
  const branch = `cow-proto/${tag}-baseline`;
  const wt = path.join(scratch, `${tag}-baseline`);
  timed(timings, 'git worktree add (full checkout)', () => {
    run('git', ['worktree', 'add', '-b', branch, wt, 'HEAD'], repo);
  });
  timed(timings, 'git status (first)', () => run('git', ['status', '--porcelain'], wt));
  return { timings, worktree: wt, branch };
}

function cowScenario(
  repo: string,
  scratch: string,
  tag: string,
  variant: 'refresh' | 'copied-index',
  engine: CloneEngine
): ScenarioResult & { statusClean: boolean } {
  const timings: Timing[] = [];
  const branch = `cow-proto/${tag}-cow-${variant}`;
  const wt = path.join(scratch, `${tag}-cow-${variant}`);

  timed(timings, 'git worktree add --no-checkout', () => {
    run('git', ['worktree', 'add', '--no-checkout', '-b', branch, wt, 'HEAD'], repo);
  });
  timed(timings, `CoW-clone working tree (engine: ${engine})`, () => {
    cloneTree(repo, wt, engine);
  });

  if (variant === 'refresh') {
    timed(timings, 'git read-tree HEAD', () => run('git', ['read-tree', 'HEAD'], wt));
    timed(timings, 'git update-index --refresh (full re-hash)', () => {
      run('git', ['update-index', '--refresh', '-q'], wt, true);
    });
  } else {
    // Variant from research §4.4: reuse the source's index + core.checkStat=minimal
    // so mtime+size matching skips the content re-hash entirely.
    timed(timings, 'copy source index into worktree gitdir', () => {
      const gitdir = run('git', ['rev-parse', '--absolute-git-dir'], wt).trim();
      fs.copyFileSync(path.join(repo, '.git', 'index'), path.join(gitdir, 'index'));
    });
    timed(timings, 'git update-index --refresh (checkStat=minimal)', () => {
      run(
        'git',
        [
          '-c',
          'core.checkStat=minimal',
          '-c',
          'core.trustctime=false',
          'update-index',
          '--refresh',
          '-q',
        ],
        wt,
        true
      );
    });
  }

  timed(timings, 'git reset --hard HEAD', () => run('git', ['reset', '--hard', 'HEAD'], wt));
  timed(timings, 'git clean -fd (keeps ignored artifacts)', () => run('git', ['clean', '-fd'], wt));
  const status = timed(timings, 'git status (steady state)', () =>
    run('git', ['status', '--porcelain'], wt)
  ) as string;

  return { timings, worktree: wt, branch, statusClean: status.trim() === '' };
}

function verifyArtifacts(wt: string): void {
  const nm = path.join(wt, 'node_modules');
  if (!fs.existsSync(nm)) {
    console.log('  node_modules: NOT PRESENT (source had none?)');
    return;
  }
  const bin = ['tsx', 'oxlint', 'vitest'].find((b) => fs.existsSync(path.join(nm, '.bin', b)));
  if (bin) {
    const out = spawnSync(path.join(nm, '.bin', bin), ['--version'], {
      cwd: wt,
      encoding: 'utf8',
    });
    console.log(
      `  node_modules survived; ${bin} --version -> ${out.status === 0 ? out.stdout.trim() : `FAILED: ${out.stderr}`}`
    );
  } else {
    console.log('  node_modules survived (no known .bin to smoke-test)');
  }
}

function cleanup(repo: string, results: ScenarioResult[], scratch: string, keep: boolean): void {
  if (keep) {
    console.log(`\n--keep set; scratch left at ${scratch}`);
    return;
  }
  for (const r of results) {
    run('git', ['worktree', 'remove', '--force', r.worktree], repo, true);
    run('git', ['branch', '-D', r.branch], repo, true);
  }
  run('git', ['worktree', 'prune'], repo, true);
  fs.rmSync(scratch, { recursive: true, force: true });
  console.log('\nCleaned up scratch worktrees, branches, and metadata.');
}

function buildSyntheticRepo(root: string, nFiles: number): string {
  const repo = path.join(root, 'synthetic-repo');
  fs.mkdirSync(repo, { recursive: true });
  run('git', ['init', '-q'], repo);
  run('git', ['config', 'user.email', 'proto@example.com'], repo);
  run('git', ['config', 'user.name', 'cow-proto'], repo);
  const perDir = 200;
  for (let i = 0; i < nFiles; i++) {
    const dir = path.join(repo, 'src', `d${Math.floor(i / perDir)}`);
    if (i % perDir === 0) fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(path.join(dir, `f${i}.ts`), `export const v${i} = ${i};\n`);
  }
  fs.writeFileSync(path.join(repo, '.gitignore'), 'artifacts/\n');
  run('git', ['add', '-A'], repo);
  run('git', ['commit', '-q', '-m', 'synthetic'], repo);
  // Ignored artifact tree, ~nFiles/2 entries, stands in for node_modules.
  const art = path.join(repo, 'artifacts');
  for (let i = 0; i < nFiles / 2; i++) {
    const dir = path.join(art, `a${Math.floor(i / perDir)}`);
    if (i % perDir === 0) fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(path.join(dir, `b${i}.js`), `module.exports=${i};\n`);
  }
  return repo;
}

function runSuite(repo: string, label: string, keep: boolean): void {
  const tag = `${Date.now()}`;
  const scratch = `${repo}-cow-proto-scratch`;
  fs.mkdirSync(scratch, { recursive: true });
  console.log(`\n################ ${label} ################`);
  console.log(`repo: ${repo}`);
  console.log(`scratch (same volume): ${scratch}`);
  console.log(`tracked+untracked entries in source: ${countEntries(repo)}`);

  const results: ScenarioResult[] = [];
  try {
    const baseline = baselineScenario(repo, scratch, tag);
    results.push(baseline);
    report('BASELINE: git worktree add', baseline.timings);
    console.log('  (no node_modules/artifacts in this worktree — deps would need a full install)');

    const engine: CloneEngine = isDarwin ? 'clonefile' : 'cp';
    const cow = cowScenario(repo, scratch, tag, 'refresh', engine);
    results.push(cow);
    report('CoW RECIPE: clone + read-tree + refresh + reset + clean', cow.timings);
    console.log(`  git status clean after recipe: ${cow.statusClean ? 'YES' : 'NO — INVESTIGATE'}`);
    verifyArtifacts(cow.worktree);

    const cow2 = cowScenario(repo, scratch, tag, 'copied-index', engine);
    results.push(cow2);
    report('CoW VARIANT: copied index + core.checkStat=minimal', cow2.timings);
    console.log(
      `  git status clean after recipe: ${cow2.statusClean ? 'YES' : 'NO — INVESTIGATE'}`
    );
    verifyArtifacts(cow2.worktree);

    // HYBRID: normal full checkout for tracked files, kernel clone for ignored
    // artifact dirs only — no index tricks, no clean step needed.
    const hyTimings: Timing[] = [];
    const hyBranch = `cow-proto/${tag}-hybrid`;
    const hyWt = path.join(scratch, `${tag}-hybrid`);
    timed(hyTimings, 'git worktree add (full checkout)', () => {
      run('git', ['worktree', 'add', '-b', hyBranch, hyWt, 'HEAD'], repo);
    });
    timed(hyTimings, 'clone ignored artifact dirs (node_modules etc.)', () => {
      for (const entry of ['node_modules', 'artifacts']) {
        const from = path.join(repo, entry);
        if (fs.existsSync(from)) cloneEntry(from, path.join(hyWt, entry), engine);
      }
    });
    const hyStatus = timed(hyTimings, 'git status', () =>
      run('git', ['status', '--porcelain'], hyWt)
    ) as string;
    results.push({ timings: hyTimings, worktree: hyWt, branch: hyBranch });
    report('HYBRID: git worktree add + clone ignored artifacts only', hyTimings);
    console.log(`  git status clean: ${hyStatus.trim() === '' ? 'YES' : 'NO — INVESTIGATE'}`);
    verifyArtifacts(hyWt);
  } finally {
    cleanup(repo, results, scratch, keep);
  }
}

const args = process.argv.slice(2);
const flag = (name: string): string | undefined => {
  const i = args.indexOf(`--${name}`);
  return i >= 0 ? args[i + 1] : undefined;
};
const keep = args.includes('--keep');
const defaultRepo = path.resolve(fileURLToPath(import.meta.url), '../../../../../..');
const repo = path.resolve(flag('repo') ?? defaultRepo);

runSuite(repo, 'REAL REPO', keep);

const synthetic = flag('synthetic');
if (synthetic) {
  const root = fs.mkdtempSync(path.join(path.dirname(repo), 'cow-proto-synth-'));
  try {
    const synthRepo = buildSyntheticRepo(root, Number(synthetic));
    runSuite(synthRepo, `SYNTHETIC REPO (${synthetic} tracked files)`, keep);
  } finally {
    if (!keep) fs.rmSync(root, { recursive: true, force: true });
  }
}
