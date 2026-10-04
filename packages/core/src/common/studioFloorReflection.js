// The Render studio's glossy floor: the model reflected in it, softening and fading with
// height above the floor, as a polished studio floor shows a product.
//
// Before each frame (the scene's onBeforeRender, see photographicStudio.js) the scene is
// drawn once more, from the camera mirrored in the floor, at a fraction of the canvas's
// resolution (`resolution`), into a small target. Small full-screen passes over that
// target fade it with each reflected point's height (`fadeHeight`), soften it a little
// (`sharpBlur`) and more (`blur`), and mix the two by that height (`blurHeight`): crisp
// where the model meets the floor, softer as it rises. The floor's shader projects its
// fragments into the mirrored view, reads that one texture and lays it over itself with
// a Fresnel weight (`strength` at grazing, `normalWeight` of it looking straight down),
// in display colour, so a light floor shows the reflection as a dark one does.
//
// The mirrored draw is the cost: a second draw of the scene, at a fraction of the pixels.
// It runs when the camera moved or the frame re-renders shadows (the casters changed; the
// mirrored draw then renders them, and the frame keeps them). Any other frame (a
// highlight, an overlay) keeps the last reflection and, with a `requestFrame`, catches up
// at most every `interval` milliseconds and once more when those frames stop. A caller
// without a `requestFrame` (a snapshot) draws it on every frame.
//
// It is drawn before the frame, at the frame's own render depth, not from the floor's
// onBeforeRender: three gives a draw nested in another its own light state, and every
// lit material then rebuilds its program key twice a frame, which cost more than the
// mirrored draw itself.

import { createHeightSchedule } from "./studioContactShadow.js";

const PASS_VERTEX = /* glsl */ `
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = vec4(position.xy, 0.0, 1.0);
}
`;

// A reflected point's height above the floor, from the mirrored draw's depth; where
// nothing was drawn, far above anything.
const HEIGHT_GLSL = /* glsl */ `
uniform sampler2D uDepth;
uniform mat4 uInverse;
uniform float uFloorZ;
float reflectedHeight(vec2 uv) {
  float depth = texture2D(uDepth, uv).r;
  if (depth >= 0.99999) return 1e20;
  vec4 point = uInverse * vec4(uv * 2.0 - 1.0, depth * 2.0 - 1.0, 1.0);
  return max(point.z / point.w - uFloorZ, 0.0);
}
`;

// Fade the mirrored image with height and premultiply it, so the blurs spread colour and
// weight together and nothing reflected bleeds in as black.
const PREP_FRAGMENT = /* glsl */ `
uniform sampler2D uColor;
uniform float uFadeHeight;
varying vec2 vUv;
${HEIGHT_GLSL}
void main() {
  vec4 color = texture2D(uColor, vUv);
  float weight = color.a * (1.0 - smoothstep(0.0, uFadeHeight, reflectedHeight(vUv)));
  gl_FragColor = vec4(color.rgb * weight, weight);
}
`;

// One separable Gaussian pass: 17 taps over two sigmas either side.
const GAUSSIAN_GLSL = /* glsl */ `
uniform sampler2D uInput;
uniform vec2 uStep;
vec4 gaussian(vec2 uv) {
  vec4 sum = vec4(0.0);
  float total = 0.0;
  for (int i = -8; i <= 8; i++) {
    float t = float(i) / 4.0;
    float w = exp(-0.5 * t * t);
    sum += w * texture2D(uInput, uv + uStep * float(i));
    total += w;
  }
  return sum / total;
}
`;

const BLUR_FRAGMENT = /* glsl */ `
varying vec2 vUv;
${GAUSSIAN_GLSL}
void main() {
  gl_FragColor = gaussian(vUv);
}
`;

// The soft copy's second pass, mixed with the crisp copy by height as it is drawn.
const COMBINE_FRAGMENT = /* glsl */ `
uniform sampler2D uSharp;
uniform float uBlurHeight;
varying vec2 vUv;
${HEIGHT_GLSL}
${GAUSSIAN_GLSL}
void main() {
  gl_FragColor = mix(texture2D(uSharp, vUv), gaussian(vUv),
    smoothstep(0.0, uBlurHeight, reflectedHeight(vUv)));
}
`;

