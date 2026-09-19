import type { PromptReference, ResourceRef } from '@hardcore/core/prompt';
import type { JsonValue } from '../../file-viewer/types.js';

export interface CadCameraSnapshot {
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
export interface CadLiveState {
  resource: ResourceRef;
  revision: string;
  active: boolean;
  loading: boolean;
  selection: readonly PromptReference[];
  selectedPartIds: readonly string[];
  selectedReferenceIds: readonly string[];
  hiddenPartIds: readonly string[];
  isolatedPartIds: readonly string[];
  camera: CadCameraSnapshot | null;
  display: { [key: string]: JsonValue };
  renderMode: 'inspect' | 'render';
}
export interface CadLiveController {
  /** Pure snapshots only. After unmount this returns the last view, active:false. */
  readState(): CadLiveState;
  select(options: { selectors: readonly string[]; replace?: boolean }): Promise<CadLiveState>;
  clearSelection(): Promise<CadLiveState>;
  setCamera(snapshot: CadCameraSnapshot): Promise<CadLiveState>;
  resetCamera(): Promise<CadLiveState>;
  setDisplaySettings(patch: { [key: string]: JsonValue }): Promise<CadLiveState>;
  setRenderMode(enabled: boolean): Promise<CadLiveState>;
  /** This returns a frozen image only; the host owns its transport and destination. */
  capture(): Promise<Blob>;
}
export interface CadLiveBinding {
  /** Bind the mounted view only. Cleanup may retain readState() as an inactive snapshot. */
  bind(controller: CadLiveController): () => void;
}

interface CadLiveRuntime {
  readState(): Omit<CadLiveState, 'active'>;
  select(options: Parameters<CadLiveController['select']>[0]): void;
  clearSelection(): void;
  setCamera(snapshot: CadCameraSnapshot): void;
  resetCamera(): void;
  setDisplaySettings(patch: Parameters<CadLiveController['setDisplaySettings']>[0]): void;
  setRenderMode(enabled: boolean): void;
  capture(): Promise<Blob>;
}
const settleFrame = () => new Promise<void>(resolve => requestAnimationFrame(() => resolve()));
const scopeKey = (state: Omit<CadLiveState, 'active'>) => JSON.stringify([state.resource, state.revision]);

/** Internal mounted-view adapter. It never retains a scene after detach. */
export function attachCadLiveBinding(binding: CadLiveBinding, readRuntime: () => CadLiveRuntime,
  settle: () => Promise<void> = settleFrame): () => void {
  let active = true;
  let departed: CadLiveState | null = null;
  const readState = (): CadLiveState => structuredClone(departed ?? { ...readRuntime().readState(), active });
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
  const mutate = async (apply: (runtime: CadLiveRuntime) => void,
    committed?: (state: CadLiveState) => boolean): Promise<CadLiveState> => {
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
  const controller: CadLiveController = {
    readState,
    select: options => mutate(runtime => runtime.select(options)),
    clearSelection: () => mutate(runtime => runtime.clearSelection()),
    setCamera: snapshot => mutate(runtime => runtime.setCamera(snapshot)),
    resetCamera: () => mutate(runtime => runtime.resetCamera()),
    setDisplaySettings: patch => mutate(runtime => runtime.setDisplaySettings(patch),
      state => patch.mode == null || state.display.mode === patch.mode),
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
  const release = binding.bind(controller);
  return () => {
    if (!active) return;
    departed = { ...readState(), active: false };
    active = false;
    // Drop the component closure: retained inactive snapshots own no scene.
    readRuntime = () => { throw new Error('This viewer is inactive.'); };
    release();
  };
}
