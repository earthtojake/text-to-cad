// CAD edge lines as ONE instanced screen-space line draw per component.
//
// A component's edge polylines are drawn once for every occurrence of the
// component. Instead of one line object per occurrence (a draw call each: the
// hand's 3,259 occurrences were ~10k draw calls a frame), a component owns a
// single quad geometry whose instances are every (segment, occurrence) pair:
// the vertex shader decodes gl_InstanceID into a segment (fetched from a
// per-component segment texture: two RGBA32F texels, start.xyz+class and
// end.xyz) and an occurrence (fetched from a per-set instance texture: four
// texels of matrix, one of colour, one of opacity/visibility/highlight), then
// extrudes the quad to the class's pixel width exactly as three's LineMaterial
// does for screen-space lines. Per-occurrence highlight, dim, hide, focus,
// exploded-view placement and selection therefore stay per occurrence: they
// are slots in the instance texture, written by the same record passes that
// used to write a material and a matrix per line object.
//
// Highlighted occurrences render in a second pass (a child mesh at the
// highlight render order) so selection outlines still draw over the
// highlighted surface; the main pass skips them. A deformed tube leaves its
// slot and takes a private GL_LINES object (see cadScene.js), because its
// points move per pose.
//
// GPU cost per component: the segment texture (32 B per drawn segment, shared
// by every occurrence and cached on the component), one instance texture
// (128 B per occurrence), one 4-vertex quad (two tiny buffers) and two
// materials. Nothing scales with segments x occurrences on the CPU.

// renderEdges imports syncEdgeInstanceStyle from here; both modules touch the
// other's exports only inside functions, never while evaluating.
import { applyLineDepthBias, CAD_EDGE_CLASS_ORDER } from "./renderEdges.js";

// Texels per occurrence row in the instance texture: 4 matrix columns, colour, state, 2 spare.
export const CAD_EDGE_INSTANCE_TEXELS = 8;
const INSTANCE_FLOATS = CAD_EDGE_INSTANCE_TEXELS * 4;
const SEGMENT_TEXTURE_MAX_WIDTH = 2048;
const MIN_CAPACITY = 8;

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function floatTexture(THREE, data, width, height) {
  const texture = new THREE.DataTexture(data, width, height, THREE.RGBAFormat, THREE.FloatType);
  texture.magFilter = THREE.NearestFilter;
  texture.minFilter = THREE.NearestFilter;
  texture.generateMipmaps = false;
  texture.needsUpdate = true;
  return texture;
}

// The component's drawn segments as a texture: texel 2i = start.xyz + class
// index, texel 2i+1 = end.xyz. `drawnRanges` are the class ranges whose style
// draws (thickness and opacity > 0), in class order.
export function buildCadEdgeSegmentTexture(THREE, cadEdges, drawnRanges) {
  const segmentCount = drawnRanges.reduce((sum, range) => sum + range.segmentCount, 0);
  if (segmentCount <= 0) {
    return null;
  }
  const texelCount = segmentCount * 2;
  const width = Math.min(texelCount, SEGMENT_TEXTURE_MAX_WIDTH);
  const height = Math.ceil(texelCount / width);
  const data = new Float32Array(width * height * 4);
  const { positions, indices } = cadEdges;
  let texel = 0;
  for (const range of drawnRanges) {
    const classIndex = Math.max(0, CAD_EDGE_CLASS_ORDER.indexOf(range.classId));
    for (let segment = range.segmentStart; segment < range.segmentStart + range.segmentCount; segment += 1) {
      const a = indices[segment * 2] * 3;
      const b = indices[segment * 2 + 1] * 3;
      data[texel * 4] = positions[a];
      data[texel * 4 + 1] = positions[a + 1];
      data[texel * 4 + 2] = positions[a + 2];
      data[texel * 4 + 3] = classIndex;
      data[texel * 4 + 4] = positions[b];
      data[texel * 4 + 5] = positions[b + 1];
      data[texel * 4 + 6] = positions[b + 2];
      data[texel * 4 + 7] = 0;
      texel += 2;
    }
  }
  return {
    texture: floatTexture(THREE, data, width, height),
    segmentCount,
    width,
    height,
    byteLength: data.byteLength
  };
}

