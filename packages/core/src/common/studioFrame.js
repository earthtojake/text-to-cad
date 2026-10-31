// The Render studio's frame: what one photographic frame is, drawn over three's own draw.
//
// Three draws the studio's scene as it always has, but into a target of this frame's rather
// than the canvas: an XR-flagged target (`isXRRenderTarget`), which three draws exactly as it
// draws the canvas, with its tone mapping and colour space, so every material keeps the one
// program it has on the canvas and in the floor's mirrored draw. Its depth is kept, and three
// small passes read it:
//
//   OCCLUSION  ground-truth ambient occlusion (GTAO, Jimenez et al. 2016, after XeGTAO), at half
//              the drawing buffer's resolution, from the depth alone: the horizon either side of
//              each pixel along a few screen directions, within a radius sized to the model. It is
//              what a studio's broad light cannot reach: the inside of a bore, the seam between a
//              cover and its housing, a bolt head on its plate, a knob in its recess.
//   SMOOTH     a depth-aware blur of that half-resolution occlusion, across and then down.
//   COMPOSITE  the scene's colour, darkened by the occlusion (in linear light, upsampled by
//              depth so it never bleeds across a silhouette), blended into an accumulation.
//
// and a last pass copies the accumulation to whatever the frame was drawn for (the canvas).
//
// A still view CONVERGES. A frame that follows the last with nothing changed (the caller says
// so: `still`) is the next SAMPLE of the same picture: the camera is moved by a fraction of a
// pixel (a Halton sequence), the occlusion's directions are turned, and the studio may move its
// key light across its softbox (`onSample`), and the frame is averaged into the ones before it.
// After `samples` of them the picture has converged (anti-aliased, its occlusion smooth, its
// shadows soft) and no further frame is owed. Anything else (a camera move, a pose, a routine's
// frame, a setting) starts again from the first sample, which is a whole picture of its own: the
// accumulation only ever refines what is on screen. A moving view therefore pays for one draw
// and the small passes a frame, and the samples only while it rests.

const PASS_VERTEX = /* glsl */ `
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = vec4(position.xy, 0.0, 1.0);
}
`;

const VIEW_GLSL = /* glsl */ `
uniform highp sampler2D uDepth;
uniform mat4 uProjectionInverse;
vec3 viewAt(vec2 uv, float depth) {
  vec4 point = uProjectionInverse * vec4(vec3(uv, depth) * 2.0 - 1.0, 1.0);
  return point.xyz / point.w;
}
float depthAt(vec2 uv) {
  return textureLod(uDepth, uv, 0.0).x;
}
`;

