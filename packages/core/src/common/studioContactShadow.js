// The Render studio's floor shadow: where the model meets the floor, a darkening
// that is deepest at contact and fades with height, and the key light's cast
// shadow, crisp near the model and softening into a wide, light penumbra away
// from it. A studio grounds a product this way; a shadow map alone gives one
// hard-edged slab at a single softness.
//
// It is baked into one small texture the floor draws with one texture read, in two
// steps. HEIGHTS: a depth map of the shadow casters rendered UP through the floor by
// a light that is never added to the scene (it lights nothing and no material samples
// it; three's own shadow pass draws it, so it sees exactly what casts the key's shadow:
// visibility, clipping, instancing and deformation included). This is the expensive
// step, a draw of every caster. COMPOSITE: three small full-screen passes that turn
// the heights and the key light's own shadow map into the floor's texture.
//
// Both steps are due once the key's shadows were re-rendered (its shadow pass marks
// them stale: the casters or the key changed), and nothing is due on a frame that
// re-rendered no shadows (one that only moved the camera or changed a highlight). The
// composite then runs on that frame, so the key's cast shadow on the floor follows
// every frame of a moving model. With a `heightInterval` the heights follow a scene
// that keeps changing at most that often, and once more, through `requestFrame`, when
// it stops: what is shown at rest is exact, and while a routine plays or a pose is
// dragged, only the contact darkening lags, by up to that interval. The snapshot
// renderer passes no interval and bakes both steps on every frame that re-renders
// shadows. A floor drawn at zero opacity is not drawn at all, so it bakes nothing.

const PREP_FRAGMENT = /* glsl */ `
uniform sampler2D uContactDepth;
uniform mat4 uContactMatrix;
uniform float uFloorDepth;
uniform sampler2DShadow uKeyMap;
uniform mat4 uKeyMatrix;
uniform float uKeyBias;
uniform float uKeyNormalBias;
uniform float uKeyEnabled;
uniform vec4 uRect;
varying vec2 vUv;

void main() {
  vec3 world = vec3(uRect.xy + (vUv * 2.0 - 1.0) * uRect.z, uRect.w);
  // How close the lowest surface above this floor point is: 1 at the floor, 0 at
  // the top of the contact range or where nothing is above it.
  vec4 contact = uContactMatrix * vec4(world, 1.0);
  float depth = texture2D(uContactDepth, contact.xy).r;
  float near = 1.0 - clamp((depth - uFloorDepth) / max(1.0 - uFloorDepth, 1e-6), 0.0, 1.0);
  // Whether the key light reaches this floor point.
  float blocked = 0.0;
  if (uKeyEnabled > 0.5) {
    vec4 key = uKeyMatrix * vec4(world + vec3(0.0, 0.0, uKeyNormalBias), 1.0);
    key.xyz /= key.w;
    key.z += uKeyBias;
    if (key.x >= 0.0 && key.x <= 1.0 && key.y >= 0.0 && key.y <= 1.0 && key.z <= 1.0) {
      blocked = 1.0 - texture(uKeyMap, key.xyz);
    }
  }
  // R: contact (tight), G: occlusion (broad), B and A: the key's shadow, blurred
  // narrow (B, near the model) and wide (A, away from it).
  gl_FragColor = vec4(near * near * near, near, blocked, blocked);
}
`;

// One separable Gaussian pass, three widths at once: R and B take the narrow
// kernel, A the medium one and G the wide one (sigmas in texels).
const BLUR_FRAGMENT = /* glsl */ `
uniform sampler2D uInput;
uniform vec2 uAxis;
uniform vec3 uSigma;
varying vec2 vUv;

void main() {
  vec2 narrow = vec2(0.0);
  float narrowWeight = 0.0;
  for (int i = -6; i <= 6; i++) {
    float t = float(i) / 3.0;
    float w = exp(-0.5 * t * t);
    narrow += w * texture2D(uInput, vUv + uAxis * t * uSigma.x).rb;
    narrowWeight += w;
  }
  float medium = 0.0;
  float mediumWeight = 0.0;
  for (int i = -12; i <= 12; i++) {
    float t = float(i) / 6.0;
    float w = exp(-0.5 * t * t);
    medium += w * texture2D(uInput, vUv + uAxis * t * uSigma.y).a;
    mediumWeight += w;
  }
  float wide = 0.0;
  float wideWeight = 0.0;
  for (int i = -24; i <= 24; i++) {
    float t = float(i) / 12.0;
    float w = exp(-0.5 * t * t);
    wide += w * texture2D(uInput, vUv + uAxis * t * uSigma.z).g;
    wideWeight += w;
  }
  narrow /= narrowWeight;
  gl_FragColor = vec4(narrow.x, wide / wideWeight, narrow.y, medium / mediumWeight);
}
`;