const VERTEX_SHADER = /* glsl */`
uniform sampler2D cadSegmentTexture;
uniform vec2 cadSegmentTexSize;
uniform int cadSegmentCount;
uniform sampler2D cadInstanceTexture;
uniform mat4 cadClassColor;
uniform vec4 cadClassWidth;
uniform vec2 resolution;
uniform float cadHighlightPass;
varying vec4 vColor;
#include <common>
#include <clipping_planes_pars_vertex>

// Same near-plane trimming as three's LineMaterial: a perspective segment
// crossing the camera plane is cut where it meets the near plane.
float cadTrimSegmentAlpha(const in vec4 start, const in vec4 end) {
  float a = projectionMatrix[2][2];
  float b = projectionMatrix[3][2];
  float nearEstimate = (a > 0.0) ? (-b / (a + 1.0)) : (-0.5 * b / a);
  return (nearEstimate - start.z) / (end.z - start.z);
}

void main() {
  int segment = gl_InstanceID % cadSegmentCount;
  int occurrence = gl_InstanceID / cadSegmentCount;
  int texWidth = int(cadSegmentTexSize.x);
  int texel = segment * 2;
  vec4 startPoint = texelFetch(cadSegmentTexture, ivec2(texel % texWidth, texel / texWidth), 0);
  vec4 endPoint = texelFetch(cadSegmentTexture, ivec2((texel + 1) % texWidth, (texel + 1) / texWidth), 0);
  vec4 style = texelFetch(cadInstanceTexture, ivec2(4, occurrence), 0);
  vec4 state = texelFetch(cadInstanceTexture, ivec2(5, occurrence), 0);
  int classIndex = int(startPoint.w + 0.5);
  float lineWidth = cadClassWidth[classIndex];
  float passVisible = cadHighlightPass > 0.5 ? state.z : 1.0 - state.z;
  if (state.y < 0.5 || passVisible < 0.5 || lineWidth <= 0.0) {
    // Not drawn in this pass: collapse the quad outside the clip volume.
    gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
    vColor = vec4(0.0);
    return;
  }
  vec4 classColor = cadClassColor[classIndex];
  vColor = style.w > 0.5 ? vec4(style.rgb, state.x) : vec4(classColor.rgb, classColor.a * state.x);

  mat4 instanceMatrix = mat4(
    texelFetch(cadInstanceTexture, ivec2(0, occurrence), 0),
    texelFetch(cadInstanceTexture, ivec2(1, occurrence), 0),
    texelFetch(cadInstanceTexture, ivec2(2, occurrence), 0),
    texelFetch(cadInstanceTexture, ivec2(3, occurrence), 0)
  );
  mat4 modelView = modelViewMatrix * instanceMatrix;
  vec4 start = modelView * vec4(startPoint.xyz, 1.0);
  vec4 end = modelView * vec4(endPoint.xyz, 1.0);
  float aspect = resolution.x / resolution.y;
  bool perspective = (projectionMatrix[2][3] == -1.0);
  if (perspective) {
    if (start.z < 0.0 && end.z >= 0.0) {
      end.xyz = mix(start.xyz, end.xyz, cadTrimSegmentAlpha(start, end));
    } else if (end.z < 0.0 && start.z >= 0.0) {
      start.xyz = mix(end.xyz, start.xyz, cadTrimSegmentAlpha(end, start));
    }
  }
  vec4 clipStart = projectionMatrix * start;
  vec4 clipEnd = projectionMatrix * end;
  vec3 ndcStart = clipStart.xyz / clipStart.w;
  vec3 ndcEnd = clipEnd.xyz / clipEnd.w;
  vec2 dir = ndcEnd.xy - ndcStart.xy;
  dir.x *= aspect;
  dir = normalize(dir);
  vec2 offset = vec2(dir.y, -dir.x);
  offset.x /= aspect;
  if (position.x < 0.0) {
    offset *= -1.0;
  }
  offset *= lineWidth;
  offset /= resolution.y;
  vec4 clip = (position.y < 0.5) ? clipStart : clipEnd;
  offset *= clip.w;
  clip.xy += offset;
  gl_Position = clip;
  vec4 mvPosition = (position.y < 0.5) ? start : end;
  #include <clipping_planes_vertex>
}
`;