// The horizon-based occlusion of XeGTAO's main pass, in GL's view space. R: visibility (1:
// open, 0: enclosed); G: the pixel's view depth, which the blur and the upsample weigh by
// (0 where nothing was drawn).
const OCCLUSION_FRAGMENT = /* glsl */ `
#define SLICES 3
#define STEPS 4
uniform mat4 uProjection;
uniform vec2 uSize;
uniform float uRadius;
uniform float uMaxPixels;
uniform float uFrame;
uniform float uOrthographic;
varying vec2 vUv;
${VIEW_GLSL}
const float PI = 3.141592653589793;
const float HALF_PI = 1.5707963267948966;

// Interleaved gradient noise (Jimenez 2014), moved on each sample of an accumulation.
float noiseAt(vec2 pixel, float frame) {
  pixel += 5.588238 * frame;
  return fract(52.9829189 * fract(dot(pixel, vec2(0.06711056, 0.00583715))));
}

// A full-resolution pixel's centre: a depth is read from one pixel, and the point it places
// must be that pixel's own, or a sloped surface reads as a staircase of false horizons.
vec2 pixelCentre(vec2 uv) {
  return (floor(uv * uSize) + 0.5) / uSize;
}

void main() {
  vec2 uv = pixelCentre(vUv);
  float depth = depthAt(uv);
  if (depth >= 1.0) {
    gl_FragColor = vec4(1.0, 0.0, 0.0, 1.0);
    return;
  }
  vec3 center = viewAt(uv, depth);
  // The surface's normal from its depth: on each axis, the neighbour on the same surface (the
  // nearer depth), so a silhouette never tilts it.
  vec2 texel = 1.0 / uSize;
  float left = depthAt(uv - vec2(texel.x, 0.0));
  float right = depthAt(uv + vec2(texel.x, 0.0));
  float below = depthAt(uv - vec2(0.0, texel.y));
  float above = depthAt(uv + vec2(0.0, texel.y));
  vec3 alongX = abs(left - depth) < abs(right - depth)
    ? center - viewAt(uv - vec2(texel.x, 0.0), left) : viewAt(uv + vec2(texel.x, 0.0), right) - center;
  vec3 alongY = abs(below - depth) < abs(above - depth)
    ? center - viewAt(uv - vec2(0.0, texel.y), below) : viewAt(uv + vec2(0.0, texel.y), above) - center;
  vec3 viewVec = uOrthographic > 0.5 ? vec3(0.0, 0.0, 1.0) : normalize(-center);
  vec3 normal = normalize(cross(alongX, alongY));
  if (dot(normal, viewVec) < 0.0) normal = -normal;

  // The radius on screen at this depth, held to a share of the view so a close-up's samples
  // stay coherent; the falloff follows the radius actually searched.
  float pixelSize = (uOrthographic > 0.5 ? 1.0 : -center.z) * 2.0 / (uProjection[1][1] * uSize.y);
  float radiusPixels = min(uRadius / pixelSize, uMaxPixels);
  if (radiusPixels < 2.0) {
    gl_FragColor = vec4(1.0, -center.z, 0.0, 1.0);
    return;
  }
  float radius = radiusPixels * pixelSize;
  float falloffRange = 0.615 * radius;
  float falloffMul = -1.0 / falloffRange;
  float falloffAdd = (radius - falloffRange) / falloffRange + 1.0;

  float sliceNoise = noiseAt(gl_FragCoord.xy, uFrame);
  float stepNoise = noiseAt(gl_FragCoord.yx + vec2(13.0, 71.0), uFrame + 0.5);
  float visibility = 0.0;
  for (int slice = 0; slice < SLICES; slice++) {
    float phi = (float(slice) + sliceNoise) * PI / float(SLICES);
    vec2 omega = vec2(cos(phi), sin(phi));
    vec3 direction = vec3(omega, 0.0);
    vec3 orthoDirection = direction - dot(direction, viewVec) * viewVec;
    vec3 axis = normalize(cross(orthoDirection, viewVec));
    vec3 projectedNormal = normal - axis * dot(normal, axis);
    float projectedLength = length(projectedNormal);
    float cosNormal = clamp(dot(projectedNormal, viewVec) / max(projectedLength, 1e-5), 0.0, 1.0);
    float n = sign(dot(orthoDirection, projectedNormal)) * acos(cosNormal);
    float low0 = cos(n + HALF_PI);
    float low1 = cos(n - HALF_PI);
    float horizon0 = low0;
    float horizon1 = low1;
    for (int step = 0; step < STEPS; step++) {
      float jitter = fract(stepNoise + float(slice * STEPS + step) * 0.6180339887);
      float s = (float(step) + jitter) / float(STEPS);
      s = s * s + 1.5 / radiusPixels;
      vec2 offset = omega * (s * radiusPixels) * texel;
      vec2 uv0 = pixelCentre(uv + offset);
      vec2 uv1 = pixelCentre(uv - offset);
      vec3 delta0 = viewAt(uv0, depthAt(uv0)) - center;
      vec3 delta1 = viewAt(uv1, depthAt(uv1)) - center;
      float distance0 = max(length(delta0), 1e-6);
      float distance1 = max(length(delta1), 1e-6);
      float weight0 = clamp(distance0 * falloffMul + falloffAdd, 0.0, 1.0);
      float weight1 = clamp(distance1 * falloffMul + falloffAdd, 0.0, 1.0);
      horizon0 = max(horizon0, mix(low0, dot(delta0 / distance0, viewVec), weight0));
      horizon1 = max(horizon1, mix(low1, dot(delta1 / distance1, viewVec), weight1));
    }
    projectedLength = mix(projectedLength, 1.0, 0.05);
    float h0 = -acos(clamp(horizon1, -1.0, 1.0));
    float h1 = acos(clamp(horizon0, -1.0, 1.0));
    h0 = n + clamp(h0 - n, -HALF_PI, HALF_PI);
    h1 = n + clamp(h1 - n, -HALF_PI, HALF_PI);
    float arc0 = (cosNormal + 2.0 * h0 * sin(n) - cos(2.0 * h0 - n)) / 4.0;
    float arc1 = (cosNormal + 2.0 * h1 * sin(n) - cos(2.0 * h1 - n)) / 4.0;
    visibility += projectedLength * (arc0 + arc1);
  }
  gl_FragColor = vec4(clamp(visibility / float(SLICES), 0.0, 1.0), -center.z, 0.0, 1.0);
}
`;

