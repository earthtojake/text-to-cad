// A field's scene: an implicit model drawn by marching it, with no mesh.
//
// The engine answers what the page marches a GSL model with (`GET
// /api/v1/documents/gsl/<id>/field`): a GLSL ES 3.00 library that defines
// `gsl_march` (the first surface along a ray, written by omega's gsl), one
// std140 uniform block carrying time and the model's sliders with the byte
// each sits at, the textures the field reads, and the box to march. This
// builds the kit scene of it (`viewer/sceneContract.js`): one triangle that
// covers the view, whose fragment shader casts a ray for its pixel through the
// camera three draws with, marches the field along it, shades what it meets
// and writes that point's depth, so the field stands among the stage's own
// objects (grid, ground, ink) as any opaque surface does.
//
// Nothing here knows GSL: the library is taken as it is, and a slider is a
// number written into the block.
//
// A field shown alone shades itself, by one light of its own. One drawn among other surfaces
// (`lit`: an engine document's concepts, `xbf/xbfConcepts.js`) is lit as they are instead: its
// material is three's physical one, whose fragment is given the marched point, normal and depth in
// place of a triangle's, so the stage's lights, its environment, its tone curve and a surface
// model (`setFinish`) reach it as they reach a mesh, and it is drawn see-through where asked.

export const FIELD_SCHEMA_VERSION = 1;

// The block's members by their WGSL type: how many floats, as three holds them.
const COMPONENTS = { "f32": 1, "vec2<f32>": 2, "vec3<f32>": 3, "vec4<f32>": 4 };

const VERTEX = "void main() { gl_Position = vec4(position.xy, 0.0, 1.0); }";

// The fragment's own half, after the library: the ray of this pixel in the
// scene's frame, the march, a plain shading of the hit by its gradient, and
// its depth. A perspective ray is measured from the eye, an orthographic one
// from its own point on the near plane; `pixelScale` is the size of a pixel a
// unit from the eye (of every pixel, orthographic), which the march's
// tolerances follow.
// A section's planes, for a field: what stands behind one (its negative side) is cut away. A ray is
// kept to the part of it in front of every plane, and where it enters through a plane into the solid
// (the field below zero there) the cut itself is what it meets: `cap` is that plane's normal, else zero.
// The planes are given in the field's own frame (`writeFieldClip`). A library without `gsl_field`
// (an older gsl's) is cut and not capped.
export const FIELD_CLIP_PLANES = 4;
export const FIELD_CLIP_GLSL = `
uniform vec4 uClip[${FIELD_CLIP_PLANES}];
uniform int uClipCount;
bool fieldClipped(vec3 origin, vec3 direction, inout float tEntry, inout float tExit, out vec3 cap) {
  cap = vec3(0.0);
  for (int i = 0; i < ${FIELD_CLIP_PLANES}; i++) {
    if (i >= uClipCount) { break; }
    float side = dot(uClip[i].xyz, origin) + uClip[i].w;
    float along = dot(uClip[i].xyz, direction);
    if (abs(along) < 1e-9) { if (side < 0.0) { return true; } continue; }
    float t = -side / along;
    if (along > 0.0) { if (t > tEntry) { tEntry = t; cap = uClip[i].xyz; } } else { tExit = min(tExit, t); }
  }
  return uClipCount > 0 && tExit <= tEntry;
}
`;

/** The uniforms `FIELD_CLIP_GLSL` reads, none cutting. */
export function fieldClipUniforms(THREE) {
  return { uClip: { value: Array.from({ length: FIELD_CLIP_PLANES }, () => new THREE.Vector4()) }, uClipCount: { value: 0 } };
}