const PASS_VERTEX = /* glsl */ `
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = vec4(position.xy, 0.0, 1.0);
}
`;

const LAYER_VERTEX = /* glsl */ `
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`;

const LAYER_FRAGMENT = /* glsl */ `
uniform sampler2D uShadow;
uniform float uOpacity;
uniform float uReady;
uniform vec4 uStrength;
varying vec2 vUv;

// Up to one 8-bit level of noise per pixel (three's rand hash). Spread STUDIO_DITHER_SCALE
// times wider about the same mean where each kept pixel averages that scale squared of these.
float ditherNoise(vec2 uv) {
  highp float dt = mod(dot(uv, vec2(12.9898, 78.233)), 3.141592653589793);
#ifdef STUDIO_DITHER_SCALE
  return max((fract(sin(dt) * 43758.5453) - 0.5) * STUDIO_DITHER_SCALE + 0.5, 0.0) / 255.0;
#else
  return fract(sin(dt) * 43758.5453) / 255.0;
#endif
}

void main() {
  vec4 s = texture2D(uShadow, vUv);
  // Occlusion: a tight dark line at contact under a broad, light falloff.
  float occlusion = 1.0 - (1.0 - uStrength.x * s.r) * (1.0 - uStrength.y * s.g);
  // The key's shadow is crisp and full close to the model, soft and light away from it.
  float proximity = smoothstep(0.0, 0.5, s.g);
  float key = mix(s.a, s.b, proximity) * mix(uStrength.w, uStrength.z, proximity);
  float darkness = 1.0 - (1.0 - occlusion) * (1.0 - key);
  // Fade out inside the baked square, so its edge never shows.
  vec2 edge = min(vUv, 1.0 - vUv);
  darkness *= smoothstep(0.0, 0.08, min(edge.x, edge.y));
  float alpha = darkness * uOpacity * uReady;
  // Darkening the floor rounds it to 8 bits again, and a shallow shadow on a dark
  // floor bands. The colour, divided by alpha, is what the blend adds over the floor
  // whatever its colour: exactly this noise, which dithers that rounding (and lifts
  // the shadow by half a level on average).
  gl_FragColor = vec4(vec3(min(ditherNoise(gl_FragCoord.xy + 7.31) / max(alpha, 1e-4), 1.0)), alpha);
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

function bakeTarget(THREE, size) {
  const target = new THREE.WebGLRenderTarget(size, size, {
    type: THREE.HalfFloatType,
    minFilter: THREE.LinearFilter,
    magFilter: THREE.LinearFilter,
    depthBuffer: false,
    generateMipmaps: false
  });
  target.texture.name = "studio-contact-shadow";
  return target;
}

function eachMaterial(object, visit) {
  const materials = Array.isArray(object.material) ? object.material : [object.material];
  for (const material of materials) if (material) visit(material);
}

const defaultNow = () => (typeof performance !== "undefined" && typeof performance.now === "function"
  ? performance.now() : Date.now());

/**
 * How far the floor's dither (and its shadow layer's) is spread: `scale`, a snapshot's render
 * scale. A snapshot draws `scale` times the pixels it keeps and averages each kept pixel over
 * scale² of them, which quiets one level of noise to 1/scale and lets the rounding of what it
 * keeps band again; drawn that much wider, the noise comes back at a level. At 1 (the viewer,
 * which shows its pixels as drawn) nothing is defined, and the shader is the one it always was.
 */
export function syncDitherScale(material, scale) {
  const value = Number(scale) > 1 && Number.isFinite(Number(scale)) ? Number(scale).toFixed(4) : null;
  if ((material.defines?.STUDIO_DITHER_SCALE ?? null) === value) return;
  const defines = { ...material.defines };
  delete defines.STUDIO_DITHER_SCALE;
  if (value) defines.STUDIO_DITHER_SCALE = value;
  material.defines = defines;
  material.needsUpdate = true;
}

/**
 * When stale heights are rendered: at once, or, with an `interval` in milliseconds, no
 * sooner than that after the last time, asking for the frame that will render them
 * (`requestFrame`) so the last change is always rendered. Scheduling only: a test drives
 * it with its own clock (`now`) and timer (`setTimer`, `clearTimer`).
 */
export function createHeightSchedule({
  interval = 0,
  requestFrame = null,
  now = defaultNow,
  setTimer = (callback, ms) => setTimeout(callback, ms),
  clearTimer = (id) => clearTimeout(id)
} = {}) {
  const wait = Math.max(0, Number(interval) || 0);
  let last = -Infinity;
  let timer = null;
  return {
    /** Whether heights may be rendered now. When not, the frame that may is asked for. */
    due() {
      const remaining = last + wait - now();
      // Within a millisecond is due: a timer's clock and `now` need not agree closer.
      if (remaining < 1) return true;
      if (timer === null && typeof requestFrame === "function") {
        timer = setTimer(() => {
          timer = null;
          requestFrame();
        }, remaining);
      }
      return false;
    },
    /** Heights were rendered now: the interval starts again, and a frame asked for them is no longer owed. */
    rendered() {
      last = now();
      if (timer !== null) clearTimer(timer);
      timer = null;
    },
    /** The next heights are due at once. */
    reset() {
      last = -Infinity;
    },
    dispose() {
      if (timer !== null) clearTimer(timer);
      timer = null;
    }
  };
}

/**
 * Create the floor shadow for one photographic studio. `keyLight` is the studio's
 * shadow-casting key. Add `object` to the studio; call `place()` whenever the floor
 * or the model's rest placement moves, and `setOpacity()` with the floor's.
 *
 * `strength` is how dark each part gets at its darkest: contact, broad occlusion,
 * the key's shadow near the model and away from it. `blur` gives the narrow, medium
 * and wide kernels as fractions of the baked square's width.
 *
 * `heightInterval` (milliseconds, default 0: every time) is how often the heights may
 * follow a scene that keeps changing; `requestFrame` asks the caller for a frame (one
 * that need not re-render shadows) to render the heights it deferred. `now`, `setTimer`
 * and `clearTimer` replace the clock and timer, for tests.
 */
export function createStudioContactShadow(THREE, keyLight, {
  size = 512,
  strength = { contact: 0.75, occlusion: 0.5, key: 0.75, keyFar: 0.35 },
  blur = { narrow: 0.012, medium: 0.03, wide: 0.06 },
  heightInterval = 0,
  requestFrame = null,
  now,
  setTimer,
  clearTimer
} = {}) {
  const object = new THREE.Group();
  object.name = "studio-contact-shadow";

  // The light that measures heights, pointed straight up through the floor.
  const light = new THREE.DirectionalLight(0xffffff, 0);
  light.name = "studio-contact-shadow-probe";
  light.castShadow = true;
  light.shadow.bias = 0;
  light.shadow.normalBias = 0;
  light.shadow.mapSize.set(size, size);
  light.target = new THREE.Object3D();
  // A depth texture this module READS: three's own shadow maps compare instead.
  const depthTarget = new THREE.WebGLRenderTarget(size, size, { depthBuffer: true, generateMipmaps: false });
  depthTarget.depthTexture = new THREE.DepthTexture(size, size, THREE.UnsignedIntType);
  depthTarget.depthTexture.minFilter = THREE.NearestFilter;
  depthTarget.depthTexture.magFilter = THREE.NearestFilter;
  light.shadow.map = depthTarget;

  const targets = [bakeTarget(THREE, size), bakeTarget(THREE, size)];
  const passCamera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
  const prep = fullScreenPass(THREE, PREP_FRAGMENT, {
    uContactDepth: { value: depthTarget.depthTexture },
    uContactMatrix: { value: new THREE.Matrix4() },
    uFloorDepth: { value: 0 },
    uKeyMap: { value: null },
    uKeyMatrix: { value: new THREE.Matrix4() },
    uKeyBias: { value: 0 },
    uKeyNormalBias: { value: 0 },
    uKeyEnabled: { value: 0 },
    uRect: { value: new THREE.Vector4(0, 0, 1, 0) }
  });
  const blurPass = fullScreenPass(THREE, BLUR_FRAGMENT, {
    uInput: { value: null },
    uAxis: { value: new THREE.Vector2() },
    uSigma: { value: new THREE.Vector3(blur.narrow * size, blur.medium * size, blur.wide * size) }
  });

  const layer = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.ShaderMaterial({
    uniforms: {
      uShadow: { value: targets[0].texture },
      uOpacity: { value: 1 },
      uReady: { value: 0 },
      uStrength: { value: new THREE.Vector4(strength.contact, strength.occlusion, strength.key, strength.keyFar) }
    },
    vertexShader: LAYER_VERTEX,
    fragmentShader: LAYER_FRAGMENT,
    transparent: true,
    depthWrite: false,
    side: THREE.DoubleSide,
    forceSinglePass: true,
    polygonOffset: true,
    polygonOffsetFactor: 1,
    polygonOffsetUnits: 1
  }));
  layer.name = "studio-contact-shadow-layer";
  // Drawn over the floor (-3), under everything the model draws.
  layer.renderOrder = -2;
  object.add(layer);

  // A shadow caster of zero area: every shadow pass draws it (as does the main pass;
  // it rasterizes nothing in either), so it notices each time the key's shadows are
  // re-rendered, which is when the bake is stale.
  const sentinelGeometry = new THREE.BufferGeometry();
  sentinelGeometry.setAttribute("position", new THREE.BufferAttribute(new Float32Array(9), 3));
  const sentinel = new THREE.Mesh(sentinelGeometry, new THREE.MeshBasicMaterial({ colorWrite: false, depthWrite: false }));
  sentinel.name = "studio-contact-shadow-sentinel";
  sentinel.castShadow = true;
  sentinel.frustumCulled = false;
  object.add(sentinel);

  const schedule = createHeightSchedule({ interval: heightInterval, requestFrame, now, setTimer, clearTimer });
  const state = {
    heightsStale: true, compositeStale: true, heightsReady: false, heightsFloorDepth: 0,
    enabled: true, opacity: 1, rect: null, floorDepth: 0, placement: ""
  };
  const markStale = () => {
    state.heightsStale = true;
    state.compositeStale = true;
  };
  sentinel.onBeforeShadow = (renderer, object3d, camera, shadowCamera) => {
    if (shadowCamera !== light.shadow.camera) markStale();
  };

  function renderHeights(shadowMap, scene, camera) {
    // Seen from below, a single-sided part's underside faces the probe and three's
    // shadow pass would cull it. Draw every caster double-sided for this pass alone,
    // so the map holds each part's lowest surface rather than the inside of its top.
    const sides = [];
    scene.traverse((caster) => {
      if (!caster.castShadow || !caster.material) return;
      eachMaterial(caster, (material) => {
        if (material.side === THREE.DoubleSide || material.shadowSide === THREE.DoubleSide) return;
        sides.push([material, material.shadowSide]);
        material.shadowSide = THREE.DoubleSide;
      });
    });
    const { needsUpdate } = shadowMap;
    shadowMap.needsUpdate = true;
    try {
      shadowMap.render([light], scene, camera);
    } finally {
      for (const [material, side] of sides) material.shadowSide = side;
      shadowMap.needsUpdate = needsUpdate;
    }
    // The composite reads these heights with the placement they were measured at.
    state.heightsFloorDepth = state.floorDepth;
    state.heightsReady = true;
  }

  function composite(renderer, shadowMap) {
    const uniforms = prep.uniforms;
    uniforms.uContactMatrix.value.copy(light.shadow.matrix);
    uniforms.uFloorDepth.value = state.heightsFloorDepth;
    const keyMap = keyLight.shadow?.map?.depthTexture || null;
    uniforms.uKeyEnabled.value = keyLight.visible && keyLight.castShadow && keyMap ? 1 : 0;
    uniforms.uKeyMap.value = keyMap;
    uniforms.uKeyMatrix.value.copy(keyLight.shadow.matrix);
    uniforms.uKeyBias.value = keyLight.shadow.bias;
    uniforms.uKeyNormalBias.value = keyLight.shadow.normalBias;
    uniforms.uRect.value.set(...state.rect);

    const previousTarget = renderer.getRenderTarget();
    const previousAutoClear = renderer.autoClear;
    const previousShadowAutoUpdate = shadowMap.autoUpdate;
    renderer.autoClear = false;
    shadowMap.autoUpdate = false;
    try {
      renderer.setRenderTarget(targets[0]);
      renderer.render(prep.scene, passCamera);
      for (const [from, to, axis] of [[0, 1, [1 / size, 0]], [1, 0, [0, 1 / size]]]) {
        blurPass.uniforms.uInput.value = targets[from].texture;
        blurPass.uniforms.uAxis.value.set(...axis);
        renderer.setRenderTarget(targets[to]);
        renderer.render(blurPass.scene, passCamera);
      }
    } finally {
      renderer.setRenderTarget(previousTarget);
      renderer.autoClear = previousAutoClear;
      shadowMap.autoUpdate = previousShadowAutoUpdate;
    }
    state.compositeStale = false;
    layer.material.uniforms.uReady.value = 1;
  }

  // The bake runs where the floor is drawn, after this frame's shadow pass, so it
  // reads the key's fresh shadow map; a frame that re-rendered no shadows has nothing
  // stale, and a hidden floor (off, or at zero opacity) is not drawn, so bakes nothing.
  layer.onBeforeRender = (renderer, scene, camera) => {
    if (!state.heightsStale && !state.compositeStale) return;
    const shadowMap = renderer.shadowMap;
    if (!state.rect || !shadowMap?.enabled) return;
    if (state.heightsStale && schedule.due()) {
      renderHeights(shadowMap, scene, camera);
      schedule.rendered();
      state.heightsStale = false;
      state.compositeStale = true;
    }
    if (state.compositeStale && state.heightsReady) composite(renderer, shadowMap);
  };

  function showLayer() {
    const visible = state.enabled && state.opacity > 0;
    // Shown again after the scene may have changed unseen: bake it at once.
    if (visible && !layer.visible) {
      markStale();
      schedule.reset();
    }
    layer.visible = visible;
  }

  return {
    object,
    layer,
    sentinel,
    probe: light,
    /**
     * Fit the baked square and the contact range to the model's rest placement and
     * the floor: `center` and `reach` are the centre and half-width of the floor area
     * the shadow may cover, `height` how far above the floor occlusion reaches.
     */
    place({ center, half: reach, floorZ, height }) {
      const placement = [center[0], center[1], reach, floorZ, height].join(",");
      if (placement === state.placement) return;
      state.placement = placement;
      // A margin for the square's faded edge.
      const half = reach * 1.12;
      const range = Math.max(height, 1e-6);
      // The probe sits just below the floor, so geometry touching it is in view.
      const below = range * 0.004;
      state.rect = [center[0], center[1], half, floorZ];
      light.position.set(center[0], center[1], floorZ - below);
      light.target.position.set(center[0], center[1], floorZ + range);
      light.updateMatrixWorld(true);
      light.target.updateMatrixWorld(true);
      const probeCamera = light.shadow.camera;
      probeCamera.left = -half;
      probeCamera.right = half;
      probeCamera.top = half;
      probeCamera.bottom = -half;
      probeCamera.near = 0;
      probeCamera.far = below + range;
      probeCamera.updateProjectionMatrix();
      state.floorDepth = below / (below + range);
      layer.position.set(center[0], center[1], floorZ);
      layer.scale.set(2 * half, 2 * half, 1);
      layer.updateMatrixWorld(true);
      markStale();
    },
    setOpacity(opacity) {
      layer.material.uniforms.uOpacity.value = opacity;
      state.opacity = opacity;
      showLayer();
    },
    setEnabled(enabled) {
      state.enabled = enabled;
      showLayer();
    },
    /** The dither's spread: a snapshot's render scale (`syncDitherScale`). */
    setDitherScale(scale) {
      syncDitherScale(layer.material, scale);
    },
    get stale() {
      return state.heightsStale || state.compositeStale;
    },
    dispose() {
      schedule.dispose();
      object.removeFromParent();
      depthTarget.depthTexture?.dispose();
      depthTarget.dispose();
      for (const target of targets) target.dispose();
      for (const mesh of [prep.mesh, blurPass.mesh, layer, sentinel]) {
        mesh.geometry.dispose();
        mesh.material.dispose();
      }
    }
  };
}
