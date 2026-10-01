import type { PromptReference, ResourceRef } from '@text-to-cad/core/prompt';
import type { JsonValue } from '../../../file-viewer/types.js';
import { normalizeViewSettings, resolveViewSettings } from '@text-to-cad/core/common/viewSettings.js';
import { mergeViewerDisplaySettings } from '../view-settings/viewerDisplaySettings.js';
import { cameraReadsBack } from './liveReadback.js';

// The live command surface: what an app-owned tool (an agent, a test) may ask of
// the viewport that is actually mounted. The base commands mean the same thing
// for every renderer; a renderer ADDS commands of its own by name and DECLINES
// the known host commands that make no sense for it, with the sentence the
// caller is shown. Nothing is ever a silent no-op.
//
// A mutating command replies only once its effect is on screen, never on the call returning:
// a settled frame at least, and where the command has a committed predicate, until that holds.
// The predicate compares against what the runtime records, not the request. Each command's
// predicate (setCamera's position-and-target readback, Preview's orbit, resetCamera's rest,
// setRenderMode's projection, a renderer's own select) is stated once in packages/ui/docs/cad-renderer.md
// under "Live commands". A renderer whose reset is instant (a flat drawing) returns no predicate
// and a settled frame is its answer. The wait is bounded at ten seconds, then it throws "The
// viewer did not finish applying this command." rather than answer with a state the command did
// not produce. A command sent from outside a React event renders on a later task, which is why
// one frame is not the answer.

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
  /**
   * A picture for a library card, once the view has settled — its whole file loaded and drawn —
   * of the model framed whole from the default direction at `size`, whatever the camera on
   * screen, the panels over it or the window's size. Nothing on screen changes.
   */
  thumbnail(size: { width: number; height: number }): Promise<Blob>;
}
export interface LiveViewBinding<Controller = LiveViewController> {
  /** Bind the mounted view only. Cleanup may retain readState() as an inactive snapshot. */
  bind(controller: Controller): () => void;
}
/** What the mounted renderer answers with. Extra commands are own properties, found by name. */
export interface LiveViewRuntime<State extends LiveViewState = LiveViewState> {
  readState(): Omit<State, 'active'>;
  /**
   * May hand back the predicate that says the camera it APPLIED is on screen: a shell derives
   * the applied camera from the request (view settings, scene scale), so the request itself
   * is not what reads back. Without one, the binding waits for the request to read back.
   */
  setCamera(snapshot: LiveCameraSnapshot): void | ((state: State) => boolean);
  /** May hand back the predicate that says the camera has come to rest (an eased reset has not, a frame later). */
  resetCamera(): void | ((state: State) => boolean);
  setDisplaySettings(patch: { [key: string]: JsonValue }): void;
  setRenderMode(enabled: boolean): void;
  /** False while the camera is under way; a capture waits for it, so the image shows the camera the state names. */
  atRest?(): boolean;
  capture(): Promise<Blob>;
  /** The card's picture, drawn off to the side of the view (`kit/viewport/thumbnail.js`). */
  thumbnail(size: { width: number; height: number }): Promise<Blob>;
}
export interface LiveBindingOptions {
  settle?: () => Promise<void>;
  /**
   * Resolves once the view shows its whole file, drawn: at once when it already does, else on the
   * renderer's own render that makes it so, never on a timer (`useWhenSettled`); it rejects when
   * the view goes first. A thumbnail waits for it. Default: at once.
   */
  ready?: () => Promise<void>;
  /** Commands this renderer adds: `runtime[name](...args)` runs as one admitted mutation. */
  commands?: readonly string[];
  /** Host commands this renderer has no meaning for, each with the error its caller reads. */
  declined?: Readonly<Record<string, string>>;
}

/** Commands hosts send beyond the base set. Every renderer implements or declines each one. */
export const HOST_LIVE_COMMANDS = Object.freeze(['select', 'clearSelection'] as const);

