// A scene's own lighting (`sceneContract.js`'s `rig`), on whatever stage shows it: the viewer's
// viewport (`@text-to-cad/ui` renderers/kit, `ShellViewport.jsx`) and the snapshot's headless stage
// (`common/renderMeshScene.js`) both light a scene that brings a rig with THIS, in place of the
// theme's rig, outside photographic Render. A rig is plain data:
//
//   { id,                                   what it is, for a host deciding whether it changed
//     ambient,                              { color, intensity }: three's AmbientLight, or null
//     lights: [{ name, towards, color, intensity }],   DirectionalLights; `towards`, the unit
//                                           vector from a surface to the light, world frame
//     environment,                          the light every surface reflects, or null:
//                                           { width, height, data, intensity, rotation }, an
//                                           equirectangular image (RGBA floats, bottom row
//                                           first) the stage turns into its PMREM, each
//                                           roughness's level the image prefiltered by that
//                                           roughness's GGX lobe (`ggxEnvironment.js`), lighting
//                                           the scene at `intensity`, turned by `rotation` (Euler
//                                           radians, three's `scene.environmentRotation`)
//     exposure,                             the renderer's toneMappingExposure
//     toneCurve,                            a curve of SCENE_RIG_TONE_CURVES, drawn as three's
//                                           CustomToneMapping
//     blend }                               optional: "linear", see-through surfaces blended in
//                                           linear light, as an sRGB frame buffer blends them
//                                           (OCCT's raster); absent, as three blends them on the
//                                           canvas, each fragment encoded to sRGB first
//
// Its lights cast no shadow. A rig put up keeps what the stage had (its renderer's tone mapping
// and exposure, its scene's environment, intensity and rotation) and the last one taken down gives
// it back; one stage's rigs that share an environment image share its PMREM. A rig that blends in
// linear light is drawn through a frame of its own (`createLinearFrame`): the stage draws its scene
// with `renderWithSceneRig`, which is three's own draw for every other rig and for none.

import { prefilterEnvironment } from "./ggxEnvironment.js";

// The tone curves a rig may name: the body of three's `CustomToneMapping( vec3 color )`, after
// exposure. `clamp` is the colour times the exposure, clamped to [0, 1]: what an sRGB frame
// buffer does to a linear sum and nothing more (OCCT's raster: `cadgen/engine/render/look.py`).
export const SCENE_RIG_TONE_CURVES = Object.freeze({
  clamp: "return saturate( toneMappingExposure * color );"
});

const CUSTOM_TONE_MAPPING = /vec3 CustomToneMapping\( vec3 color \) \{[^}]*\}/;

/**
 * Make three's `CustomToneMapping` the rig's curve, in the shader chunk every program that tone
 * maps includes (`ShaderChunk.tonemapping_pars_fragment`). One custom curve serves a page:
 * installing it again is a no-op, and another is refused, since programs already compiled keep
 * the curve they were compiled with.
 */
export function installSceneRigToneCurve(THREE, curve) {
  const body = SCENE_RIG_TONE_CURVES[curve];
  if (!body) throw new Error(`a scene rig's tone curve is one of ${Object.keys(SCENE_RIG_TONE_CURVES).join(", ")}, not ${JSON.stringify(curve)}`);
  const chunk = THREE.ShaderChunk.tonemapping_pars_fragment;
  const found = CUSTOM_TONE_MAPPING.exec(chunk);
  if (!found) throw new Error("three's tone mapping chunk has no CustomToneMapping to replace");
  const wanted = `vec3 CustomToneMapping( vec3 color ) { ${body} }`;
  if (found[0] === wanted) return;
  if (!/\{ return color; \}$/.test(found[0])) {
    throw new Error("three's CustomToneMapping already draws another curve: one custom tone curve serves a page");
  }
  THREE.ShaderChunk.tonemapping_pars_fragment = chunk.replace(CUSTOM_TONE_MAPPING, wanted);
}

/**
 * The rig a scene is lit by under the surface look it wears (`sceneContract.js`): its `rigFor(look)`
 * where it has one, else its `rig`, else none. The regular modes only: Render lights every scene alike.
 */
