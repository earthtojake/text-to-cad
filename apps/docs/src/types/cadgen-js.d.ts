// Hand-written declarations for the cadgen-js surface the docs app consumes
// (cadgen-js ships untyped JS). Declare exactly what is imported — a member
// missing here is a member the hero stopped using or never had.

declare module "cadgen-js/common/animationClock.js" {
  export type AnimationClip = {
    id: string;
    label: string;
    duration: number;
    loop: boolean;
    update: (t: number, m: unknown) => void;
  };

  export function animationClipDuration(clip: AnimationClip | null): number;

  export function findAnimationClip(
    clips: Record<string, AnimationClip>,
    clipId: string
  ): AnimationClip | null;

  export function firstAnimationClipId(
    clips: Record<string, AnimationClip>
  ): string;
}

declare module "cadgen-js/common/animationRuntime.js" {
  import type { AnimationClip } from "cadgen-js/common/animationClock.js";

  export function compileAnimationClips(
    moduleSource: string
  ): Promise<Record<string, AnimationClip>>;
}

declare module "cadgen-js/common/kinematicsModule.js" {
  export function loadAnimationSource(sidecarUrl: string): Promise<string>;
}

declare module "cadgen-js/common/cadScene.js" {
  import type { Group } from "three";

  type CadBounds = {
    min: number[];
    max: number[];
  };

  export const CAD_SCENE_SCALE: {
    CAD: string;
    URDF: string;
  };

  export type CadSceneApi = {
    root: Group;
    modelGroup: Group;
    edgesGroup: Group;
    displayRecords: unknown[];
    records: unknown[];
    bounds: CadBounds;
    radius: number;
    runtime: unknown;
    dispose: () => void;
    update: (settings?: Record<string, unknown>) => CadSceneApi;
  };

  export function buildModel(
    THREE: unknown,
    source: unknown,
    settings?: Record<string, unknown>
  ): CadSceneApi;
}

declare module "cadgen-js/common/renderModel.js" {
  export type RenderViewportApi = {
    renderer: unknown;
    scene: unknown;
    camera: unknown;
    ready: Promise<void>;
    resize: () => unknown;
    render: () => void;
    start: () => void;
    stop: () => void;
    capturePng: () => string;
    dispose: () => void;
  };

  export function renderModel(
    THREE: unknown,
    model: unknown,
    options?: Record<string, unknown>
  ): RenderViewportApi;
}

declare module "cadgen-js/common/source.js" {
  export type RenderSource = {
    kind: string;
    meshData: unknown;
    stepParameterSource: unknown;
    sourceSidecar: unknown;
  };

  export function loadSource(
    input: unknown,
    options?: Record<string, unknown>
  ): Promise<RenderSource>;

  export function packageSourceFromBaseUrl(
    baseUrl: string,
    descriptor: unknown
  ): { kind: string; package: Record<string, unknown> };

  export function stepParameterRuntime(
    stepParameterSource: unknown
  ): Record<string, unknown> | null;
}

declare module "cadgen-js/common/themeSettings.js" {
  export function cloneThemePresetSettings(presetId: string): Record<
    string,
    unknown
  > & {
    materials?: Record<string, unknown>;
  };
}