const FLOOR_VERTEX_PARS = /* glsl */ `
varying vec3 vStudioFloorWorld;
`;

const FLOOR_VERTEX = /* glsl */ `
vStudioFloorWorld = (modelMatrix * vec4(transformed, 1.0)).xyz;
`;

const FLOOR_FRAGMENT_PARS = /* glsl */ `
uniform sampler2D uReflection;
uniform mat4 uReflectionMatrix;
uniform vec3 uReflectionShape;
uniform float uReflectionReady;
varying vec3 vStudioFloorWorld;
`;

// At the end of the floor's fragment shader: the reflection, in display colour, over the floor's.
const FLOOR_FRAGMENT = /* glsl */ `
if (uReflectionReady > 0.5) {
  vec4 clip = uReflectionMatrix * vec4(vStudioFloorWorld, 1.0);
  vec2 ruv = clip.xy / clip.w * 0.5 + 0.5;
  if (clip.w > 0.0 && all(greaterThanEqual(ruv, vec2(0.0))) && all(lessThanEqual(ruv, vec2(1.0)))) {
    vec4 reflected = texture2D(uReflection, ruv);
    vec3 toEye = normalize(cameraPosition - vStudioFloorWorld);
    float grazing = 1.0 - abs(toEye.z);
    float weight = clamp(reflected.a * uReflectionShape.x
      * mix(uReflectionShape.y, 1.0, grazing * grazing * grazing), 0.0, 1.0);
    vec3 color = reflected.rgb / max(reflected.a, 1e-4);
    // Over the floor and whatever shows through it: the reflection covers both.
    float alpha = gl_FragColor.a + weight * (1.0 - gl_FragColor.a);
    gl_FragColor.rgb = (gl_FragColor.a * (1.0 - weight) * gl_FragColor.rgb + weight * color) / max(alpha, 1e-4);
    gl_FragColor.a = alpha;
  }
}
`;

function fullScreenPass(THREE, fragmentShader, uniforms) {
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), new THREE.ShaderMaterial({
    uniforms,
    vertexShader: PASS_VERTEX,
    fragmentShader,
    depthTest: false,
    depthWrite: false,
    blending: THREE.NoBlending,
    toneMapped: false
  }));
  mesh.frustumCulled = false;
  const scene = new THREE.Scene();
  scene.add(mesh);
  return { mesh, scene, uniforms: mesh.material.uniforms };
}

function colorTarget(THREE, name, depthTexture = null) {
  const target = new THREE.WebGLRenderTarget(1, 1, {
    type: THREE.HalfFloatType,
    minFilter: THREE.LinearFilter,
    magFilter: THREE.LinearFilter,
    depthBuffer: Boolean(depthTexture),
    depthTexture,
    generateMipmaps: false
  });
  target.texture.name = name;
  return target;
}

/**
 * Create the reflection for one studio floor. `patch(shader)` adds it to the floor's
 * MeshStandardMaterial shader (from its onBeforeCompile); `beforeRender(renderer, scene,
 * camera, hidden)` (before the frame: the scene's onBeforeRender) draws it when due,
 * leaving `hidden` (the floor, its shadow layer, guides) out of the mirrored draw;
 * `place()` gives the floor's height and the model's height above it.
 *
 * `resolution` is the mirrored draw's size as a fraction of the drawing buffer's; `blur`
 * and `sharpBlur` the soft and the crisp copies' Gaussian sigmas, in its texels;
 * `blurHeight` and `fadeHeight` the fractions of the model's height over which the
 * reflection turns soft and fades out; `strength` its weight at grazing and
 * `normalWeight` the fraction of that looking straight down.
 */