export function sceneRigFor(scene, look) {
  if (!scene) return null;
  return (typeof scene.rigFor === "function" ? scene.rigFor(look) : scene.rig) || null;
}

/** Whether a value is a rig a stage can put up: its lights, its exposure, a curve and a blend it knows. */
export function isSceneRig(rig) {
  const environment = rig?.environment;
  return Boolean(rig && typeof rig === "object" && Array.isArray(rig.lights)
    && (rig.ambient == null || Number.isFinite(Number(rig.ambient.intensity)))
    && (environment == null || (environment.data?.length === environment.width * environment.height * 4
      && Number.isFinite(Number(environment.intensity))))
    && Number.isFinite(Number(rig.exposure)) && Object.hasOwn(SCENE_RIG_TONE_CURVES, rig.toneCurve)
    && (rig.blend == null || rig.blend === "linear"));
}

// The frame of a rig that blends in linear light, three passes where three draws one:
//
//   SURFACES  the scene but for what three draws after its see-through surfaces, into a half-float
//             target of the destination's size. The target is XR-flagged (`isXRRenderTarget`), so
//             three draws into it as it draws the canvas -- each fragment under the rig's tone curve
//             and exposure, the curve's clamp what an 8-bit buffer does to it -- but writes in the
//             target's colour space, linear, where the canvas's is sRGB: a see-through fragment is
//             blended with what lies under it before the picture is encoded, where on the canvas it
//             is blended after. Multisampled where the context is (the canvas's antialiasing).
//   ENCODE    the target onto the destination, encoded to its colour space, its depth with it.
//   OVER      what three draws after the see-through surfaces (`drawnOverSurfaces`: an X-ray's
//             edges, a highlight, ink), over the encoded picture as three draws it on the canvas, so
//             a line's antialiased pixels are resolved in sRGB, as OCCT's are: OCCT draws X-ray's
//             edges in a layer of their own, over the model.
//
// ENCODE reads each pixel's own texel, so the scene is drawn in the destination's viewport and the
// passes fill that alone.
const LINEAR_FRAME_VERTEX = /* glsl */ `
void main() {
  gl_Position = vec4(position.xy, 0.0, 1.0);
}
`;

// Three's blend leaves colour premultiplied by alpha (alpha is 1 over a backdrop): the pass encodes
// the colour unpremultiplied, and premultiplies it again as the canvas holds it.
const LINEAR_FRAME_FRAGMENT = /* glsl */ `
uniform highp sampler2D uLinear;
uniform highp sampler2D uDepth;
void main() {
  ivec2 pixel = ivec2(gl_FragCoord.xy);
  vec4 held = texelFetch(uLinear, pixel, 0);
  vec3 straight = held.a > 0.0 ? clamp(held.rgb / held.a, 0.0, 1.0) : vec3(0.0);
  gl_FragColor = vec4(linearToOutputTexel(vec4(straight, 1.0)).rgb * held.a, held.a);
  gl_FragDepth = texelFetch(uDepth, pixel, 0).x;
}
`;

// The layer OVER draws by: what it draws, while it draws it, and the lights of a rig that blends in
// linear light, always.
const OVER_LAYER = 31;

/** Whether `renderer` can draw into half floats (WebGL2's colour-buffer-float extensions). */
function drawsHalfFloats(renderer) {
  const extensions = renderer?.extensions;
  if (typeof extensions?.has !== "function") return false;
  return extensions.has("EXT_color_buffer_float") || extensions.has("EXT_color_buffer_half_float");
}

/**
 * Whether three draws `object` after the see-through surfaces of a scene (their `renderOrder` 0)
 * as `camera` sees it: a transparent one ordered after them. Three draws every opaque object first,
 * whatever its order.
 */
export function drawnOverSurfaces(object, camera) {
  if (!(object?.renderOrder > 0) || !(object.isMesh || object.isLine || object.isPoints || object.isSprite)) return false;
  if (!object.layers.test(camera.layers)) return false;
  const { material } = object;
  return Array.isArray(material) ? material.some(entry => entry?.transparent === true) : material?.transparent === true;
}

/**
 * The frame a rig that blends in linear light draws its scene through (see above). Where the
 * renderer cannot draw into half floats it draws the scene as three does.
 * @returns {{ target: object | null, render(renderer, scene, camera): void,
 *   compileAsync(renderer, scene, camera): Promise<unknown>, dispose(): void }}
 */
