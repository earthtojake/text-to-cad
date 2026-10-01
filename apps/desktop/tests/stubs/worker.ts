/**
 * Stands in for Vite's `?worker` imports under vitest.
 *
 * `monaco.ts` imports Monaco's five workers as `…?worker`, which is a Vite
 * build feature: the plugin compiles the module and hands back a constructor.
 * Vitest runs without that plugin, so the import is unresolvable and every
 * test that reaches `monaco.ts` — even one that only wants `languageFor` —
 * fails to load.
 *
 * Aliased in `vitest.config.ts`. Nothing calls it: `setupMonaco` is not run in
 * a jsdom test, because there is no canvas for Monaco to attach to.
 */
export default class StubWorker {
  postMessage(): void {}
  terminate(): void {}
  addEventListener(): void {}
  removeEventListener(): void {}
}
