// The Render studio's backdrop: a seamless sweep behind the model rather than a flat fill.
//
// A product photographer's backdrop is never one flat colour: a light on the paper sweep
// lifts it behind the subject, it falls off toward the frame's edges, and above the
// horizon the wall darkens as it rises away from the lights. Render tools mimic that with
// a gradient or vignette behind the model (KeyShot's gradient backgrounds, Blender's
// studio world, the render modes of Fusion and Onshape), and so does this: one
// full-screen draw, before anything else in the scene, of the backdrop colour
//
//   - lifted toward white behind the middle of the frame (`lift`),
//   - shaded toward the frame's corners (`shade`: a share of the colour, more on a dark
//     colour, where the same share is far less visible, than on a light one), and
//   - shaded more above the horizon, by how far the view looks up (`wall`), so a low view
//     reads as a floor running into a wall rather than as a plane cut off against a fill.
//
// So the Background colour is the sweep's tone, lifted behind the model and shaded toward
// the edges (white stays white behind it). Its alpha is the backdrop's opacity: a
// half-transparent background keeps its gradient, and a transparent one draws exactly what
// the clear does, nothing.
//
// It writes no depth, so the studio frame's occlusion never darkens it, casts no shadow
// and is never picked; the floor's mirrored draw leaves it out. Whoever renders the scene
// with the background taken away (a thumbnail) gets nothing of it either: with no
// `scene.background` it takes the clear's alpha, which they set to 0.

const BACKDROP_VERTEX = /* glsl */ `
uniform mat4 uProjectionInverse;
uniform mat4 uCameraWorld;
varying vec3 vRay;
varying vec2 vScreen;
void main() {
  vScreen = position.xy;
  // The view ray through this corner, in the world: affine across the screen, so the
  // corners' rays interpolate exactly.
  vec4 nearPoint = uProjectionInverse * vec4(position.xy, -1.0, 1.0);
  vec4 farPoint = uProjectionInverse * vec4(position.xy, 1.0, 1.0);
  vRay = mat3(uCameraWorld) * (farPoint.xyz / farPoint.w - nearPoint.xyz / nearPoint.w);
  gl_Position = vec4(position.xy, 0.0, 1.0);
}
`;

const BACKDROP_FRAGMENT = /* glsl */ `
uniform vec3 uColor;
uniform float uAlpha;
uniform vec3 uShape;
uniform float uAspect;
uniform float uPremultiply;
uniform float uLinear;
varying vec3 vRay;
varying vec2 vScreen;

float ditherNoise(vec2 uv) {
  highp float dt = mod(dot(uv, vec2(12.9898, 78.233)), 3.141592653589793);
  return fract(sin(dt) * 43758.5453);
}

vec3 srgbToLinear(vec3 c) {
  return mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)), step(vec3(0.04045), c));
}

void main() {
  // 0 in the middle of the frame (a little above it, where a product's mass sits), 1 at a corner.
  vec2 at = vec2(vScreen.x * uAspect, vScreen.y - 0.12);
  float reach = clamp(length(at) / length(vec2(uAspect, 1.12)), 0.0, 1.0);
  float glow = 1.0 - smoothstep(0.0, 0.75, reach);
  float corner = smoothstep(0.3, 1.0, reach);
  float wall = smoothstep(0.0, 0.55, vRay.z * inversesqrt(dot(vRay, vRay)));
  vec3 color = mix(uColor, vec3(1.0), uShape.x * glow * glow);
  color *= 1.0 - uShape.y * clamp(corner + uShape.z * wall, 0.0, 1.0);
  // A dark sweep spans few of the canvas's 8-bit levels: a level of noise turns the
  // rounding's contour rings into grain too fine to see.
#ifdef STUDIO_DITHER_SCALE
  color += (ditherNoise(gl_FragCoord.xy) - 0.5) * STUDIO_DITHER_SCALE / 255.0;
#else
  color += (ditherNoise(gl_FragCoord.xy) - 0.5) / 255.0;
#endif
  color = clamp(color, 0.0, 1.0);
  // Into the canvas (or a target three draws as it) in display colour, as a clear writes;
  // into any other target in linear light.
  if (uLinear > 0.5) color = srgbToLinear(color);
  gl_FragColor = vec4(color * mix(1.0, uAlpha, uPremultiply), uAlpha);
}
`;

/**
 * Create the backdrop. `object` goes in the studio's group; `update` sets its colour, its
 * opacity and its `shape` (`lift`, `shade` for a dark and a light colour, `wall`).
 */
export function createStudioBackdrop(THREE, shape) {
  const uniforms = {
    uColor: { value: new THREE.Vector3(1, 1, 1) },
    uAlpha: { value: 1 },
    uShape: { value: new THREE.Vector3(0, 0, 0) },
    uAspect: { value: 1 },
    uPremultiply: { value: 1 },
    uLinear: { value: 0 },
    uProjectionInverse: { value: new THREE.Matrix4() },
    uCameraWorld: { value: new THREE.Matrix4() }
  };
  const material = new THREE.ShaderMaterial({
    uniforms,
    vertexShader: BACKDROP_VERTEX,
    fragmentShader: BACKDROP_FRAGMENT,
    depthTest: false,
    depthWrite: false,
    blending: THREE.NoBlending,
    toneMapped: false
  });
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), material);
  mesh.name = "studio-backdrop";
  mesh.frustumCulled = false;
  mesh.castShadow = false;
  mesh.receiveShadow = false;
  // First of everything opaque: whatever the scene draws covers it.
  mesh.renderOrder = -1e9;
  mesh.raycast = () => {};
  const state = { alpha: 1 };
  const display = { r: 1, g: 1, b: 1 };

  mesh.onBeforeRender = (renderer, scene, camera) => {
    // Rendered with the background taken away (and the clear made transparent), it is not there.
    const alpha = scene.background ? state.alpha : Math.min(state.alpha, renderer.getClearAlpha());
    const target = renderer.getRenderTarget();
    uniforms.uAlpha.value = alpha;
    uniforms.uPremultiply.value = renderer.getContextAttributes?.()?.premultipliedAlpha === false ? 0 : 1;
    uniforms.uLinear.value = target && target.isXRRenderTarget !== true ? 1 : 0;
    uniforms.uProjectionInverse.value.copy(camera.projectionMatrixInverse);
    uniforms.uCameraWorld.value.copy(camera.matrixWorld);
    const projection = camera.projectionMatrix.elements;
    uniforms.uAspect.value = Math.abs(projection[0]) > 1e-12 ? Math.abs(projection[5] / projection[0]) : 1;
    material.uniformsNeedUpdate = true;
  };

  return {
    object: mesh,
    uniforms,
    /** The backdrop's colour (any THREE colour input) and opacity, 0 to 1. */
    update({ color, opacity }) {
      new THREE.Color(color).getRGB(display, THREE.SRGBColorSpace);
      uniforms.uColor.value.set(display.r, display.g, display.b);
      state.alpha = opacity;
      // Transparent, it would draw exactly the clear: it is not drawn at all.
      mesh.visible = opacity > 0;
      // More shade on a dark colour, where the same share of it is far less visible.
      const luma = 0.2126 * display.r + 0.7152 * display.g + 0.0722 * display.b;
      uniforms.uShape.value.set(shape.lift, shape.shade.dark + (shape.shade.light - shape.shade.dark) * luma, shape.wall);
    },
    dispose() {
      mesh.removeFromParent();
      mesh.geometry.dispose();
      material.dispose();
    }
  };
}