export function createLinearFrame(THREE) {
  let target = null;
  let disposed = false;
  const geometry = new THREE.BufferGeometry();
  // One triangle over the whole viewport: no diagonal seam.
  geometry.setAttribute("position", new THREE.Float32BufferAttribute([-1, -1, 0, 3, -1, 0, -1, 3, 0], 3));
  const pass = new THREE.Mesh(geometry, new THREE.ShaderMaterial({
    name: "Scene rig linear frame",
    uniforms: { uLinear: { value: null }, uDepth: { value: null } },
    vertexShader: LINEAR_FRAME_VERTEX,
    fragmentShader: LINEAR_FRAME_FRAGMENT,
    blending: THREE.NoBlending,
    // Every pixel takes the scene's depth, for what OVER draws to be hidden where it was.
    depthTest: true,
    depthFunc: THREE.AlwaysDepth,
    depthWrite: true,
    toneMapped: false
  }));
  pass.frustumCulled = false;
  const passScene = new THREE.Scene();
  passScene.add(pass);
  const passCamera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
  const uniforms = pass.material.uniforms;
  const size = new THREE.Vector2();
  const region = new THREE.Vector4();
  const drawn = new THREE.Vector4();
  const viewport = new THREE.Vector4();
  const scissor = new THREE.Vector4();
  const over = [];
  const masks = [];

  function targetFor(renderer) {
    if (!target) {
      const antialiased = renderer.getContext?.()?.getContextAttributes?.()?.antialias === true;
      // The scene's depth, which ENCODE hands the destination: depth and stencil, as the canvas has.
      const depthTexture = new THREE.DepthTexture(1, 1, THREE.UnsignedInt248Type);
      depthTexture.format = THREE.DepthStencilFormat;
      target = new THREE.WebGLRenderTarget(1, 1, {
        type: THREE.HalfFloatType,
        colorSpace: THREE.LinearSRGBColorSpace,
        minFilter: THREE.NearestFilter,
        magFilter: THREE.NearestFilter,
        generateMipmaps: false,
        depthBuffer: true,
        stencilBuffer: true,
        depthTexture,
        samples: antialiased ? 4 : 0,
        resolveStencilBuffer: false
      });
      target.texture.name = "scene-rig-linear";
      target.isXRRenderTarget = true;
      frame.target = target;
    }
    return target;
  }

  // What three draws after the see-through surfaces, as `camera` sees `scene`: on OVER's layer
  // alone until `restoreOver`, so SURFACES leaves it out whatever shows or hides it meanwhile.
  function setOver(scene, camera) {
    scene.traverse((object) => {
      if (!drawnOverSurfaces(object, camera)) return;
      over.push(object);
      masks.push(object.layers.mask);
      object.layers.set(OVER_LAYER);
    });
  }

  function restoreOver() {
    over.forEach((object, at) => { object.layers.mask = masks[at]; });
    over.length = masks.length = 0;
  }

  // OVER: the scene by its layer alone (what goes over, and the rig's lights), on the destination,
  // with no backdrop and no shadow pass of its own.
  function drawOver(renderer, scene, camera) {
    const layers = camera.layers.mask;
    const background = scene.background;
    const shadowMap = renderer.shadowMap;
    const shadows = shadowMap ? [shadowMap.autoUpdate, shadowMap.needsUpdate] : null;
    try {
      camera.layers.set(OVER_LAYER);
      scene.background = null;
      if (shadowMap) shadowMap.autoUpdate = shadowMap.needsUpdate = false;
      renderer.render(scene, camera);
    } finally {
      camera.layers.mask = layers;
      scene.background = background;
      if (shadowMap) [shadowMap.autoUpdate, shadowMap.needsUpdate] = shadows;
    }
  }

  const frame = {
    target: null,
    /** Draw `scene` from `camera` to the renderer's current target (the canvas, or a caller's). */
    render(renderer, scene, camera) {
      if (disposed) throw new Error("The scene rig's linear frame was disposed");
      if (!drawsHalfFloats(renderer)) {
        renderer.render(scene, camera);
        return;
      }
      const destination = renderer.getRenderTarget();
      const into = targetFor(renderer);
      if (destination) size.set(destination.width, destination.height);
      else renderer.getDrawingBufferSize(size);
      const width = Math.max(1, Math.floor(size.x));
      const height = Math.max(1, Math.floor(size.y));
      if (into.width !== width || into.height !== height) into.setSize(width, height);
      // Where the destination would be drawn now, in its pixels: the scene is drawn there.
      renderer.getCurrentViewport(region);
      into.viewport.copy(region);
      if (destination) {
        into.scissor.copy(destination.scissor);
        into.scissorTest = destination.scissorTest;
      } else {
        // As three scissors the canvas once it is the target again (`setRenderTarget(null)`).
        into.scissor.copy(renderer.getScissor(scissor).multiplyScalar(renderer.getPixelRatio()).floor());
        into.scissorTest = renderer.getScissorTest();
        renderer.getViewport(viewport);
      }
      const autoClear = renderer.autoClear;
      try {
        setOver(scene, camera);
        renderer.autoClear = true;
        renderer.setRenderTarget(into);
        renderer.render(scene, camera);
        renderer.setRenderTarget(destination);
        // Three gives the canvas its viewport back floored; the passes fill the one drawn in.
        if (!destination && !renderer.getCurrentViewport(drawn).equals(region)) renderer.setViewport(viewport);
        renderer.autoClear = false;
        uniforms.uLinear.value = into.texture;
        uniforms.uDepth.value = into.depthTexture;
        renderer.render(passScene, passCamera);
        if (over.length) drawOver(renderer, scene, camera);
      } finally {
        restoreOver();
        uniforms.uLinear.value = uniforms.uDepth.value = null;
        renderer.autoClear = autoClear;
        if (renderer.getRenderTarget() !== destination) renderer.setRenderTarget(destination);
      }
    },
    /**
     * Compile what `render` draws: the scene's programs as SURFACES draws into the target, those of
     * what goes over it as OVER draws on the destination, and the pass's.
     */
    compileAsync(renderer, scene, camera) {
      if (disposed || !drawsHalfFloats(renderer)) return renderer.compileAsync(scene, camera);
      const destination = renderer.getRenderTarget();
      const compiled = [];
      renderer.setRenderTarget(targetFor(renderer));
      try {
        compiled.push(renderer.compileAsync(scene, camera));
      } finally {
        renderer.setRenderTarget(destination);
      }
      scene.traverse((object) => { if (drawnOverSurfaces(object, camera)) compiled.push(renderer.compileAsync(object, camera, scene)); });
      compiled.push(renderer.compileAsync(passScene, passCamera));
      return Promise.all(compiled);
    },
    dispose() {
      if (disposed) return;
      disposed = true;
      target?.depthTexture?.dispose();
      target?.dispose();
      target = frame.target = null;
      geometry.dispose();
      pass.material.dispose();
    }
  };
  return frame;
}