// One axis of a depth-aware Gaussian over the half-resolution occlusion: a neighbour on
// another surface (a different depth, relative to this one's) counts for nothing.
const SMOOTH_FRAGMENT = /* glsl */ `
uniform sampler2D uInput;
uniform vec2 uStep;
varying vec2 vUv;
void main() {
  vec4 center = texture2D(uInput, vUv);
  if (center.g <= 0.0) {
    gl_FragColor = center;
    return;
  }
  float sum = center.r;
  float total = 1.0;
  for (int i = -4; i <= 4; i++) {
    if (i == 0) continue;
    vec4 tap = texture2D(uInput, vUv + uStep * float(i));
    float t = float(i) / 2.5;
    float weight = tap.g > 0.0 ? exp(-0.5 * t * t) * exp(-abs(tap.g - center.g) / (center.g * 0.02)) : 0.0;
    sum += tap.r * weight;
    total += weight;
  }
  gl_FragColor = vec4(sum / total, center.g, 0.0, 1.0);
}
`;

// The scene's colour (display-referred: tone mapped and sRGB-encoded, as three drew it) under
// the occlusion, applied in linear light. The half-resolution occlusion is upsampled by depth:
// of the four texels around this pixel, those on its own surface carry it.
const COMPOSITE_FRAGMENT = /* glsl */ `
uniform sampler2D uColor;
uniform sampler2D uOcclusion;
uniform vec2 uOcclusionSize;
uniform float uStrength;
uniform float uPower;
varying vec2 vUv;
${VIEW_GLSL}
vec3 toLinear(vec3 c) {
  return mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)), step(vec3(0.04045), c));
}
vec3 toDisplay(vec3 c) {
  return mix(c * 12.92, 1.055 * pow(c, vec3(1.0 / 2.4)) - 0.055, step(vec3(0.0031308), c));
}
void main() {
  vec4 color = texture2D(uColor, vUv);
  float depth = depthAt(vUv);
  float visibility = 1.0;
  if (depth < 1.0 && uStrength > 0.0) {
    float z = -viewAt(vUv, depth).z;
    vec2 at = vUv * uOcclusionSize - 0.5;
    vec2 f = fract(at);
    ivec2 base = ivec2(floor(at));
    ivec2 last = ivec2(uOcclusionSize) - 1;
    float sum = 0.0;
    float total = 0.0;
    for (int y = 0; y < 2; y++) {
      for (int x = 0; x < 2; x++) {
        vec4 tap = texelFetch(uOcclusion, clamp(base + ivec2(x, y), ivec2(0), last), 0);
        float bilinear = (x == 0 ? 1.0 - f.x : f.x) * (y == 0 ? 1.0 - f.y : f.y);
        float weight = tap.g > 0.0 ? (bilinear + 1e-3) * exp(-abs(tap.g - z) / (z * 0.02)) : 0.0;
        sum += tap.r * weight;
        total += weight;
      }
    }
    if (total > 1e-5) visibility = pow(sum / total, uPower);
    visibility = mix(1.0, visibility, uStrength);
  }
  gl_FragColor = vec4(toDisplay(toLinear(color.rgb) * visibility), color.a);
}
`;

