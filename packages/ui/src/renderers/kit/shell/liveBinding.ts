import type { PromptReference, ResourceRef } from '@hardcore/core/prompt';
import type { JsonValue } from '../../../file-viewer/types.js';
import { normalizeViewSettings } from '@hardcore/core/common/viewSettings.js';
import { mergeViewerDisplaySettings } from '../view-settings/viewerDisplaySettings.js';

// The live command surface: what an app-owned tool (an agent, a test) may ask of
// the viewport that is actually mounted. The base commands mean the same thing
// for every renderer; a renderer ADDS commands of its own by name and DECLINES
// the known host commands that make no sense for it, with the sentence the
// caller is shown. Nothing is ever a silent no-op.

export interface LiveCameraSnapshot {
  position: [number, number, number];
  target: [number, number, number];
  up: [number, number, number];
  zoom?: number;
  projection?: 'orthographic' | 'perspective';
  focalLength?: number;
  orthographicHalfHeight?: number;
  modelKey?: string;
  sceneScaleMode?: string;
  coordinateSystem?: string;
}
export interface LiveViewState {
  resource: ResourceRef;
  revision: string;
  active: boolean;
  loading: boolean;
  selection: readonly PromptReference[];
  camera: LiveCameraSnapshot | null;
  /** Canonical sparse grouped View configuration. */
  display: { [key: string]: JsonValue };
  renderMode: 'inspect' | 'render';
}
export interface LiveViewController<State extends LiveViewState = LiveViewState> {
  /** Pure snapshots only. After unmount this returns the last view, active:false. */
  readState(): State;
  setCamera(snapshot: LiveCameraSnapshot): Promise<State>;
  resetCamera(): Promise<State>;
  setDisplaySettings(patch: { [key: string]: JsonValue }): Promise<State>;
  setRenderMode(enabled: boolean): Promise<State>;
  /** This returns a frozen image only; the host owns its transport and destination. */
  capture(): Promise<Blob>;
}
export interface LiveViewBinding<Controller = LiveViewController> {
  /** Bind the mounted view only. Cleanup may retain readState() as an inactive snapshot. */
  bind(controller: Controller): () => void;
}
/** What the mounted renderer answers with. Extra commands are own properties, found by name. */
export interface LiveViewRuntime<State extends LiveViewState = LiveViewState> {
  readState(): Omit<State, 'active'>;
  setCamera(snapshot: LiveCameraSnapshot): void;
  resetCamera(): void;
  setDisplaySettings(patch: { [key: string]: JsonValue }): void;
  setRenderMode(enabled: boolean): void;
  capture(): Promise<Blob>;
}
export interface LiveBindingOptions {
  settle?: () => Promise<void>;
  /** Commands this renderer adds: `runtime[name](...args)` runs as one admitted mutation. */
  commands?: readonly string[];
  /** Host commands this renderer has no meaning for, each with the error its caller reads. */
  declined?: Readonly<Record<string, string>>;
}

/** Commands hosts send beyond the base set. Every renderer implements or declines each one. */
export const HOST_LIVE_COMMANDS = Object.freeze(['select', 'clearSelection'] as const);

const settleFrame = () => new Promise<void>(resolve => requestAnimationFrame(() => resolve()));
const scopeKey = (state: { resource: ResourceRef; revision: string }) => JSON.stringify([state.resource, state.revision]);