/**
 * Draw `scene` from `camera` as the rig up on a stage composites it (`rig`, the handle
 * `applySceneRig` returned, or the stage's `sceneRig`): through its frame where it blends in linear
 * light, else as three draws it. Every stage draws a scene that may wear a rig by this.
 */
export function renderWithSceneRig(rig, renderer, scene, camera) {
  if (rig?.frame) rig.frame.render(renderer, scene, camera);
  else renderer.render(scene, camera);
}

/** Compile what `renderWithSceneRig` draws (three's `compileAsync`, through the rig's frame where it has one). */
export function compileWithSceneRig(rig, renderer, scene, camera) {
  return rig?.frame ? rig.frame.compileAsync(renderer, scene, camera) : renderer.compileAsync(scene, camera);
}

// A renderer's PMREMs of environment images, by the image's pixels: shared by the rigs that light
// with the same image, released with the last of them. Each level is the image prefiltered by the
// GGX lobe of its roughness, as OCCT bakes its image-based light (`ggxEnvironment.js`).
const environments = new WeakMap();

function acquireEnvironment(THREE, renderer, environment) {
  let held = environments.get(renderer);
  if (!held) environments.set(renderer, held = new Map());
  let found = held.get(environment.data);
  if (!found) {
    found = { target: prefilterEnvironment(THREE, renderer, environment), refs: 0 };
    held.set(environment.data, found);
  }
  found.refs += 1;
  return found.target;
}