// GLSL3 ShaderMaterials declare their own output (three adds the gl_FragColor
// alias only to GLSL1 programs); linearToOutputTexel is three's colour-space
// conversion from the fragment prefix, what <colorspace_fragment> applies.
const FRAGMENT_SHADER = /* glsl */`
uniform float opacity;
varying vec4 vColor;
layout(location = 0) out vec4 cadFragColor;
#include <clipping_planes_pars_fragment>
void main() {
  #include <clipping_planes_fragment>
  cadFragColor = linearToOutputTexel(vec4(vColor.rgb, vColor.a * opacity));
}
`;

function createInstancedLineMaterial(THREE, uniforms, { depthTest, depthBias, highlightPass }) {
  const material = new THREE.ShaderMaterial({
    glslVersion: THREE.GLSL3,
    uniforms: {
      ...uniforms,
      cadHighlightPass: { value: highlightPass ? 1 : 0 },
      opacity: { value: 1 }
    },
    vertexShader: VERTEX_SHADER,
    fragmentShader: FRAGMENT_SHADER,
    transparent: true,
    depthTest,
    depthWrite: false,
    side: THREE.DoubleSide,
    toneMapped: false,
    clipping: true
  });
  // The runtime resyncs `material.resolution` on resize like a LineMaterial.
  Object.defineProperty(material, "resolution", {
    get() {
      return material.uniforms.resolution.value;
    }
  });
  material.userData.cadEdgeInstances = true;
  applyLineDepthBias(material, depthBias);
  return material;
}

function quadGeometry(THREE) {
  const geometry = new THREE.InstancedBufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute([-1, 0, 0, 1, 0, 0, -1, 1, 0, 1, 1, 0], 3));
  geometry.setIndex([0, 1, 2, 2, 1, 3]);
  geometry.instanceCount = 0;
  // Every instance is placed by the shader; three must not cull the quad.
  geometry.boundingSphere = new THREE.Sphere(new THREE.Vector3(), Infinity);
  return geometry;
}

/**
 * The occurrences of one component (one edge style) as instances of one draw.
 *
 *   const set = new CadEdgeInstances(THREE, { segments, classStyles, resolution, depthTest, depthBias, renderOrder, highlightRenderOrder })
 *   const slot = set.allocate();           // a record's occurrence
 *   set.setMatrix(slot, matrix4);          // its display matrix (edgesGroup space)
 *   set.setStyle(slot, { color, opacity }) // override colour + uniform opacity (highlight, dim, effect recolour) ...
 *   set.setStyle(slot, { opacityScale })   // ... or the class colours at scaled class opacity
 *   set.setVisible(slot, bool); set.setHighlighted(slot, bool)
 *   set.release(slot)
 *
 * `object` is the Mesh to add to the edges group; `highlightObject` is its
 * child for the highlight pass. `materials` is what clip planes and resolution
 * syncs iterate.
 */