/** Write `planes` (three's, the scene's coordinates) into a field's clip uniforms, in the frame `toLocal` takes the scene to. */
export function writeFieldClip(THREE, uniforms, planes, toLocal) {
  const given = (planes || []).slice(0, FIELD_CLIP_PLANES);
  const normalMatrix = new THREE.Matrix3().getNormalMatrix(toLocal);
  given.forEach((plane, at) => {
    const local = plane.clone().applyMatrix4(toLocal, normalMatrix);
    uniforms.uClip.value[at].set(local.normal.x, local.normal.y, local.normal.z, local.constant);
  });
  uniforms.uClipCount.value = given.length;
}

// The surface this pixel's ray meets, in the scene's frame: where, its normal, the ray's direction
// and its body. A pixel whose ray meets none is discarded; one that meets it writes its depth.
const SURFACE = `
uniform mat4 uProjectionInverse;
uniform mat4 uCameraToScene;
uniform mat4 uSceneToClip;
uniform mat4 uSceneToView;
uniform vec4 uViewport;
uniform vec3 uBoxMin;
uniform vec3 uBoxMax;
uniform float uOrthographic;
uniform float uStepScale;
uniform vec3 uSurface[8];

void fieldSurface(out vec3 point, out vec3 normal, out vec3 direction, out int shape) {
  vec2 ndc = (gl_FragCoord.xy - uViewport.xy) / uViewport.zw * 2.0 - 1.0;
  vec4 nearView = uProjectionInverse * vec4(ndc, -1.0, 1.0);
  vec4 farView = uProjectionInverse * vec4(ndc, 1.0, 1.0);
  vec3 nearPoint = (uCameraToScene * vec4(nearView.xyz / nearView.w, 1.0)).xyz;
  vec3 farPoint = (uCameraToScene * vec4(farView.xyz / farView.w, 1.0)).xyz;
  vec3 eye = (uCameraToScene * vec4(0.0, 0.0, 0.0, 1.0)).xyz;
  direction = normalize(farPoint - nearPoint);
  vec3 origin = mix(eye, nearPoint, uOrthographic);
  vec3 a = (uBoxMin - origin) / direction;
  vec3 b = (uBoxMax - origin) / direction;
  vec3 lower = min(a, b);
  vec3 upper = max(a, b);
  float tEntry = max(max(lower.x, lower.y), lower.z);
  float tExit = min(min(upper.x, upper.y), upper.z);
  float pixelScale = 2.0 * abs(uProjectionInverse[1][1]) / uViewport.w;
  vec3 cap;
  if (fieldClipped(origin, direction, tEntry, tExit, cap)) { discard; }
  float t;
  shape = -1;
#ifdef FIELD_CAPS
  if (cap != vec3(0.0)) {
    // The cut through the solid: the plane itself, facing what was cut away, in its body's colour.
    gsl_shape cut = gsl_field(origin + direction * tEntry);
    if (cut.distance_ < 0.0) { t = tEntry; normal = -cap; shape = int(cut.shapeIndex); }
  }
#endif
  if (shape < 0) {
    gsl_hit hit = gsl_march(origin, direction, tEntry, tExit, pixelScale, uOrthographic, uStepScale, vec4(0.0));
    if (!hit.hit) { discard; }
    t = hit.t;
    normal = normalize(hit.gradient);
    shape = int(hit.shapeIndex);
  }
  point = origin + direction * t;
  vec4 clip = uSceneToClip * vec4(point, 1.0);
  gl_FragDepth = clamp(clip.z / clip.w * 0.5 + 0.5, 0.0, 1.0);
}
`;

// A field shown alone: a plain shading of the surface by its gradient.
const FRAGMENT = `
uniform vec3 uLight;

void main() {
  vec3 point;
  vec3 normal;
  vec3 direction;
  int shape;
  fieldSurface(point, normal, direction, shape);
  float lit = 0.32 + 0.68 * max(dot(normal, uLight), 0.0);
  float rim = 0.12 * pow(1.0 - max(dot(normal, -direction), 0.0), 3.0);
  gl_FragColor = vec4(uSurface[shape % 8] * (lit + rim), 1.0);
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
}
`;