/** Mounted-view adapter. It never retains a scene after detach. */
export function attachLiveBinding<State extends LiveViewState, Controller extends LiveViewController<State>>(
  binding: LiveViewBinding<Controller>, readRuntime: () => LiveViewRuntime<State>,
  { settle = settleFrame, commands = [], declined = {} }: LiveBindingOptions = {}): () => void {
  for (const name of HOST_LIVE_COMMANDS) {
    if (commands.includes(name) === Object.hasOwn(declined, name)) {
      throw new Error(`A renderer's live binding must either implement or decline the host command "${name}".`);
    }
  }
  let active = true;
  let departed: State | null = null;
  const readState = (): State => structuredClone(departed ?? ({ ...readRuntime().readState(), active } as State));
  const admit = () => {
    if (!active) throw new Error('Show the model tab before controlling its viewer.');
    const runtime = readRuntime();
    const state = runtime.readState();
    if (state.loading) throw new Error('Wait for the displayed model revision to finish loading.');
    return { runtime, scope: scopeKey(state) };
  };
  const checkScope = (scope: string) => {
    if (!active) throw new Error('The model tab closed while its viewer command was running.');
    if (scopeKey(readRuntime().readState()) !== scope) throw new Error('The displayed model revision changed while its viewer command was running.');
  };
  const mutate = async (apply: (runtime: LiveViewRuntime<State>) => void,
    committed?: (state: State) => boolean): Promise<State> => {
    const { runtime, scope } = admit();
    apply(runtime);
    const deadline = Date.now() + 10_000;
    // A mode switch can suspend while the Render chunk loads. The first RAF
    // may precede its React commit, so observe the actual destination state.
    do {
      await settle();
      checkScope(scope);
      const state = readState();
      if (!committed || committed(state)) return state;
    } while (Date.now() < deadline);
    throw new Error('The viewer did not finish applying this command.');
  };
  const controller: LiveViewController<State> & Record<string, unknown> = {
    readState,
    setCamera: snapshot => mutate(runtime => runtime.setCamera(snapshot)),
    resetCamera: () => mutate(runtime => runtime.resetCamera()),
    setDisplaySettings: async patch => {
      const normalized = normalizeViewSettings(patch);
      const canonicalPatch = Object.hasOwn(patch, 'mode') ? normalized
        : Object.fromEntries(Object.entries(normalized).filter(([key]) => key !== 'mode'));
      const containsPatch = (actual: unknown, expected: unknown): boolean => {
        if (!expected || typeof expected !== 'object' || Array.isArray(expected)) {
          return JSON.stringify(actual) === JSON.stringify(expected);
        }
        return Boolean(actual && typeof actual === 'object') && Object.entries(expected).every(
          ([key, value]) => containsPatch((actual as Record<string, unknown>)[key], value));
      };
      let expectedDisplay: ReturnType<typeof mergeViewerDisplaySettings>;
      return mutate(runtime => {
        expectedDisplay = mergeViewerDisplaySettings(runtime.readState().display, canonicalPatch);
        runtime.setDisplaySettings(canonicalPatch as { [key: string]: JsonValue });
      }, state => containsPatch(state.display, expectedDisplay));
    },
    setRenderMode: enabled => mutate(runtime => runtime.setRenderMode(enabled),
      state => state.renderMode === (enabled ? 'render' : 'inspect')),
    async capture() {
      const { runtime, scope } = admit();
      const pending = runtime.capture();
      const blob = await pending;
      checkScope(scope);
      return blob;
    },
  };
  for (const name of commands) {
    if (name in controller) throw new Error(`The live command "${name}" is already part of every renderer's base set.`);
    controller[name] = (...args: unknown[]) => mutate(runtime => {
      const command = (runtime as unknown as Record<string, unknown>)[name];
      if (typeof command !== 'function') throw new Error(`This renderer declared the live command "${name}" but its mounted view does not answer it.`);
      command.apply(runtime, args);
    });
  }
  for (const [name, reason] of Object.entries(declined)) {
    if (name in controller) throw new Error(`The live command "${name}" is implemented and cannot also be declined.`);
    controller[name] = () => Promise.reject(new Error(reason));
  }
  const release = binding.bind(controller as unknown as Controller);
  return () => {
    if (!active) return;
    departed = { ...readState(), active: false };
    active = false;
    // Drop the component closure: retained inactive snapshots own no scene.
    readRuntime = () => { throw new Error('This viewer is inactive.'); };
    release();
  };
}