// The accumulation out to the frame's own target, dithered by up to a level of the 8-bit
// canvas it lands in: an average of many samples has gradients finer than one, and rounding
// would band them.
const OUTPUT_FRAGMENT = /* glsl */ `
uniform sampler2D uAccumulation;
varying vec2 vUv;
float hash(vec2 p) {
  return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453);
}
void main() {
  vec4 color = texture2D(uAccumulation, vUv);
  float noise = (hash(gl_FragCoord.xy) + hash(gl_FragCoord.yx + 19.19) - 1.0) / 255.0;
  gl_FragColor = vec4(color.rgb + noise * color.a, color.a);
}
`;

/** How far the model may move on screen, in pixels, and a still frame still sample its picture. */
export const STUDIO_FRAME_DRIFT_PIXELS = 0.25;

/** The Halton sequence's `index`th value in `base` (index from 1), in [0, 1). */
export function halton(index, base) {
  let result = 0;
  let fraction = 1 / base;
  let value = index;
  while (value > 0) {
    result += fraction * (value % base);
    value = Math.floor(value / base);
    fraction /= base;
  }
  return result;
}

/**
 * Where sample `index` of an accumulation puts the camera, in drawing-buffer pixels: the
 * first (0) where it is, every other a fraction of a pixel away (Halton 2, 3), so averaged
 * samples cover each pixel's area evenly.
 */
export function studioFrameJitter(index) {
  if (!(index > 0)) return [0, 0];
  return [halton(index, 2) - 0.5, halton(index, 3) - 0.5];
}

function fullScreenPass(THREE, fragmentShader, uniforms, material = {}) {
  const geometry = new THREE.BufferGeometry();
  // One triangle over the whole target: no diagonal seam for a filter to straddle.
  geometry.setAttribute("position", new THREE.Float32BufferAttribute([-1, -1, 0, 3, -1, 0, -1, 3, 0], 3));
  geometry.setAttribute("uv", new THREE.Float32BufferAttribute([0, 0, 2, 0, 0, 2], 2));
  const mesh = new THREE.Mesh(geometry, new THREE.ShaderMaterial({
    uniforms,
    vertexShader: PASS_VERTEX,
    fragmentShader,
    depthTest: false,
    depthWrite: false,
    blending: THREE.NoBlending,
    toneMapped: false,
    ...material
  }));
  mesh.frustumCulled = false;
  const scene = new THREE.Scene();
  scene.add(mesh);
  return { mesh, scene, uniforms: mesh.material.uniforms };
}

function passTarget(THREE, name) {
  const target = new THREE.WebGLRenderTarget(1, 1, {
    type: THREE.HalfFloatType,
    minFilter: THREE.NearestFilter,
    magFilter: THREE.NearestFilter,
    depthBuffer: false,
    generateMipmaps: false
  });
  target.texture.name = name;
  return target;
}

/**
 * Create the frame for one photographic studio.
 *
 * `samples` is how many samples a still view converges over (1: no accumulation, each frame
 * is its own picture). `multisample` is the scene target's MSAA sample count, as the canvas
 * it replaces has (0 where the caller supersamples instead: a snapshot at its render scale).
 * `occlusion` is the ambient occlusion's `strength` (0: none, 1: all of it), its `radius` as a
 * share of the model's (bounds) radius, its `power` (contrast) and `maxScreen`, the largest
 * share of the view's height its radius may span. `onSample(index, renderer, context)` is
 * called before each sample is drawn, so the studio can place its key light for it (0: at
 * rest); `context.castersChanged` says whether this frame may have moved a shadow caster.
 * `afterSample()` follows the draw.
 */