// A field lit as a mesh is: three's physical program (r187's `meshphysical`), its triangle's
// position, normal and colour replaced by the marched surface's. Each line is one replacement of
// three's text, and a three without the text it replaces is refused by name.
const LIT_UNIFORMS = `
uniform float uLift;
uniform float uFlat;
`;
const LIT_FRAGMENT = [
  // The view position is the marched point's, not a varying of the triangle that covers the view.
  ["varying vec3 vViewPosition;", "vec3 vViewPosition;"],
  ["void main() {", `void main() {
  vec3 fieldPoint;
  vec3 fieldNormal;
  vec3 fieldDirection;
  int fieldShape;
  fieldSurface(fieldPoint, fieldNormal, fieldDirection, fieldShape);
  vViewPosition = -(uSceneToView * vec4(fieldPoint, 1.0)).xyz;
  fieldNormal = normalize(mat3(uSceneToView) * fieldNormal);`],
  ["vec4 diffuseColor = vec4( diffuse, opacity );", "vec4 diffuseColor = vec4( uSurface[fieldShape % 8], opacity );"],
  // A section cuts the field along its ray (`fieldClipped`), never the triangle.
  ["#include <clipping_planes_fragment>", ""],
  // The look's lift: a trace of the surface's own colour (`surfaceLook.js`).
  ["vec3 totalEmissiveRadiance = emissive;", "vec3 totalEmissiveRadiance = diffuseColor.rgb * uLift;"],
  ["#include <normal_fragment_begin>", "float faceDirection = 1.0;\n\tvec3 normal = fieldNormal;\n\tvec3 nonPerturbedNormal = normal;"],
  // "Flat": colour without shading.
  ["#include <opaque_fragment>", "if ( uFlat > 0.5 ) { outgoingLight = diffuseColor.rgb; }\n\t#include <opaque_fragment>"]
];
const LIT_VERTEX = [
  ["#include <project_vertex>", "vec4 mvPosition = vec4( transformed, 1.0 );\n\tgl_Position = vec4( position.xy, 0.0, 1.0 );"]
];

function rewritten(text, replacements) {
  for (const [found, put] of replacements) {
    if (!text.includes(found)) throw new Error(`A lit field is drawn by three's physical program, and this three's has no \`${found}\`.`);
    text = text.replace(found, put);
  }
  return text;
}

let litFields = 0;

// The lit field's material: three's physical one over the field's own uniforms and block.
function litMaterial(THREE, uniforms, group, library) {
  const material = new THREE.MeshPhysicalMaterial({ name: "field", side: THREE.FrontSide });
  const id = (litFields += 1);
  let model = null;
  // The field's own uniforms, read as a shader material's are (`xbfConcepts.js`), and its block.
  material.uniforms = uniforms;
  material.uniformsGroups = [group];
  // It dresses itself (`setFinish`): a look that dresses every lit material under a root leaves it alone.
  material.userData.cadOwnLook = true;
  material.onBeforeCompile = (shader, renderer) => {
    Object.assign(shader.uniforms, uniforms);
    shader.vertexShader = rewritten(shader.vertexShader, LIT_VERTEX);
    shader.fragmentShader = `${library}\n${SURFACE}\n${LIT_UNIFORMS}\n${rewritten(shader.fragmentShader, LIT_FRAGMENT)}`;
    model?.onBeforeCompile(shader, renderer);
  };
  material.customProgramCacheKey = () => `field:${id}:${model ? model.customProgramCacheKey() : ""}`;
  return {
    material,
    /** The surface model its lighting is drawn by (`viewer/surfaceBrdf.js`'s), or three's own for none. */
    setModel(next = null) {
      if (model === next) return;
      model = next;
      material.needsUpdate = true;
    }
  };
}