export function createStudioFloorReflection(THREE, {
  resolution = 0.5,
  blur = 2,
  sharpBlur = 0,
  strength = 0.75,
  normalWeight = 0.45,
  blurHeight = 0.8,
  fadeHeight = 1,
  interval = 400,
  requestFrame = null,
  now,
  setTimer,
  clearTimer
} = {}) {
  const depthTexture = new THREE.DepthTexture(1, 1, THREE.UnsignedIntType);
  // The mirrored draw, then the blurs' halfway passes; the crisp copy; and what the floor
  // reads. No pass draws into a target whose colour or depth it samples: WebGL refuses
  // that draw as a feedback loop, so the soft copy's second pass and the mix are one.
  const mirrored = colorTarget(THREE, "studio-floor-reflection", depthTexture);
  const sharp = colorTarget(THREE, "studio-floor-reflection-sharp");
  const combined = colorTarget(THREE, "studio-floor-reflection-combined");
  const passCamera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
  const heightUniforms = () => ({
    uDepth: { value: depthTexture },
    uInverse: { value: inverse },
    uFloorZ: { value: 0 }
  });
  const inverse = new THREE.Matrix4();
  const prep = fullScreenPass(THREE, PREP_FRAGMENT, {
    ...heightUniforms(),
    uColor: { value: mirrored.texture },
    uFadeHeight: { value: 1 }
  });
  const blurPass = fullScreenPass(THREE, BLUR_FRAGMENT, {
    uInput: { value: null },
    uStep: { value: new THREE.Vector2() }
  });
  const combine = fullScreenPass(THREE, COMBINE_FRAGMENT, {
    ...heightUniforms(),
    uSharp: { value: sharp.texture },
    uInput: { value: null },
    uStep: { value: new THREE.Vector2() },
    uBlurHeight: { value: 1 }
  });

  const uniforms = {
    uReflection: { value: combined.texture },
    uReflectionMatrix: { value: new THREE.Matrix4() },
    uReflectionShape: { value: new THREE.Vector3(strength, normalWeight, 0) },
    uReflectionReady: { value: 0 }
  };

  const state = { sceneChanged: true, lastView: [], floorZ: 0, height: 1, width: 0, heightPx: 0, ready: false };
  const schedule = createHeightSchedule({ interval, requestFrame, now, setTimer, clearTimer });

  const mirrorCameras = new Map();
  const plane = new THREE.Plane();
  const normal = new THREE.Vector3(0, 0, 1);
  const floorPoint = new THREE.Vector3();
  const eye = new THREE.Vector3();
  const mirroredEye = new THREE.Vector3();
  const lookAt = new THREE.Vector3();
  const target = new THREE.Vector3();
  const rotation = new THREE.Matrix4();
  const clipPlane = new THREE.Vector4();
  const q = new THREE.Vector4();
  const viewProjection = new THREE.Matrix4();
  const size = new THREE.Vector2();
  const clearColor = new THREE.Color();

  function mirrorCamera(camera) {
    const kind = camera.isOrthographicCamera ? "orthographic" : "perspective";
    let mirror = mirrorCameras.get(kind);
    if (!mirror) {
      mirror = camera.clone();
      mirrorCameras.set(kind, mirror);
    }
    return mirror;
  }

  function viewKey(camera) {
    return [...camera.matrixWorld.elements, ...camera.projectionMatrix.elements, state.width, state.heightPx, state.floorZ];
  }

  function sameView(key) {
    const last = state.lastView;
    if (last.length !== key.length) return false;
    for (let index = 0; index < key.length; index += 1) if (last[index] !== key[index]) return false;
    return true;
  }

  function resize(renderer) {
    renderer.getDrawingBufferSize(size);
    const width = Math.max(1, Math.round(size.x * resolution));
    const height = Math.max(1, Math.round(size.y * resolution));
    if (width === state.width && height === state.heightPx) return;
    state.width = width;
    state.heightPx = height;
    for (const renderTarget of [mirrored, sharp, combined]) renderTarget.setSize(width, height);
  }

  // The camera mirrored in the floor, its near plane turned onto the floor so nothing
  // below it is reflected (Lengyel's oblique clipping, as in three's Reflector).
  function placeMirror(camera) {
    const mirror = mirrorCamera(camera);
    mirror.copy(camera, false);
    floorPoint.set(0, 0, state.floorZ);
    eye.setFromMatrixPosition(camera.matrixWorld);
    rotation.extractRotation(camera.matrixWorld);
    lookAt.set(0, 0, -1).applyMatrix4(rotation).add(eye);
    mirroredEye.subVectors(floorPoint, eye).reflect(normal).negate().add(floorPoint);
    target.subVectors(floorPoint, lookAt).reflect(normal).negate().add(floorPoint);
    mirror.position.copy(mirroredEye);
    mirror.up.set(0, 1, 0).applyMatrix4(rotation).reflect(normal);
    mirror.lookAt(target);
    mirror.updateMatrixWorld(true);
    mirror.projectionMatrix.copy(camera.projectionMatrix);
    mirror.layers.mask = camera.layers.mask;
    plane.setFromNormalAndCoplanarPoint(normal, floorPoint).applyMatrix4(mirror.matrixWorldInverse);
    clipPlane.set(plane.normal.x, plane.normal.y, plane.normal.z, plane.constant);
    const p = mirror.projectionMatrix.elements;
    if (mirror.isOrthographicCamera) {
      q.set((Math.sign(clipPlane.x) + p[8]) / p[0], (Math.sign(clipPlane.y) + p[9]) / p[5], -mirror.far, 1);
    } else {
      q.set((Math.sign(clipPlane.x) + p[8]) / p[0], (Math.sign(clipPlane.y) + p[9]) / p[5], -1, (1 + p[10]) / p[14]);
    }
    clipPlane.multiplyScalar(2 / clipPlane.dot(q));
    p[2] = clipPlane.x;
    p[6] = clipPlane.y;
    if (mirror.isOrthographicCamera) {
      p[10] = clipPlane.z;
      p[14] = clipPlane.w - 1;
    } else {
      p[10] = clipPlane.z + 1;
      p[14] = clipPlane.w;
    }
    mirror.projectionMatrixInverse.copy(mirror.projectionMatrix).invert();
    return mirror;
  }

  function pass(renderer, fullScreen, into) {
    renderer.setRenderTarget(into);
    renderer.render(fullScreen.scene, passCamera);
  }

  // Aim a Gaussian pass across `from`, or down it: taps a quarter sigma apart, so the 17
  // taps span two sigmas either side.
  function aim(fullScreen, from, sigma, down) {
    fullScreen.uniforms.uInput.value = from.texture;
    fullScreen.uniforms.uStep.value.set(down ? 0 : sigma / 4 / state.width, down ? sigma / 4 / state.heightPx : 0);
  }

  function blurInto(renderer, from, via, into, sigma) {
    aim(blurPass, from, sigma, false);
    pass(renderer, blurPass, via);
    aim(blurPass, via, sigma, true);
    pass(renderer, blurPass, into);
  }

  function draw(renderer, scene, camera, hidden) {
    const mirror = placeMirror(camera);
    viewProjection.multiplyMatrices(mirror.projectionMatrix, mirror.matrixWorldInverse);
    uniforms.uReflectionMatrix.value.copy(viewProjection);
    inverse.copy(viewProjection).invert();
    for (const fullScreen of [prep, combine]) fullScreen.uniforms.uFloorZ.value = state.floorZ;
    prep.uniforms.uFadeHeight.value = Math.max(state.height * fadeHeight, 1e-6);
    combine.uniforms.uBlurHeight.value = Math.max(state.height * blurHeight, 1e-6);

    const shadowMap = renderer.shadowMap;
    const saved = {
      target: renderer.getRenderTarget(),
      autoClear: renderer.autoClear,
      clearAlpha: renderer.getClearAlpha(),
      background: scene.background,
      matrixAuto: scene.matrixWorldAutoUpdate,
      visible: hidden.map((object) => object.visible)
    };
    renderer.getClearColor(clearColor);
    for (const object of hidden) object.visible = false;
    scene.background = null;
    // The frame has just updated every matrix.
    scene.matrixWorldAutoUpdate = false;
    try {
      renderer.setRenderTarget(mirrored);
      renderer.setClearColor(0x000000, 0);
      renderer.autoClear = false;
      renderer.state.buffers.depth.setMask(true);
      renderer.clear(true, true, false);
      // Drawn as the frame is drawn: three draws into an XR target as into the canvas, with
      // its tone mapping and colour space. Three keys each material's program on both, and
      // a target drawn any other way would switch every material's program twice a frame.
      mirrored.isXRRenderTarget = saved.target === null || saved.target.isXRRenderTarget === true;
      mirrored.texture.colorSpace = saved.target ? saved.target.texture.colorSpace : renderer.outputColorSpace;
      renderer.render(scene, mirror);
      mirrored.isXRRenderTarget = false;
      // Any shadows due this frame were rendered by that draw: the frame keeps them.
      shadowMap.needsUpdate = false;
      pass(renderer, prep, sharp);
      // The scene's colour is spent once faded: it carries the blurs' halfway passes.
      if (sharpBlur > 0) blurInto(renderer, sharp, mirrored, sharp, sharpBlur);
      aim(blurPass, sharp, blur, false);
      pass(renderer, blurPass, mirrored);
      aim(combine, mirrored, blur, true);
      pass(renderer, combine, combined);
    } finally {
      mirrored.isXRRenderTarget = false;
      hidden.forEach((object, index) => { object.visible = saved.visible[index]; });
      scene.background = saved.background;
      scene.matrixWorldAutoUpdate = saved.matrixAuto;
      renderer.setClearColor(clearColor, saved.clearAlpha);
      renderer.autoClear = saved.autoClear;
      renderer.setRenderTarget(saved.target);
      if (camera.viewport) renderer.state.viewport(camera.viewport);
    }
    uniforms.uReflectionReady.value = 1;
    state.ready = true;
  }

  return {
    uniforms,
    /** Add the reflection to the floor's shader (call from its onBeforeCompile). */
    patch(shader) {
      Object.assign(shader.uniforms, uniforms);
      shader.vertexShader = shader.vertexShader
        .replace("#include <common>", `#include <common>\n${FLOOR_VERTEX_PARS}`)
        .replace("#include <fog_vertex>", `#include <fog_vertex>\n${FLOOR_VERTEX}`);
      shader.fragmentShader = shader.fragmentShader
        .replace("#include <common>", `#include <common>\n${FLOOR_FRAGMENT_PARS}`)
        .replace("#include <dithering_fragment>", `${FLOOR_FRAGMENT}\n#include <dithering_fragment>`);
    },
    /** The floor plane's height and how far above it the model reaches. */
    place({ floorZ, height }) {
      if (floorZ !== state.floorZ || height !== state.height) state.sceneChanged = true;
      state.floorZ = floorZ;
      state.height = Math.max(height, 1e-6);
    },
    beforeRender(renderer, scene, camera, hidden = []) {
      eye.setFromMatrixPosition(camera.matrixWorld);
      // Seen from below the floor there is nothing to reflect.
      if (eye.z <= state.floorZ) {
        uniforms.uReflectionReady.value = 0;
        return;
      }
      resize(renderer);
      const key = viewKey(camera);
      // A frame that re-renders shadows is one whose casters changed.
      const shadows = renderer.shadowMap;
      const recast = shadows.enabled === true && (shadows.autoUpdate === true || shadows.needsUpdate === true);
      const changed = !sameView(key) || state.sceneChanged || recast;
      if (!state.ready || changed || schedule.due()) {
        state.lastView = key;
        state.sceneChanged = false;
        draw(renderer, scene, camera, hidden);
        schedule.rendered();
      }
    },
    /** GPU memory of its targets: a half-float colour each, and the mirrored draw's depth. */
    get memoryBytes() {
      return state.width * state.heightPx * (8 * 3 + 4);
    },
    dispose() {
      schedule.dispose();
      depthTexture.dispose();
      for (const renderTarget of [mirrored, sharp, combined]) renderTarget.dispose();
      for (const fullScreen of [prep, blurPass, combine]) {
        fullScreen.mesh.geometry.dispose();
        fullScreen.mesh.material.dispose();
      }
    }
  };
}