const settleFrame = () => new Promise<void>(resolve => requestAnimationFrame(() => resolve()));
const LIVE_COMMAND_TIMEOUT_MS = 10_000;
const UNFINISHED = 'The viewer did not finish applying this command.';
const scopeKey = (state: { resource: ResourceRef; revision: string }) => JSON.stringify([state.resource, state.revision]);

/** Mounted-view adapter. It never retains a scene after detach. */
export function attachLiveBinding<State extends LiveViewState, Controller extends LiveViewController<State>>(
  binding: LiveViewBinding<Controller>, readRuntime: () => LiveViewRuntime<State>,
  { settle = settleFrame, ready = () => Promise.resolve(), commands = [], declined = {} }: LiveBindingOptions = {}): () => void {
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
  // The wait is bounded at ten seconds of wall clock, then it throws rather than returning a
  // state the command did not produce. The bound is a timer raced against each frame, not a
  // check after one: a frame that never comes (a hidden window, a paused rAF) must still end it.
  const settleBefore = (deadline: number) => new Promise<void>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(UNFINISHED)), Math.max(0, deadline - Date.now()));
    settle().then(() => { clearTimeout(timer); resolve(); }, error => { clearTimeout(timer); reject(error); });
  });
  const untilCommitted = async (scope: string, committed: () => boolean) => {
    const deadline = Date.now() + LIVE_COMMAND_TIMEOUT_MS;
    do {
      await settleBefore(deadline);
      checkScope(scope);
      if (committed()) return;
    } while (Date.now() < deadline);
    throw new Error(UNFINISHED);
  };
  const mutate = async (apply: (runtime: LiveViewRuntime<State>) => void | ((state: State) => boolean),
    committed?: (state: State) => boolean): Promise<State> => {
    const { runtime, scope } = admit();
    // A command may hand back the predicate that says when ITS effect is on screen.
    committed = apply(runtime) || committed;
    // A mode switch can suspend while the Render chunk loads. The first RAF
    // may precede its React commit, so observe the actual destination state.
    let state!: State;
    await untilCommitted(scope, () => {
      state = readState();
      return !committed || committed(state);
    });
    return state;
  };
  const controller: LiveViewController<State> & Record<string, unknown> = {
    readState,
    setCamera: snapshot => mutate(runtime => runtime.setCamera(snapshot), state => cameraReadsBack(state.camera, snapshot)),
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
    // Committed once the VIEWPORT shows the mode, not once the store names it: the store flips at
    // once, the camera takes the mode's projection a frame or more later, and the reply (or a
    // capture right after it) must not describe the mode it left.
    setRenderMode: enabled => mutate(runtime => runtime.setRenderMode(enabled),
      state => state.renderMode === (enabled ? 'render' : 'inspect')
        && (!state.camera?.projection || state.camera.projection === resolveViewSettings(state.display).camera.projection)),
    async capture() {
      const { runtime, scope } = admit();
      // An image taken mid-move would show a camera the state (read right after) does not name.
      if (runtime.atRest && !runtime.atRest()) await untilCommitted(scope, () => runtime.atRest!());
      const pending = runtime.capture();
      const blob = await pending;
      checkScope(scope);
      return blob;
    },
    async thumbnail(size) {
      if (!active) throw new Error('Show the model tab before controlling its viewer.');
      await ready();
      const { runtime, scope } = admit();
      const blob = await runtime.thumbnail(size);
      checkScope(scope);
      return blob;
    },
  };
  for (const name of commands) {
    if (name in controller) throw new Error(`The live command "${name}" is already part of every renderer's base set.`);
    // Clearing is committed once nothing is selected; `select` (and any renderer command)
    // returns its own predicate.
    controller[name] = (...args: unknown[]) => mutate(runtime => {
      const command = (runtime as unknown as Record<string, unknown>)[name];
      if (typeof command !== 'function') throw new Error(`This renderer declared the live command "${name}" but its mounted view does not answer it.`);
      const committed = command.apply(runtime, args);
      if (typeof committed === 'function') return committed as (state: State) => boolean;
      return name === 'clearSelection' ? (state: State) => state.selection.length === 0 : undefined;
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