// Each body's colour, by its index (0 is no body): the first a neutral grey, as a part with no
// colour of its own is drawn, the rest told apart.
const SURFACES = [
  [0.72, 0.74, 0.77], [0.72, 0.74, 0.77], [0.86, 0.55, 0.33], [0.36, 0.60, 0.84],
  [0.48, 0.74, 0.47], [0.80, 0.48, 0.66], [0.83, 0.76, 0.40], [0.45, 0.72, 0.74]
];

function assertPayload(payload) {
  if (payload?.schema !== FIELD_SCHEMA_VERSION) {
    throw new Error(`The viewer received a field at schema ${JSON.stringify(payload?.schema)}, but this build of the app reads schema ${FIELD_SCHEMA_VERSION}.`);
  }
  if (payload.target !== "glsl-es300" || typeof payload.code !== "string" || payload.entry?.march !== "gsl_march") {
    throw new Error("The field is not a GLSL ES 3.00 library that defines gsl_march.");
  }
  if (!Array.isArray(payload.region) || payload.region.length !== 6 || !payload.region.every(Number.isFinite)) {
    throw new Error("The field names no box to march.");
  }
}

function texture3d(THREE, described, bytes) {
  const [width, height, depth] = described.size;
  const half = described.format === "r16float";
  const data = half ? new Uint16Array(bytes) : new Uint8Array(bytes);
  if (data.length !== width * height * depth * (half ? 1 : 4)) {
    throw new Error(`The field's texture ${described.name} is ${data.byteLength} bytes, not the ${width} x ${height} x ${depth} of ${described.format} it is described as.`);
  }
  const texture = new THREE.Data3DTexture(data, width, height, depth);
  texture.format = half ? THREE.RedFormat : THREE.RGBAFormat;
  texture.type = half ? THREE.HalfFloatType : THREE.UnsignedByteType;
  texture.minFilter = texture.magFilter = described.filter === "linear" ? THREE.LinearFilter : THREE.NearestFilter;
  texture.wrapS = texture.wrapT = texture.wrapR = THREE.ClampToEdgeWrapping;
  texture.unpackAlignment = 1;
  texture.needsUpdate = true;
  return texture;
}

/**
 * The kit scene of a field (`viewer/sceneContract.js`), from the engine's payload and the bytes of
 * each texture it names.
 *
 * @param {typeof import("three")} THREE
 * @param {object} payload  `GET .../field`'s answer.
 * @param {Record<string, ArrayBuffer>} [textures]  Each texture's raw texels, by its `name`.
 * @param {{ lit?: boolean }} [options]  `lit`: lit by the stage as a mesh is, where it stands among
 *   other surfaces; a field shown alone shades itself.
 * @returns {import("../viewer/sceneContract.js").KitScene & {
 *   parameters: { name: string, value: number, min: number, max: number }[],
 *   parameterValue: (name: string) => number, setParameter: (name: string, value: number) => boolean,
 *   bodyCount: number }}
 */