export class CadEdgeInstances {
  constructor(THREE, {
    segments,
    classStyles,
    resolution = null,
    depthTest = true,
    depthBias = 0,
    renderOrder = 3,
    highlightRenderOrder = 26
  }) {
    this.THREE = THREE;
    this.segments = segments;
    this.capacity = 0;
    this.slotCount = 0;
    this.liveCount = 0;
    this.highlightedCount = 0;
    // A SET, not an array: releasing every occurrence of a component walks the
    // trailing slots one at a time in syncCounts, and an array turned that into
    // an includes + indexOf + splice per step — quadratic in the occurrence
    // count of the component being torn down, on every publish that drops one.
    this.freeSlots = new Set();
    this.instanceData = new Float32Array(0);
    this.instanceTexture = null;
    this.disposed = false;

    const classColor = new THREE.Matrix4();
    const classWidth = new THREE.Vector4();
    const elements = classColor.elements;
    for (let index = 0; index < CAD_EDGE_CLASS_ORDER.length; index += 1) {
      const style = classStyles.find((entry) => entry.classId === CAD_EDGE_CLASS_ORDER[index]) || null;
      elements[index * 4] = style?.color?.r ?? 0;
      elements[index * 4 + 1] = style?.color?.g ?? 0;
      elements[index * 4 + 2] = style?.color?.b ?? 0;
      elements[index * 4 + 3] = style ? clamp(style.opacity, 0, 1) : 0;
      classWidth.setComponent(index, style ? clamp(style.thickness, 0, 6) : 0);
    }
    this.uniforms = {
      cadSegmentTexture: { value: segments.texture },
      cadSegmentTexSize: { value: new THREE.Vector2(segments.width, segments.height) },
      cadSegmentCount: { value: segments.segmentCount },
      cadInstanceTexture: { value: null },
      cadClassColor: { value: classColor },
      cadClassWidth: { value: classWidth },
      resolution: { value: new THREE.Vector2(resolution?.width || 1, resolution?.height || 1) }
    };
    this.material = createInstancedLineMaterial(THREE, this.uniforms, { depthTest, depthBias, highlightPass: false });
    this.highlightMaterial = createInstancedLineMaterial(THREE, this.uniforms, { depthTest, depthBias, highlightPass: true });
    this.materials = [this.material, this.highlightMaterial];
    this.geometry = quadGeometry(THREE);
    this.object = new THREE.Mesh(this.geometry, this.material);
    this.object.renderOrder = renderOrder;
    this.object.frustumCulled = false;
    this.object.matrixAutoUpdate = false;
    this.object.userData.cadEdgeInstances = this;
    this.object.userData.beforeDispose = () => this.dispose();
    this.highlightObject = new THREE.Mesh(this.geometry, this.highlightMaterial);
    this.highlightObject.renderOrder = highlightRenderOrder;
    this.highlightObject.frustumCulled = false;
    this.highlightObject.matrixAutoUpdate = false;
    this.highlightObject.visible = false;
    this.highlightObject.userData.cadEdgeInstancesHighlight = true;
    this.object.add(this.highlightObject);
    this.grow(MIN_CAPACITY);
  }

  grow(capacity) {
    const THREE = this.THREE;
    const next = new Float32Array(capacity * INSTANCE_FLOATS);
    next.set(this.instanceData.subarray(0, Math.min(this.instanceData.length, next.length)));
    this.instanceData = next;
    this.capacity = capacity;
    this.instanceTexture?.dispose();
    this.instanceTexture = floatTexture(THREE, next, CAD_EDGE_INSTANCE_TEXELS, capacity);
    this.uniforms.cadInstanceTexture.value = this.instanceTexture;
  }

  allocate() {
    let slot;
    if (this.freeSlots.size) {
      slot = this.freeSlots.values().next().value;
      this.freeSlots.delete(slot);
    } else {
      if (this.slotCount >= this.capacity) {
        this.grow(Math.max(MIN_CAPACITY, this.capacity * 2));
      }
      slot = this.slotCount;
      this.slotCount += 1;
    }
    this.liveCount += 1;
    const base = slot * INSTANCE_FLOATS;
    this.instanceData.fill(0, base, base + INSTANCE_FLOATS);
    // Identity matrix, class colours at full opacity, visible, not highlighted.
    this.instanceData[base] = 1;
    this.instanceData[base + 5] = 1;
    this.instanceData[base + 10] = 1;
    this.instanceData[base + 15] = 1;
    this.instanceData[base + 20] = 1;
    this.instanceData[base + 21] = 1;
    this.syncCounts();
    this.instanceTexture.needsUpdate = true;
    return slot;
  }

  release(slot) {
    if (!Number.isInteger(slot) || slot < 0 || slot >= this.slotCount) {
      return;
    }
    const base = slot * INSTANCE_FLOATS;
    if (this.instanceData[base + 22] > 0.5) {
      this.highlightedCount -= 1;
    }
    this.instanceData.fill(0, base, base + INSTANCE_FLOATS);
    this.freeSlots.add(slot);
    this.liveCount -= 1;
    this.syncCounts();
    this.instanceTexture.needsUpdate = true;
  }

  syncCounts() {
    // Trailing freed slots shrink the draw; interior ones are collapsed by the shader.
    while (this.slotCount > 0 && this.freeSlots.has(this.slotCount - 1)) {
      this.freeSlots.delete(this.slotCount - 1);
      this.slotCount -= 1;
    }
    this.geometry.instanceCount = this.segments.segmentCount * this.slotCount;
    this.highlightObject.visible = this.highlightedCount > 0;
  }