export function createStudioFrame(THREE, {
  samples = 32,
  multisample = 4,
  occlusion = {},
  onSample = null,
  afterSample = null
} = {}) {
  const settings = {
    samples: Math.max(1, Math.round(samples)),
    strength: 1,
    radius: 0.1,
    power: 2,
    maxScreen: 0.2,
    modelRadius: 1,
    ...occlusion
  };

  const depthTexture = new THREE.DepthTexture(1, 1, THREE.UnsignedInt248Type);
  depthTexture.format = THREE.DepthStencilFormat;
  depthTexture.minFilter = THREE.NearestFilter;
  depthTexture.magFilter = THREE.NearestFilter;
  // The scene, drawn as the canvas is: 8-bit display colour (the canvas's), its depth kept.
  const sceneTarget = new THREE.WebGLRenderTarget(1, 1, {
    type: THREE.UnsignedByteType,
    minFilter: THREE.NearestFilter,
    magFilter: THREE.NearestFilter,
    depthBuffer: true,
    stencilBuffer: true,
    depthTexture,
    samples: Math.max(0, Math.round(multisample)),
    generateMipmaps: false
  });
  sceneTarget.texture.name = "studio-frame-scene";
  sceneTarget.texture.internalFormat = "RGBA8";
  sceneTarget.isXRRenderTarget = true;
  const occlusionTargets = [passTarget(THREE, "studio-frame-occlusion"), passTarget(THREE, "studio-frame-occlusion-smooth")];
  const accumulation = passTarget(THREE, "studio-frame-accumulation");

  const passCamera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
  const projection = new THREE.Matrix4();
  const projectionInverse = new THREE.Matrix4();
  const occlusionPass = fullScreenPass(THREE, OCCLUSION_FRAGMENT, {
    uDepth: { value: depthTexture },
    uProjection: { value: projection },
    uProjectionInverse: { value: projectionInverse },
    uSize: { value: new THREE.Vector2(1, 1) },
    uRadius: { value: 1 },
    uMaxPixels: { value: 64 },
    uFrame: { value: 0 },
    uOrthographic: { value: 0 }
  });
  const smoothPass = fullScreenPass(THREE, SMOOTH_FRAGMENT, {
    uInput: { value: null },
    uStep: { value: new THREE.Vector2() }
  });
  // Each sample is blended into the accumulation at 1 / (its index + 1): the first replaces
  // what was there, the nth is an nth of the average.
  const compositePass = fullScreenPass(THREE, COMPOSITE_FRAGMENT, {
    uColor: { value: sceneTarget.texture },
    uDepth: { value: depthTexture },
    uProjectionInverse: { value: projectionInverse },
    uOcclusion: { value: occlusionTargets[0].texture },
    uOcclusionSize: { value: new THREE.Vector2(1, 1) },
    uStrength: { value: 1 },
    uPower: { value: 1 }
  }, {
    blending: THREE.CustomBlending,
    blendEquation: THREE.AddEquation,
    blendSrc: THREE.ConstantAlphaFactor,
    blendDst: THREE.OneMinusConstantAlphaFactor,
    blendEquationAlpha: THREE.AddEquation,
    blendSrcAlpha: THREE.ConstantAlphaFactor,
    blendDstAlpha: THREE.OneMinusConstantAlphaFactor,
    blendAlpha: 1
  });
  const outputPass = fullScreenPass(THREE, OUTPUT_FRAGMENT, {
    uAccumulation: { value: accumulation.texture }
  });

  const state = { index: 0, width: 0, height: 0, disposed: false };
  const size = new THREE.Vector2();
  // The view the picture's samples are of (its first's), and points of the model the camera's
  // drift since then is measured at.
  const anchor = new THREE.Matrix4();
  const viewProjection = new THREE.Matrix4();
  const probes = [];
  const anchored = new THREE.Vector4();
  const current = new THREE.Vector4();
  placeProbes([0, 0, 0], 1);

  function placeProbes(center, radius) {
    probes.length = 0;
    const reach = radius / Math.sqrt(3);
    probes.push(new THREE.Vector4(center[0], center[1], center[2], 1));
    for (const x of [-1, 1]) for (const y of [-1, 1]) for (const z of [-1, 1]) {
      probes.push(new THREE.Vector4(center[0] + x * reach, center[1] + y * reach, center[2] + z * reach, 1));
    }
  }

  // How far, in drawing-buffer pixels, the model has moved on screen since the picture's first
  // sample. The tail of a damped orbit moves the camera by ever less for a second or more after
  // the hand lets go: a fraction of a pixel is still the same picture.
  // A point behind the camera (a close-up from inside the model's bounds) says nothing; with
  // none in front, any change of the view is a move.
  function drift() {
    let most = 0;
    let seen = 0;
    for (const probe of probes) {
      anchored.copy(probe).applyMatrix4(anchor);
      current.copy(probe).applyMatrix4(viewProjection);
      if (!(anchored.w > 0) || !(current.w > 0)) continue;
      seen += 1;
      most = Math.max(most,
        Math.abs(current.x / current.w - anchored.x / anchored.w) * state.width / 2,
        Math.abs(current.y / current.w - anchored.y / anchored.w) * state.height / 2);
    }
    if (seen > 0) return most;
    return viewProjection.equals(anchor) ? 0 : Infinity;
  }

  function resize(renderer) {
    renderer.getDrawingBufferSize(size);
    const width = Math.max(1, Math.round(size.x));
    const height = Math.max(1, Math.round(size.y));
    if (width === state.width && height === state.height) return false;
    state.width = width;
    state.height = height;
    sceneTarget.setSize(width, height);
    const halfWidth = Math.max(1, Math.ceil(width / 2));
    const halfHeight = Math.max(1, Math.ceil(height / 2));
    for (const target of occlusionTargets) target.setSize(halfWidth, halfHeight);
    accumulation.setSize(width, height);
    occlusionPass.uniforms.uSize.value.set(width, height);
    compositePass.uniforms.uOcclusionSize.value.set(halfWidth, halfHeight);
    return true;
  }

  function pass(renderer, fullScreen, into) {
    renderer.setRenderTarget(into);
    renderer.render(fullScreen.scene, passCamera);
  }

  // Draw the scene for sample `index`: its camera a fraction of a pixel away for every sample
  // but the first, and left exactly as it was.
  function drawScene(renderer, scene, camera, index) {
    const [jitterX, jitterY] = studioFrameJitter(index);
    const savedView = camera.view ? { ...camera.view } : null;
    if (index > 0) camera.setViewOffset(state.width, state.height, jitterX, jitterY, state.width, state.height);
    try {
      sceneTarget.texture.colorSpace = renderer.outputColorSpace;
      renderer.setRenderTarget(sceneTarget);
      renderer.render(scene, camera);
      projection.copy(camera.projectionMatrix);
      projectionInverse.copy(camera.projectionMatrixInverse);
    } finally {
      if (index > 0) {
        if (savedView?.enabled) {
          camera.setViewOffset(savedView.fullWidth, savedView.fullHeight, savedView.offsetX, savedView.offsetY,
            savedView.width, savedView.height);
        } else {
          camera.clearViewOffset();
        }
      }
    }
  }

  function drawOcclusion(renderer, camera, index) {
    const uniforms = occlusionPass.uniforms;
    uniforms.uRadius.value = Math.max(settings.modelRadius * settings.radius, 1e-9);
    uniforms.uMaxPixels.value = Math.max(state.height * settings.maxScreen, 4);
    uniforms.uFrame.value = index % 64;
    uniforms.uOrthographic.value = camera.isOrthographicCamera ? 1 : 0;
    pass(renderer, occlusionPass, occlusionTargets[0]);
    const [first, second] = occlusionTargets;
    smoothPass.uniforms.uInput.value = first.texture;
    smoothPass.uniforms.uStep.value.set(1 / first.width, 0);
    pass(renderer, smoothPass, second);
    smoothPass.uniforms.uInput.value = second.texture;
    smoothPass.uniforms.uStep.value.set(0, 1 / first.height);
    pass(renderer, smoothPass, first);
  }

  function output(renderer, target) {
    renderer.setRenderTarget(target);
    renderer.render(outputPass.scene, passCamera);
  }

  return {
    get samples() { return settings.samples; },
    /** The index of the sample the next still frame draws (0: a new picture). */
    get sample() { return state.index; },
    /** Whether the picture on screen is every sample it will have. */
    get converged() { return state.index >= settings.samples; },
    /**
     * The model's (rest) bounds: its radius, which the occlusion's radius is a share of, and
     * its centre, about which a camera's drift is measured.
     */
    place({ radius, center = [0, 0, 0] }) {
      const next = Math.max(Number(radius) || 0, 1e-9);
      if (next !== settings.modelRadius) state.index = 0;
      settings.modelRadius = next;
      placeProbes(center.map((value) => Number(value) || 0), next);
    },
    /** Change how many samples a still view converges over, or the occlusion. */
    configure({ samples: count, occlusion: patch } = {}) {
      if (count != null) settings.samples = Math.max(1, Math.round(count));
      if (patch) Object.assign(settings, patch);
      state.index = 0;
    },
    /** Start the next frame from its first sample. */
    reset() {
      state.index = 0;
    },
    /**
     * Draw one frame of `scene` from `camera` to the renderer's current target (the canvas,
     * or a caller's own). `still`: nothing but the camera has changed since the last frame it
     * drew, so it may be the next sample of that picture; it is, unless the camera has moved
     * the model by more than `STUDIO_FRAME_DRIFT_PIXELS` since the picture began. `present: false`
     * leaves the accumulation unpresented (a snapshot presents only its last sample). Answers
     * whether more samples are owed: the caller asks for another still frame while they are.
     */
    render(renderer, scene, camera, { still = false, present = true } = {}) {
      if (state.disposed) throw new Error("The studio frame was disposed");
      const target = renderer.getRenderTarget();
      const autoClear = renderer.autoClear;
      const resized = resize(renderer);
      camera.updateMatrixWorld();
      viewProjection.multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse);
      if (!still || resized || drift() > STUDIO_FRAME_DRIFT_PIXELS) state.index = 0;
      if (state.index === 0) anchor.copy(viewProjection);
      if (state.index >= settings.samples) {
        // Converged and unchanged: what is accumulated is the picture.
        if (present) output(renderer, target);
        return { refining: false, sample: state.index };
      }
      const index = state.index;
      const shadowMap = renderer.shadowMap;
      onSample?.(index, renderer, {
        castersChanged: !still && Boolean(shadowMap?.enabled && (shadowMap.autoUpdate || shadowMap.needsUpdate))
      });
      try {
        renderer.autoClear = true;
        drawScene(renderer, scene, camera, index);
      } finally {
        afterSample?.(index);
      }
      try {
        renderer.autoClear = false;
        if (settings.strength > 0) drawOcclusion(renderer, camera, index);
        compositePass.uniforms.uStrength.value = settings.strength;
        compositePass.uniforms.uPower.value = settings.power;
        compositePass.mesh.material.blendAlpha = 1 / (index + 1);
        pass(renderer, compositePass, accumulation);
        if (present) output(renderer, target);
      } finally {
        renderer.autoClear = autoClear;
        renderer.setRenderTarget(target);
      }
      state.index = index + 1;
      return { refining: state.index < settings.samples, sample: index };
    },
    /**
     * A still picture, converged: every sample drawn now, back to back, and presented once.
     * A snapshot's frame.
     */
    renderStill(renderer, scene, camera, { samples: count = settings.samples } = {}) {
      const total = Math.max(1, Math.round(count));
      const previous = settings.samples;
      const shadowMap = renderer.shadowMap;
      const autoUpdate = shadowMap?.autoUpdate;
      settings.samples = total;
      try {
        for (let index = 0; index < total; index += 1) {
          // The first sample renders the shadows the scene casts; the rest re-render them only
          // when a sample moves the key (`onSample` asks), as the viewer's frames do.
          if (index === 1 && shadowMap) shadowMap.autoUpdate = false;
          this.render(renderer, scene, camera, { still: index > 0, present: index === total - 1 });
        }
      } finally {
        settings.samples = previous;
        if (shadowMap) shadowMap.autoUpdate = autoUpdate;
      }
    },
    /** GPU memory of its targets, in bytes. */
    get memoryBytes() {
      const pixels = state.width * state.height;
      const multisample = Math.max(1, sceneTarget.samples);
      const half = occlusionTargets[0].width * occlusionTargets[0].height;
      // Colour and depth-stencil, multisampled and resolved; two half-resolution and one full
      // half-float target.
      return pixels * 8 * (multisample + (sceneTarget.samples > 0 ? 1 : 0)) + half * 8 * 2 + pixels * 8;
    },
    dispose() {
      if (state.disposed) return;
      state.disposed = true;
      depthTexture.dispose();
      sceneTarget.dispose();
      accumulation.dispose();
      for (const target of occlusionTargets) target.dispose();
      for (const fullScreen of [occlusionPass, smoothPass, compositePass, outputPass]) {
        fullScreen.mesh.geometry.dispose();
        fullScreen.mesh.material.dispose();
      }
    }
  };
}