function releaseEnvironment(renderer, environment) {
  const held = environments.get(renderer);
  const found = held?.get(environment.data);
  if (!found) return;
  found.refs -= 1;
  if (found.refs > 0) return;
  found.target.dispose();
  held.delete(environment.data);
}

/**
 * Put a scene's rig up on a stage: its lights in a group of their own under `stage.scene`, its
 * environment as the scene's, its exposure and tone curve on `stage.renderer`. The stage's own
 * lights are the caller's to hide. `stage` is the object the stage keeps for as long as it lives
 * (the viewer's runtime, the snapshot's viewport): the rig up on it is `stage.sceneRig`, and what
 * it found there is kept beside it until the last rig comes down.
 *
 * A rig that blends in linear light brings its frame (`frame`, `createLinearFrame`), which the
 * stage draws the scene through (`renderWithSceneRig`) and which goes with the rig.
 *
 * @param {typeof import("three")} THREE
 * @param {{ scene: import("three").Scene, renderer: object }} stage
 * @param {object} rig  A scene's `rig` (`sceneContract.js`).
 * @returns {{ rig: object, group: import("three").Group, frame: object | null, restate(): void, dispose(): void }}
 *   `restate`: put the rig's renderer and environment state back after the stage set its own.
 */
export function applySceneRig(THREE, stage, rig) {
  if (!isSceneRig(rig)) throw new Error("a scene rig has directional lights, an exposure, a known tone curve and a known blend");
  installSceneRigToneCurve(THREE, rig.toneCurve);
  const { scene, renderer } = stage;
  const group = new THREE.Group();
  group.name = "Scene rig";
  if (rig.ambient) group.add(new THREE.AmbientLight(rig.ambient.color || "#ffffff", Number(rig.ambient.intensity)));
  for (const light of rig.lights) {
    const directional = new THREE.DirectionalLight(light.color || "#ffffff", Number(light.intensity));
    directional.name = String(light.name || "rig light");
    // A directional light shines from its position towards its target, the origin.
    directional.position.fromArray(light.towards).normalize();
    directional.castShadow = false;
    group.add(directional);
  }
  // Its frame's OVER pass draws by a layer of its own, which these light too.
  if (rig.blend === "linear") for (const light of group.children) light.layers.enable(OVER_LAYER);
  scene.add(group);
  stage.sceneRigKept ??= {
    toneMapping: renderer.toneMapping, toneMappingExposure: renderer.toneMappingExposure, environment: scene.environment,
    environmentIntensity: scene.environmentIntensity, environmentRotation: scene.environmentRotation.clone()
  };
  const target = rig.environment ? acquireEnvironment(THREE, renderer, rig.environment) : null;
  let disposed = false;
  const handle = {
    rig,
    group,
    frame: rig.blend === "linear" ? createLinearFrame(THREE) : null,
    restate() {
      if (disposed) return;
      renderer.toneMapping = THREE.CustomToneMapping;
      renderer.toneMappingExposure = Number(rig.exposure);
      scene.environment = target ? target.texture : null;
      scene.environmentIntensity = target ? Number(rig.environment.intensity) : 0;
      scene.environmentRotation.set(...(rig.environment?.rotation || [0, 0, 0]));
    },
    dispose() {
      if (disposed) return;
      disposed = true;
      group.removeFromParent();
      for (const light of group.children) light.dispose?.();
      handle.frame?.dispose();
      if (stage.sceneRig === handle) {
        const kept = stage.sceneRigKept;
        renderer.toneMapping = kept.toneMapping;
        renderer.toneMappingExposure = kept.toneMappingExposure;
        scene.environment = kept.environment;
        scene.environmentIntensity = kept.environmentIntensity;
        scene.environmentRotation.copy(kept.environmentRotation);
        stage.sceneRig = null;
        stage.sceneRigKept = undefined;
      }
      if (rig.environment) releaseEnvironment(renderer, rig.environment);
    }
  };
  stage.sceneRig = handle;
  handle.restate();
  return handle;
}