export function buildFieldScene(THREE, payload, textures = {}, { lit = false } = {}) {
  assertPayload(payload);
  const [x0, y0, z0, x1, y1, z1] = payload.region;

  // The block, its members in the order of their bytes: three lays a group out as std140 does,
  // which is how the payload's offsets were worked out, and each is checked against it below.
  const members = [
    ...(payload.uniforms || []).map((uniform) => ({ ...uniform, slider: null })),
    ...(payload.sliders || []).map((slider) => ({ name: slider.uniform, type: slider.type, offset: slider.offset, value: [slider.value], slider }))
  ].sort((first, second) => first.offset - second.offset);
  const group = new THREE.UniformsGroup();
  group.setName(payload.uniformBlock);
  const sliders = new Map();
  let expected = 0;
  for (const member of members) {
    const count = COMPONENTS[member.type];
    if (!count) throw new Error(`The field's uniform ${member.name} is a ${member.type}, which this viewer cannot bind.`);
    const align = count === 1 ? 4 : count === 2 ? 8 : 16;
    expected = Math.ceil(expected / align) * align;
    if (member.offset !== expected) {
      throw new Error(`The field's uniform ${member.name} is at byte ${member.offset}, where its block's layout puts it at ${expected}.`);
    }
    expected += count * 4;
    const values = member.value.map(Number);
    member.uniform = new THREE.Uniform(count === 1 ? values[0] : count === 2 ? new THREE.Vector2(...values)
      : count === 3 ? new THREE.Vector3(...values) : new THREE.Vector4(...values));
    group.add(member.uniform);
    if (member.slider) sliders.set(member.slider.name, member);
  }

  const uniforms = {
    uProjectionInverse: { value: new THREE.Matrix4() },
    uCameraToScene: { value: new THREE.Matrix4() },
    uSceneToClip: { value: new THREE.Matrix4() },
    uSceneToView: { value: new THREE.Matrix4() },
    uViewport: { value: new THREE.Vector4(0, 0, 1, 1) },
    uBoxMin: { value: new THREE.Vector3(x0, y0, z0) },
    uBoxMax: { value: new THREE.Vector3(x1, y1, z1) },
    uOrthographic: { value: 0 },
    uStepScale: { value: 1 },
    uLight: { value: new THREE.Vector3(0.35, -0.45, 0.82).normalize() },
    uSurface: { value: SURFACES.map((rgb) => new THREE.Vector3(...rgb)) },
    uLift: { value: 0 },
    uFlat: { value: 0 },
    ...fieldClipUniforms(THREE)
  };
  let clipPlanes = [];
  // The model's clock, where its block carries one (`time`): seconds, 0 until something plays it.
  const clock = members.find(member => !member.slider && member.name === "time") || null;
  const made = [];
  for (const described of payload.textures || []) {
    const bytes = textures[described.name];
    if (!bytes) throw new Error(`The field reads the texture ${described.name}, which was not loaded.`);
    const texture = texture3d(THREE, described, bytes);
    made.push(texture);
    uniforms[described.uniform] = { value: texture };
  }

  const library = `precision highp sampler3D;\n${payload.entry?.field === "gsl_field" ? "#define FIELD_CAPS\n" : ""}${payload.code}\n${FIELD_CLIP_GLSL}`;
  const dressed = lit ? litMaterial(THREE, uniforms, group, library) : null;
  const material = dressed ? dressed.material : new THREE.ShaderMaterial({
    name: "field", uniforms, uniformsGroups: [group], vertexShader: VERTEX,
    fragmentShader: `${library}\n${SURFACE}\n${FRAGMENT}`,
    depthTest: true, depthWrite: true, transparent: false, toneMapped: true
  });
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(new Float32Array([-1, -1, 0, 3, -1, 0, -1, 3, 0]), 3));
  // What anything that measures the object should find is the box marched, never the triangle
  // that covers the view.
  geometry.boundingBox = new THREE.Box3(new THREE.Vector3(x0, y0, z0), new THREE.Vector3(x1, y1, z1));
  geometry.boundingSphere = geometry.boundingBox.getBoundingSphere(new THREE.Sphere());
  const mesh = new THREE.Mesh(geometry, material);
  mesh.name = "field";
  mesh.frustumCulled = false;
  mesh.castShadow = false;
  mesh.receiveShadow = false;
  // No ray meets the triangle as geometry: it is the view, not a surface.
  mesh.raycast = () => {};
  const projection = new THREE.Matrix4();
  const sceneToWorldInverse = new THREE.Matrix4();
  const viewport = new THREE.Vector4();
  mesh.onBeforeRender = (renderer, _scene, camera) => {
    // The camera three is drawing with now: the view's, a jittered one, a mirror's.
    sceneToWorldInverse.copy(mesh.matrixWorld).invert();
    uniforms.uProjectionInverse.value.copy(camera.projectionMatrixInverse);
    uniforms.uCameraToScene.value.multiplyMatrices(sceneToWorldInverse, camera.matrixWorld);
    projection.multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse);
    uniforms.uSceneToClip.value.multiplyMatrices(projection, mesh.matrixWorld);
    uniforms.uSceneToView.value.multiplyMatrices(camera.matrixWorldInverse, mesh.matrixWorld);
    writeFieldClip(THREE, uniforms, clipPlanes, sceneToWorldInverse);
    uniforms.uOrthographic.value = camera.isOrthographicCamera ? 1 : 0;
    renderer.getCurrentViewport(viewport);
    uniforms.uViewport.value.copy(viewport);
  };
  const object3D = new THREE.Group();
  object3D.name = "field";
  object3D.add(mesh);

  return {
    object3D,
    bounds: { min: [x0, y0, z0], max: [x1, y1, z1] },
    bodyCount: (payload.bodies || []).length,
    parameters: [...sliders.values()].map(({ slider }) => ({ name: slider.name, value: slider.value, min: slider.min, max: slider.max })),
    parameterValue: (name) => Number(sliders.get(name)?.uniform.value),
    setParameter(name, value) {
      const member = sliders.get(name);
      if (!member || !Number.isFinite(value)) return false;
      member.uniform.value = Math.min(Math.max(value, member.slider.min), member.slider.max);
      return true;
    },
    /** Whether the model reads its clock (the engine's word of its source, `timed`): one that does is played. */
    timed: payload.timed === true && Boolean(clock),
    /** The model's clock, in seconds. True when the model has one and it moved. */
    setTime(seconds) {
      if (!clock || !Number.isFinite(seconds) || clock.uniform.value === seconds) return false;
      clock.uniform.value = seconds;
      return true;
    },
    /** A section's planes (three's, the scene's coordinates): the field is cut by them, and capped where one cuts its solid. */
    setClipPlanes(planes) {
      clipPlanes = Array.isArray(planes) ? planes : [];
    },
    /** Whether the stage lights it (`lit`). */
    lit,
    /**
     * What a lit field wears, as a look dresses a lit mesh (`viewer/surfaceLook.js`): its finish, the
     * lift of its own colour, `flat` for colour without shading, its `opacity` (below 1 it is drawn
     * see-through: the first surface along each ray, blended, writing no depth) and the surface
     * `model` its lighting is drawn by. Null: three's own plain finish. Its bodies' colours are the
     * material's `uSurface`. Nothing for a field that shades itself.
     */
    setFinish(finish = null) {
      if (!dressed) return;
      const plain = finish || {};
      const number = (value, fallback) => (Number.isFinite(Number(value)) && value != null ? Number(value) : fallback);
      material.roughness = number(plain.roughness, 1);
      material.metalness = number(plain.metalness, 0);
      material.clearcoat = number(plain.clearcoat, 0);
      material.clearcoatRoughness = number(plain.clearcoatRoughness, 0);
      material.specularIntensity = number(plain.specularIntensity, 1);
      material.envMapIntensity = number(plain.envMapIntensity, 1);
      uniforms.uLift.value = number(plain.lift, 0);
      uniforms.uFlat.value = plain.flat === true ? 1 : 0;
      const opacity = Math.min(Math.max(number(plain.opacity, 1), 0), 1);
      const seeThrough = opacity < 0.999;
      if (material.transparent !== seeThrough) { material.transparent = seeThrough; material.needsUpdate = true; }
      material.opacity = opacity;
      material.depthWrite = !seeThrough;
      dressed.setModel(plain.model || null);
    },
    // A field shown alone is shaded by its own fragment, and none takes a shadow: the host's looks leave it alone.
    setSurfaceLook() {},
    setShadowReception() {},
    dispose() {
      geometry.dispose();
      material.dispose();
      group.dispose();
      for (const texture of made) texture.dispose();
    }
  };
}
