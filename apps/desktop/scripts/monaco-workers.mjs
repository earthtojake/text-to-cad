/**
 * Monaco's language worker managers name their own workers:
 *
 *   createWorker: () => new Worker(new URL('ts.worker.js', import.meta.url), …)
 *
 * and Vite bundles every `new Worker(new URL(…))` it sees. The app already
 * bundles the same four workers through `?worker` imports
 * (src/renderer/features/explorer/renderers/code/editor/setup.ts), and its
 * `MonacoEnvironment.getWorker` is the one Monaco calls: `getWorker` in
 * monaco-editor/esm/vs/internal/common/workers.js returns whatever
 * `getWorker` answers and only reaches `createWorker` when there is no
 * `MonacoEnvironment.getWorker` at all. So `createWorker` is dead code here —
 * but Vite still bundled each worker twice, TypeScript's (the largest module in
 * the renderer) included, a second Rollup graph held in memory beside the
 * first. The output was byte-identical and deduplicated; the cost was build
 * time and peak memory.
 *
 * This replaces that dead constructor with a throw, so each worker is bundled
 * once. If Monaco changes the shape, the build fails here rather than quietly
 * going back to bundling twice.
 */
const WORKER_MANAGER = /[\\/]monaco-editor[\\/]esm[\\/]vs[\\/]languages[\\/]features[\\/][^\\/]+[\\/]workerManager\.js$/;
const CONSTRUCTOR = /new Worker\(new URL\((['"])[\w.]+\.worker\.js\1, import\.meta\.url\), \{ type: "module" \}\)/g;

/** @returns {import('vite').Plugin} */
export function monacoWorkersOncePlugin() {
  return {
    name: "text-to-cad-monaco-workers-once",
    enforce: "pre",
    apply: "build",
    transform: {
      filter: { id: WORKER_MANAGER },
      handler(code, id) {
        let replaced = 0;
        const out = code.replace(CONSTRUCTOR, () => {
          replaced += 1;
          return '(() => { throw new Error("MonacoEnvironment.getWorker supplies Monaco\'s workers"); })()';
        });
        if (replaced !== 1) {
          this.error(`expected one worker constructor in ${id}, found ${replaced}: review scripts/monaco-workers.mjs`);
        }
        return { code: out, map: null };
      },
    },
  };
}