  setMatrix(slot, matrix) {
    const base = slot * INSTANCE_FLOATS;
    const elements = matrix.elements;
    for (let index = 0; index < 16; index += 1) {
      this.instanceData[base + index] = elements[index];
    }
    this.instanceTexture.needsUpdate = true;
  }

  // Override colour (a THREE.Color) with a uniform opacity, or — without a
  // colour — the class colours at their class opacity times `opacityScale`.
  setStyle(slot, { color = null, opacity = null, opacityScale = 1 } = {}) {
    const base = slot * INSTANCE_FLOATS;
    if (color) {
      this.instanceData[base + 16] = color.r;
      this.instanceData[base + 17] = color.g;
      this.instanceData[base + 18] = color.b;
      this.instanceData[base + 19] = 1;
      this.instanceData[base + 20] = clamp(opacity === null ? opacityScale : opacity, 0, 1);
    } else {
      this.instanceData[base + 16] = 0;
      this.instanceData[base + 17] = 0;
      this.instanceData[base + 18] = 0;
      this.instanceData[base + 19] = 0;
      this.instanceData[base + 20] = clamp(opacity === null ? opacityScale : opacity, 0, 1);
    }
    this.instanceTexture.needsUpdate = true;
  }

  setVisible(slot, visible) {
    const base = slot * INSTANCE_FLOATS;
    this.instanceData[base + 21] = visible ? 1 : 0;
    this.instanceTexture.needsUpdate = true;
  }

  setHighlighted(slot, highlighted) {
    const base = slot * INSTANCE_FLOATS;
    const was = this.instanceData[base + 22] > 0.5;
    if (was === !!highlighted) {
      return;
    }
    this.instanceData[base + 22] = highlighted ? 1 : 0;
    this.highlightedCount += highlighted ? 1 : -1;
    this.highlightObject.visible = this.highlightedCount > 0;
    this.instanceTexture.needsUpdate = true;
  }

  // Test/diagnostic readback of one slot.
  readSlot(slot) {
    const base = slot * INSTANCE_FLOATS;
    const data = this.instanceData;
    return {
      matrix: Array.from(data.subarray(base, base + 16)),
      color: data[base + 19] > 0.5 ? [data[base + 16], data[base + 17], data[base + 18]] : null,
      opacity: data[base + 20],
      visible: data[base + 21] > 0.5,
      highlighted: data[base + 22] > 0.5
    };
  }

  setResolution(width, height) {
    this.uniforms.resolution.value.set(Math.max(1, width), Math.max(1, height));
  }

  // Bytes this set holds on the GPU beyond the (cached, shared) segment texture.
  get instanceByteLength() {
    return this.instanceData.byteLength;
  }

  dispose() {
    if (this.disposed) {
      return;
    }
    this.disposed = true;
    this.instanceTexture?.dispose();
    this.material.dispose();
    this.highlightMaterial.dispose();
    this.geometry.dispose();
  }
}

// The instance sets of a scene runtime, whether the cadScene runtime itself or
// a viewer runtime holding one.
export function cadEdgeInstanceSets(runtime) {
  const sets = runtime?.cadEdgeInstanceSets || runtime?.cadScene?.runtime?.cadEdgeInstanceSets;
  return sets ? [...sets] : [];
}

// Per-occurrence edge state written by the visual-state pass; mirrors
// syncRecordEdgeMaterials for a record whose edges are an instance slot.
export function syncEdgeInstanceStyle(edgeInstance, { color = null, opacity = null, opacityScale = 1, fallbackColor = null }) {
  if (!edgeInstance?.set || edgeInstance.set.disposed) {
    return;
  }
  const THREE = edgeInstance.set.THREE;
  if (opacity === null && !color) {
    edgeInstance.set.setStyle(edgeInstance.slot, { opacityScale });
    return;
  }
  const override = color || (fallbackColor ? new THREE.Color(fallbackColor) : null);
  edgeInstance.set.setStyle(edgeInstance.slot, { color: override, opacity, opacityScale });
}
