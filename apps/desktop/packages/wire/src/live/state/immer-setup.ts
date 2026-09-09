import { enablePatches, Immer, type Patch } from 'immer';

const configuredImmer = createConfiguredImmer();

// These exports must come from the configured instance. Besides containing the
// configuration in Wire, this makes patch initialization a data dependency of
// every consumer instead of a discardable module-evaluation side effect.
const applyPatches: typeof import('immer').applyPatches =
  configuredImmer.applyPatches.bind(configuredImmer);
const produce: typeof import('immer').produce = configuredImmer.produce;
const produceWithPatches: typeof import('immer').produceWithPatches =
  configuredImmer.produceWithPatches;

export { applyPatches, produce, produceWithPatches, type Patch };

// Structural declaration keeps this browser-reachable file free of node
// ambient types; the typeof guard already handles environments without it.
declare const process: { env: Record<string, string | undefined> } | undefined;

function createConfiguredImmer(): Immer {
  // Immer registers its RFC-6902 patch plugin at module scope. Run that
  // registration while constructing the instance whose methods we export.
  enablePatches();

  // Auto-freeze is a dev-only correctness tripwire: it turns out-of-band
  // mutations into an immediate TypeError. It is disabled in production
  // because Object.freeze is O(N).
  return new Immer({ autoFreeze: readNodeEnv() !== 'production' });
}

function readNodeEnv(): string | undefined {
  return typeof process !== 'undefined' ? process.env['NODE_ENV'] : undefined;
}
