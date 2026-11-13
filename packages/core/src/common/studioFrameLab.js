// PROTOTYPE (a lab, not shipped behaviour): screen-space global illumination and screen-space
// reflections as extra passes of the studio's frame (studioFrame.js). Both are OFF unless the page
// sets `globalThis.__studioFrameLab = { ssgi: 1, ssr: 1 }` (strengths) before the frame is created;
// with neither set the frame creates nothing of this file and draws exactly what it always drew.
//
// What it adds to one sample of the frame:
//
//   GEOMETRY   a second draw of the scene's opaque meshes with stand-in materials into two
//              half-float attachments: the view-space shading normal and roughness, the base
//              colour and metalness. (The frame's own draw keeps its one program per material:
//              these are other materials, one shared program.)
//   BOUNCE     at half resolution, a few cosine-distributed rays per pixel marched through the
//              depth buffer. A ray that meets the front of a visible surface brings that surface's
//              radiance (the scene's colour, un-tone-mapped) and takes away the environment light
//              the ambient occlusion had not already taken from that direction; blurred by depth
//              like the occlusion, upsampled by depth, and added as diffuse light (times the
//              receiver's diffuse albedo).
//   REFLECT    at full resolution, one ray per pixel along a direction of the surface's GGX lobe
//              (its visible normals). Where it meets a visible surface, that surface's radiance
//              replaces the environment's in the specular term: `B (L_hit - occlusion L_env)`, `B`
//              the split-sum weight of the surface's F0.
//   COMPOSITE  today's composite, then in scene-linear light (PBR Neutral inverted) the two terms
//              are added and the result tone mapped again.
//
// Every stochastic choice (ray directions, march offsets) moves with the sample index, so the
// frame's accumulation converges them with everything else.
//
// A STILL VIEW'S LIGHT. One sample of either effect is grain, and a moving view is one sample a
// frame. So a picture's first sample carries none of it (`weightAt`): a moving view is drawn exactly
// as it is without the lab, by the frame's own passes, at the frame's own cost. Once the view
// rests, each later sample carries a growing share (over `fade` samples) and the shares are scaled
// so the converged picture holds all of it: the light fades in as the picture converges, already
// averaged over the samples behind it.

const TONE_GLSL = /* glsl */ `
vec3 toLinear(vec3 c) {
  return mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)), step(vec3(0.04045), c));
}
vec3 toDisplay(vec3 c) {
  return mix(c * 12.92, 1.055 * pow(c, vec3(1.0 / 2.4)) - 0.055, step(vec3(0.0031308), c));
}
// Khronos PBR Neutral (three's NeutralToneMapping, exposure already applied) and its inverse.
const float NEUTRAL_START = 0.76;
const float NEUTRAL_DESATURATION = 0.15;
vec3 neutral(vec3 color) {
  float x = min(color.r, min(color.g, color.b));
  float offset = x < 0.08 ? x - 6.25 * x * x : 0.04;
  color -= offset;
  float peak = max(color.r, max(color.g, color.b));
  if (peak < NEUTRAL_START) return color;
  float d = 1.0 - NEUTRAL_START;
  float newPeak = 1.0 - d * d / (peak + d - NEUTRAL_START);
  color *= newPeak / peak;
  float g = 1.0 - 1.0 / (NEUTRAL_DESATURATION * (peak - newPeak) + 1.0);
  return mix(color, vec3(newPeak), g);
}
vec3 neutralInverse(vec3 color) {
  color = clamp(color, 0.0, 0.998);
  float peak = max(color.r, max(color.g, color.b));
  if (peak >= NEUTRAL_START) {
    float d = 1.0 - NEUTRAL_START;
    float oldPeak = d * d / (1.0 - peak) - d + NEUTRAL_START;
    float g = 1.0 - 1.0 / (NEUTRAL_DESATURATION * (oldPeak - peak) + 1.0);
    color = (color - g * peak) / (1.0 - g);
    color *= oldPeak / peak;
  }
  float y = max(min(color.r, min(color.g, color.b)), 0.0);
  float offset = y < 0.04 ? sqrt(y / 6.25) - y : 0.04;
  return color + offset;
}
`;

// What every lab pass reads: the frame's depth and colour, the geometry draw, the occlusion.
const SCENE_GLSL = /* glsl */ `
uniform highp sampler2D uDepth;
uniform sampler2D uColor;
uniform sampler2D uHistory;
uniform float uHistoryOn;
uniform sampler2D uNormal;
uniform sampler2D uSurface;
uniform sampler2D uOcclusion;
uniform vec2 uOcclusionSize;
uniform float uStrength;
uniform float uPower;
uniform mat4 uProjection;
uniform mat4 uProjectionInverse;
uniform vec2 uSize;
uniform float uOrthographic;
uniform float uFrame;
uniform samplerCube uEnv;
uniform mat3 uEnvFromView;
uniform float uEnvScale;
uniform float uEnvMaxLod;
const float PI = 3.141592653589793;

vec3 viewAt(vec2 uv, float depth) {
  vec4 point = uProjectionInverse * vec4(vec3(uv, depth) * 2.0 - 1.0, 1.0);
  return point.xyz / point.w;
}
float depthAt(vec2 uv) {
  return textureLod(uDepth, uv, 0.0).x;
}
// A depth's view-space z (negative in front of the camera), perspective or orthographic.
float viewZ(float depth) {
  float ndc = depth * 2.0 - 1.0;
  return (uProjection[3][2] - ndc * uProjection[3][3]) / (ndc * uProjection[2][3] - uProjection[2][2]);
}
// A pixel's size in the scene at view depth z.
float pixelSize(float z) {
  return (uOrthographic > 0.5 ? 1.0 : -z) * 2.0 / (uProjection[1][1] * uSize.y);
}
vec2 pixelCentre(vec2 uv) {
  return (floor(uv * uSize) + 0.5) / uSize;
}
float occlusionOf(float value) {
  return mix(1.0, pow(value, uPower), uStrength);
}
// The occlusion as the composite applies it: upsampled by depth, or its nearest texel.
float occlusionAt(vec2 uv, float z) {
  if (uStrength <= 0.0) return 1.0;
  vec2 at = uv * uOcclusionSize - 0.5;
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
  return total > 1e-5 ? occlusionOf(sum / total) : 1.0;
}
float occlusionNear(vec2 uv) {
  if (uStrength <= 0.0) return 1.0;
  ivec2 at = clamp(ivec2(uv * uOcclusionSize), ivec2(0), ivec2(uOcclusionSize) - 1);
  return occlusionOf(texelFetch(uOcclusion, at, 0).r);
}
// The radiance a visible point sends to the camera, in exposed scene-linear light, as the picture
// shows it: from the picture so far (the accumulation, which has the samples before this one with
// their occlusion, bounce and reflections, so each sample carries the light one bounce further),
// or for a picture's first sample from this sample's colour under its occlusion.
vec3 radianceAt(vec2 uv) {
  if (uHistoryOn > 0.5) return neutralInverse(toLinear(textureLod(uHistory, uv, 0.0).rgb));
  return neutralInverse(toLinear(textureLod(uColor, uv, 0.0).rgb)) * occlusionNear(uv);
}
vec3 envAt(vec3 viewDirection, float lod) {
  return textureLod(uEnv, uEnvFromView * viewDirection, lod).rgb * uEnvScale;
}
// The split-sum scale and bias of F0 (Karis's fit, three's DFGApprox of old).
vec2 environmentBrdf(float dotNV, float roughness) {
  const vec4 c0 = vec4(-1.0, -0.0275, -0.572, 0.022);
  const vec4 c1 = vec4(1.0, 0.0425, 1.04, -0.04);
  vec4 r = roughness * c0 + c1;
  float a004 = min(r.x * r.x, exp2(-9.28 * dotNV)) * r.x + r.y;
  return vec2(-1.04, 1.04) * a004 + r.zw;
}
// The environment's specular light off a surface toward view, as the material draws it (three's
// getIBLRadiance along the mirror direction, weighed by the split sum of the surface's F0).
vec3 environmentSpecular(vec3 normal, vec3 view, float roughness, vec4 surface, float blur) {
  float r4 = roughness * roughness * roughness * roughness;
  vec3 mirror = normalize(mix(reflect(-view, normal), normal, r4));
  vec2 scaleBias = environmentBrdf(clamp(dot(normal, view), 0.0, 1.0), roughness);
  vec3 f0 = mix(vec3(0.04), surface.rgb, clamp(surface.a, 0.0, 1.0));
  // blur: the roughness of whatever gathers this light, which blurs the environment once more.
  float r = clamp(sqrt(roughness * roughness + blur * blur), 0.0, 1.0);
  return (f0 * scaleBias.x + scaleBias.y) * envAt(mirror, uEnvMaxLod * r * (2.0 - r));
}
// The radiance the visible point at uv (view-space point, its shading normal and roughness in
// shading) sends along toward. What the camera sees of it holds its environment reflection as
// the CAMERA mirrors it; a glossy surface sends another part of the environment another way. So
// that reflection is taken out and the one aimed along toward put in (unoccluded but for the
// ambient occlusion: a second bounce is not traced), blurred as the gatherer's own lobe of
// roughness blur would blur it, which a handful of rays cannot; the rest (diffuse light, the
// key's highlight) is taken to leave the same in every direction.
vec3 radianceToward(vec2 uv, vec3 point, vec4 shading, vec3 toward, float blur) {
  vec3 normal = normalize(shading.xyz);
  float roughness = clamp(shading.w, 0.0, 1.0);
  vec4 surface = textureLod(uSurface, uv, 0.0);
  vec3 camera = uOrthographic > 0.5 ? vec3(0.0, 0.0, 1.0) : normalize(-point);
  float occlusion = occlusionAt(uv, -point.z);
  vec3 drawn = environmentSpecular(normal, camera, roughness, surface, 0.0);
  vec3 aimed = min(environmentSpecular(normal, toward, roughness, surface, blur), vec3(4.0));
  return max(radianceAt(uv) - occlusion * drawn, 0.0) + occlusion * aimed;
}

float ign(vec2 pixel) {
  return fract(52.9829189 * fract(dot(pixel, vec2(0.06711056, 0.00583715))));
}
// Two numbers in [0, 1) for this pixel and sample: a lattice over the samples (R3's first two
// rates, so it is not the key light's R2 nor the camera's Halton), offset per pixel.
vec2 noise2(vec2 pixel) {
  return fract(vec2(ign(pixel), ign(pixel.yx + vec2(71.0, 113.0))) + uFrame * vec2(0.8191725134, 0.6710436067));
}
float noise1(vec2 pixel) {
  return fract(ign(pixel.yx + vec2(13.0, 71.0)) + uFrame * 0.5497004779);
}
void basis(vec3 n, out vec3 t, out vec3 b) {
  float s = n.z >= 0.0 ? 1.0 : -1.0;
  float a = -1.0 / (s + n.z);
  float c = n.x * n.y * a;
  t = vec3(1.0 + s * n.x * n.x * a, s * c, -s * n.x);
  b = vec3(c, s + n.y * n.y * a, -n.y);
}
`;

const TRACE_GLSL = /* glsl */ `
// Where the ray from origin along direction (view space) meets the depth buffer within reach:
// its uv and how far along it (z), or z < 0 for none. Steps grow with the square of the distance
// and start at a jittered offset; a step that lands behind a surface is bisected back to the
// crossing, and counts only if the ray is at the surface there (it crossed it, rather than passed
// behind something's silhouette). A ray that passes behind is unknown: it is marched on until it
// comes out.
vec3 trace(vec3 origin, vec3 direction, float reach, float jitter) {
  float limit = reach;
  if (uOrthographic < 0.5 && direction.z > 0.0) limit = min(limit, -0.9 * origin.z / direction.z);
  float low = 0.0;
  bool hidden = false;
  for (int i = 0; i < TRACE_STEPS; i++) {
    float s = (float(i) + jitter) / float(TRACE_STEPS);
    float t = limit * s * s;
    vec3 point = origin + direction * t;
    vec4 clip = uProjection * vec4(point, 1.0);
    vec2 uv = clip.xy / clip.w * 0.5 + 0.5;
    if (uv.x <= 0.0 || uv.x >= 1.0 || uv.y <= 0.0 || uv.y >= 1.0) return vec3(uv, -1.0);
    float behind = viewZ(depthAt(uv)) - point.z;
    if (behind > 0.0) {
      if (!hidden) {
        float high = t;
        vec2 hitUv = uv;
        float hitBehind = behind;
        float hitZ = point.z;
        for (int j = 0; j < TRACE_REFINE; j++) {
          float mid = 0.5 * (low + high);
          vec3 q = origin + direction * mid;
          vec4 c = uProjection * vec4(q, 1.0);
          vec2 at = c.xy / c.w * 0.5 + 0.5;
          float b = viewZ(depthAt(at)) - q.z;
          if (b > 0.0) {
            high = mid;
            hitUv = at;
            hitBehind = b;
            hitZ = q.z;
          } else {
            low = mid;
          }
        }
        float tolerance = 2.0 * abs(direction.z) * (high - low) + 4.0 * pixelSize(hitZ);
        if (hitBehind < tolerance) return vec3(hitUv, high);
        hidden = true;
      }
    } else {
      hidden = false;
      low = t;
    }
  }
  return vec3(0.0, 0.0, -1.0);
}
`;

const PASS_VERTEX = /* glsl */ `
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = vec4(position.xy, 0.0, 1.0);
}
`;

// One bounce of diffuse light, at half resolution. RGB: the light to add per unit of diffuse
// albedo (it may be negative: a far occluder that is darker than the environment it hides);
// A: the pixel's view depth, which the blur and the upsample weigh by (0: nothing drawn).
const bounceFragment = ({ rays, steps }) => /* glsl */ `
#define TRACE_STEPS ${steps}
#define TRACE_REFINE 3
#define RAYS ${rays}
uniform float uReach;
uniform float uRadius;
uniform float uMaxPixels;
varying vec2 vUv;
${TONE_GLSL}
${SCENE_GLSL}
${TRACE_GLSL}
void main() {
  vec2 uv = pixelCentre(vUv);
  float depth = depthAt(uv);
  if (depth >= 1.0) {
    gl_FragColor = vec4(0.0);
    return;
  }
  vec3 center = viewAt(uv, depth);
  vec3 viewVec = uOrthographic > 0.5 ? vec3(0.0, 0.0, 1.0) : normalize(-center);
  vec3 normal = normalize(textureLod(uNormal, uv, 0.0).xyz);
  // A shading normal may lean past the silhouette: keep it facing the camera.
  normal = normalize(normal + viewVec * max(0.05 - dot(normal, viewVec), 0.0));
  float pixel = pixelSize(center.z);
  vec3 origin = center + normal * pixel * 1.5;
  // The occlusion's falloff with distance, as its pass computes it: what it has taken of the
  // environment behind an occluder that far away.
  float radiusPixels = min(uRadius / pixel, uMaxPixels);
  float radius = radiusPixels * pixel;
  float falloffRange = 0.615 * radius;
  float own = occlusionNear(uv);
  vec3 tangent;
  vec3 bitangent;
  basis(normal, tangent, bitangent);
  vec3 sum = vec3(0.0);
  for (int ray = 0; ray < RAYS; ray++) {
    // The pixel's rays are spread over the hemisphere together: each a share of a turn on.
    vec2 u = fract(noise2(gl_FragCoord.xy) + float(ray) * vec2(1.0 / float(RAYS), 0.6180339887));
    float r = sqrt(u.x);
    float phi = 2.0 * PI * u.y;
    vec3 direction = normalize(tangent * (r * cos(phi)) + bitangent * (r * sin(phi)) + normal * sqrt(max(1.0 - u.x, 0.0)));
    vec3 hit = trace(origin, direction, uReach, fract(noise1(gl_FragCoord.xy) + float(ray) * 0.6180339887));
    if (hit.z <= 0.0) continue;
    // Only the front of a visible surface is known: one met from behind sends light nobody drew.
    vec4 met = textureLod(uNormal, hit.xy, 0.0);
    if (dot(met.xyz, direction) >= 0.0) continue;
    vec3 light = radianceToward(hit.xy, origin + direction * hit.z, met, -direction, 1.0);
    float taken = radiusPixels < 2.0 ? 0.0 : clamp((radius - hit.z) / falloffRange, 0.0, 1.0);
    float fade = 1.0 - smoothstep(0.7, 1.0, hit.z / uReach);
    sum += fade * (light - (1.0 - taken) * own * envAt(direction, 0.84 * uEnvMaxLod));
  }
  gl_FragColor = vec4(sum / float(RAYS), -center.z);
}
`;

// One axis of a Gaussian over the bounce (half resolution) or the reflection (full), among
// pixels of one surface: a neighbour at another depth (relative to this one's) or facing another
// way counts for nothing. `byRoughness` spreads the taps with the surface's roughness, so a
// mirror's reflection is left as sharp as it was traced and a satin one's grain is averaged.
const smoothFragment = ({ taps, sigma, byRoughness }) => /* glsl */ `
uniform sampler2D uInput;
uniform sampler2D uNormal;
uniform vec2 uStep;
uniform vec2 uSize;
varying vec2 vUv;
vec2 pixelCentre(vec2 uv) {
  return (floor(uv * uSize) + 0.5) / uSize;
}
void main() {
  vec4 center = texture2D(uInput, vUv);
  gl_FragColor = center;
  if (center.a <= 0.0) return;
  vec4 shading = textureLod(uNormal, pixelCentre(vUv), 0.0);
  float spread = ${byRoughness ? "clamp(shading.w * 5.0 - 0.25, 0.0, 1.5)" : "1.0"};
  if (spread <= 0.0) return;
  vec3 sum = center.rgb;
  float total = 1.0;
  for (int i = -${taps}; i <= ${taps}; i++) {
    if (i == 0) continue;
    vec2 at = vUv + uStep * float(i) * spread;
    vec4 tap = texture2D(uInput, at);
    float t = float(i) / ${sigma.toFixed(2)};
    float facing = max(dot(shading.xyz, textureLod(uNormal, pixelCentre(at), 0.0).xyz), 0.0);
    facing *= facing;
    facing *= facing;
    float weight = tap.a > 0.0 ? exp(-0.5 * t * t) * exp(-abs(tap.a - center.a) / (center.a * 0.02)) * facing * facing : 0.0;
    sum += tap.rgb * weight;
    total += weight;
  }
  gl_FragColor = vec4(sum / total, center.a);
}
`;

// What a reflecting ray changes of the specular light, at full resolution: where it meets a
// visible surface, that surface's radiance in place of the environment's.
const reflectFragment = ({ steps, hits, env }) => /* glsl */ `
${hits ? "#define LAB_DEBUG_HITS" : ""}
${env ? "#define LAB_DEBUG_ENV" : ""}
#define TRACE_STEPS ${steps}
#define TRACE_REFINE 4
uniform float uReach;
varying vec2 vUv;
${TONE_GLSL}
${SCENE_GLSL}
${TRACE_GLSL}
// A normal of the GGX distribution visible from Ve (Heitz 2018), in the surface's frame.
vec3 visibleNormal(vec3 Ve, float alpha, vec2 u) {
  vec3 Vh = normalize(vec3(alpha * Ve.x, alpha * Ve.y, Ve.z));
  float lengthSq = Vh.x * Vh.x + Vh.y * Vh.y;
  vec3 T1 = lengthSq > 0.0 ? vec3(-Vh.y, Vh.x, 0.0) * inversesqrt(lengthSq) : vec3(1.0, 0.0, 0.0);
  vec3 T2 = cross(Vh, T1);
  float r = sqrt(u.x);
  float phi = 2.0 * PI * u.y;
  float t1 = r * cos(phi);
  float t2 = r * sin(phi);
  float s = 0.5 * (1.0 + Vh.z);
  t2 = (1.0 - s) * sqrt(max(1.0 - t1 * t1, 0.0)) + s * t2;
  vec3 Nh = t1 * T1 + t2 * T2 + sqrt(max(0.0, 1.0 - t1 * t1 - t2 * t2)) * Vh;
  return normalize(vec3(alpha * Nh.x, alpha * Nh.y, max(0.0, Nh.z)));
}
void main() {
  float depth = depthAt(vUv);
  gl_FragColor = vec4(0.0);
  if (depth >= 1.0) return;
  vec3 center = viewAt(vUv, depth);
  // A: the pixel's view depth, for the smoothing (0: nothing drawn).
  gl_FragColor.a = -center.z;
  vec3 viewVec = uOrthographic > 0.5 ? vec3(0.0, 0.0, 1.0) : normalize(-center);
  vec4 shading = textureLod(uNormal, vUv, 0.0);
  vec4 surface = textureLod(uSurface, vUv, 0.0);
  vec3 normal = normalize(shading.xyz);
  normal = normalize(normal + viewVec * max(0.05 - dot(normal, viewVec), 0.0));
  float roughness = clamp(shading.w, 0.0, 1.0);
  float alpha = max(roughness * roughness, 1e-3);
  vec3 tangent;
  vec3 bitangent;
  basis(normal, tangent, bitangent);
  vec2 u = noise2(gl_FragCoord.xy);
  // The lobe's far tail is a handful of rays that never settle in 32 samples: left out.
  u.x *= 0.85;
  vec3 local = visibleNormal(vec3(dot(viewVec, tangent), dot(viewVec, bitangent), dot(viewVec, normal)), alpha, u);
  vec3 halfVec = normalize(tangent * local.x + bitangent * local.y + normal * local.z);
  vec3 direction = reflect(-viewVec, halfVec);
  if (dot(direction, normal) <= 0.02) return;
  // The environment the material drew along its mirror direction, and the weight it drew it by.
  vec2 scaleBias = environmentBrdf(clamp(dot(normal, viewVec), 0.0, 1.0), roughness);
  vec3 brdf = mix(vec3(0.04), surface.rgb, clamp(surface.a, 0.0, 1.0)) * scaleBias.x + scaleBias.y;
  vec3 drawn = environmentSpecular(normal, viewVec, roughness, surface, 0.0);
  #ifdef LAB_DEBUG_ENV
    // The environment's specular light as this pass takes the material to have drawn it.
    gl_FragColor.rgb = drawn;
    return;
  #endif
  float pixel = pixelSize(center.z);
  vec3 origin = center + normal * pixel * 1.5;
  vec3 hit = trace(origin, direction, uReach, noise1(gl_FragCoord.xy));
  #ifdef LAB_DEBUG_HITS
    // What each ray met: its radiance; magenta for nothing, yellow for the back of a surface.
    gl_FragColor.rgb = hit.z <= 0.0 ? vec3(1.0, 0.0, 1.0)
      : dot(textureLod(uNormal, hit.xy, 0.0).xyz, direction) >= 0.0 ? vec3(1.0, 1.0, 0.0) : radianceAt(hit.xy);
    return;
  #endif
  if (hit.z <= 0.0) return;
  vec4 met = textureLod(uNormal, hit.xy, 0.0);
  if (dot(met.xyz, direction) >= 0.0) return;
  vec3 light = radianceToward(hit.xy, origin + direction * hit.z, met, -direction, roughness);
  // Toward the screen's edge and the ray's reach the reflection gives way to the environment.
  vec2 border = min(hit.xy, 1.0 - hit.xy);
  float weight = smoothstep(0.0, 0.04, min(border.x, border.y)) * (1.0 - smoothstep(0.8, 1.0, hit.z / uReach));
  float own = occlusionAt(vUv, -center.z);
  gl_FragColor = vec4(weight * (brdf * light - own * drawn), -center.z);
}
`;

// The frame's composite (the scene's colour under its occlusion, as studioFrame.js draws it),
// and then, in scene-linear light, the bounce and the reflection.
const COMPOSITE_FRAGMENT = /* glsl */ `
uniform sampler2D uBounce;
uniform sampler2D uReflection;
uniform float uBounceStrength;
uniform float uReflectionStrength;
uniform int uDebug;
varying vec2 vUv;
${TONE_GLSL}
${SCENE_GLSL}
vec3 bounceAt(vec2 uv, float z) {
  vec2 at = uv * uOcclusionSize - 0.5;
  vec2 f = fract(at);
  ivec2 base = ivec2(floor(at));
  ivec2 last = ivec2(uOcclusionSize) - 1;
  vec3 sum = vec3(0.0);
  float total = 0.0;
  for (int y = 0; y < 2; y++) {
    for (int x = 0; x < 2; x++) {
      vec4 tap = texelFetch(uBounce, clamp(base + ivec2(x, y), ivec2(0), last), 0);
      float bilinear = (x == 0 ? 1.0 - f.x : f.x) * (y == 0 ? 1.0 - f.y : f.y);
      float weight = tap.a > 0.0 ? (bilinear + 1e-3) * exp(-abs(tap.a - z) / (z * 0.02)) : 0.0;
      sum += tap.rgb * weight;
      total += weight;
    }
  }
  return total > 1e-5 ? sum / total : vec3(0.0);
}
void main() {
  vec4 color = texture2D(uColor, vUv);
  float depth = depthAt(vUv);
  vec3 linear = toLinear(color.rgb);
  if (depth < 1.0) {
    float z = -viewAt(vUv, depth).z;
    linear *= occlusionAt(vUv, z);
    vec4 surface = textureLod(uSurface, vUv, 0.0);
    vec3 albedo = surface.rgb * (1.0 - clamp(surface.a, 0.0, 1.0));
    vec3 bounce = uBounceStrength > 0.0 ? albedo * bounceAt(vUv, z) * uBounceStrength : vec3(0.0);
    vec3 reflection = uReflectionStrength > 0.0 ? textureLod(uReflection, vUv, 0.0).rgb * uReflectionStrength : vec3(0.0);
    linear = neutral(max(neutralInverse(linear) + bounce + reflection, 0.0));
    if (uDebug == 1) linear = toLinear(textureLod(uNormal, vUv, 0.0).xyz * 0.5 + 0.5);
    if (uDebug == 2) linear = vec3(textureLod(uNormal, vUv, 0.0).w, surface.a, 0.0);
    if (uDebug == 3) linear = surface.rgb;
    if (uDebug == 4) linear = toLinear(vec3(0.5)) + bounce * 2.0;
    if (uDebug == 5) linear = toLinear(vec3(0.5)) + reflection * 2.0;
    if (uDebug == 6) linear = toLinear(vec3(0.5)) + bounceAt(vUv, z) * 0.5;
    if (uDebug >= 7) linear = neutral(textureLod(uReflection, vUv, 0.0).rgb);
  }
  gl_FragColor = vec4(toDisplay(linear), color.a);
}
`;

// The geometry draw's stand-in for a mesh's material: three's own vertex transform (instances,
// batches, morphs, skins, clipping), and the surface's shading normal, roughness, base colour and
// metalness out to two attachments.
const GEOMETRY_VERTEX = /* glsl */ `
varying vec3 vLabNormal;
varying vec3 vLabPosition;
#include <common>
#include <batching_pars_vertex>
#include <color_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
  #include <color_vertex>
  #include <batching_vertex>
  #include <beginnormal_vertex>
  #include <morphinstance_vertex>
  #include <morphnormal_vertex>
  #include <skinbase_vertex>
  #include <skinnormal_vertex>
  #include <defaultnormal_vertex>
  vLabNormal = transformedNormal;
  #include <begin_vertex>
  #include <morphtarget_vertex>
  #include <skinning_vertex>
  #include <project_vertex>
  #include <clipping_planes_vertex>
  vLabPosition = -mvPosition.xyz;
}
`;
const GEOMETRY_FRAGMENT = /* glsl */ `
uniform vec3 uBase;
uniform float uRoughness;
uniform float uMetalness;
varying vec3 vLabNormal;
varying vec3 vLabPosition;
#include <color_pars_fragment>
#include <clipping_planes_pars_fragment>
layout(location = 0) out highp vec4 labNormal;
layout(location = 1) out highp vec4 labSurface;
void main() {
  vec4 diffuseColor = vec4(uBase, 1.0);
  #include <clipping_planes_fragment>
  #include <color_fragment>
  vec3 faceNormal = normalize(cross(dFdx(vLabPosition), dFdy(vLabPosition)));
  #ifdef FLAT_SHADED
    vec3 normal = faceNormal;
  #else
    vec3 normal = dot(vLabNormal, vLabNormal) > 1e-12 ? normalize(vLabNormal) : faceNormal;
    #ifdef DOUBLE_SIDED
      if (!gl_FrontFacing) normal = -normal;
    #endif
  #endif
  labNormal = vec4(normal, uRoughness);
  labSurface = vec4(diffuseColor.rgb, uMetalness);
}
`;

const DEBUG_VIEWS = Object.freeze({ normal: 1, finish: 2, base: 3, bounce: 4, reflection: 5, irradiance: 6, hits: 7, env: 8 });

/** The lab's settings as the page gave them (`globalThis.__studioFrameLab`), or null for none. */
export function studioFrameLabSettings() {
  const given = globalThis.__studioFrameLab;
  if (!given || typeof given !== "object") return null;
  const number = (value, fallback) => (Number.isFinite(Number(value)) && value != null ? Number(value) : fallback);
  const settings = {
    ssgi: Math.max(0, number(given.ssgi, 0)),
    ssr: Math.max(0, number(given.ssr, 0)),
    // How far a bounce ray and a reflection ray reach, as shares of the model's radius.
    giReach: number(given.giReach, 0.5),
    ssrReach: number(given.ssrReach, 2),
    giRays: Math.max(1, Math.round(number(given.giRays, 2))),
    giSteps: Math.max(2, Math.round(number(given.giSteps, 10))),
    ssrSteps: Math.max(2, Math.round(number(given.ssrSteps, 16))),
    // Whether a ray's light is read from the picture so far (further bounces) or from each sample alone.
    history: given.history !== false,
    // Whether a picture's first sample is left without the lab's light, and over how many of the
    // samples after it that light fades in (`gate: false`: every sample carries it, the first too).
    gate: given.gate !== false,
    fade: Math.max(1, Math.round(number(given.fade, 8))),
    // A still's sample count, in place of the caller's (1: what a moving view shows each frame).
    samples: given.samples == null ? null : Math.max(1, Math.round(number(given.samples, 32))),
    debug: Object.hasOwn(DEBUG_VIEWS, given.debug) ? given.debug : null,
    log: given.log === true
  };
  return settings.ssgi > 0 || settings.ssr > 0 || settings.debug || settings.samples ? settings : null;
}

/**
 * The lab's passes for one frame. `shared` is the frame's own: its depth texture, scene target,
 * occlusion targets, projection matrices, pass camera, and its `fullScreenPass` and `passTarget`.
 */
export function createStudioFrameLab(THREE, lab, shared) {
  const { depthTexture, sceneTarget, accumulation, occlusionTargets, projection, projectionInverse, passCamera, fullScreenPass, passTarget } = shared;
  const geometryTarget = new THREE.WebGLRenderTarget(1, 1, {
    count: 2,
    type: THREE.HalfFloatType,
    minFilter: THREE.NearestFilter,
    magFilter: THREE.NearestFilter,
    depthBuffer: true,
    generateMipmaps: false
  });
  geometryTarget.textures[0].name = "studio-frame-lab-normal";
  geometryTarget.textures[1].name = "studio-frame-lab-surface";
  const bounceTargets = [passTarget(THREE, "studio-frame-lab-bounce"), passTarget(THREE, "studio-frame-lab-bounce-smooth")];
  const reflectionTargets = [passTarget(THREE, "studio-frame-lab-reflection"), passTarget(THREE, "studio-frame-lab-reflection-smooth")];
  const envFromView = new THREE.Matrix3();

  const sceneUniforms = () => ({
    uDepth: { value: depthTexture },
    uColor: { value: sceneTarget.texture },
    uHistory: { value: accumulation.texture },
    uHistoryOn: { value: 0 },
    uNormal: { value: geometryTarget.textures[0] },
    uSurface: { value: geometryTarget.textures[1] },
    uOcclusion: { value: occlusionTargets[0].texture },
    uOcclusionSize: { value: new THREE.Vector2(1, 1) },
    uStrength: { value: 1 },
    uPower: { value: 1 },
    uProjection: { value: projection },
    uProjectionInverse: { value: projectionInverse },
    uSize: { value: new THREE.Vector2(1, 1) },
    uOrthographic: { value: 0 },
    uFrame: { value: 0 },
    uEnv: { value: null },
    uEnvFromView: { value: envFromView },
    uEnvScale: { value: 0 },
    uEnvMaxLod: { value: 0 }
  });
  const bouncePass = fullScreenPass(THREE, bounceFragment({ rays: lab.giRays, steps: lab.giSteps }), {
    ...sceneUniforms(),
    uReach: { value: 1 },
    uRadius: { value: 1 },
    uMaxPixels: { value: 64 }
  });
  const smoothUniforms = () => ({
    uInput: { value: null },
    uNormal: { value: geometryTarget.textures[0] },
    uStep: { value: new THREE.Vector2() },
    uSize: { value: new THREE.Vector2(1, 1) }
  });
  const smoothPass = fullScreenPass(THREE, smoothFragment({ taps: 4, sigma: 2.5, byRoughness: false }), smoothUniforms());
  const reflectSmoothPass = fullScreenPass(THREE, smoothFragment({ taps: 3, sigma: 2, byRoughness: true }), smoothUniforms());
  // Blur one of a pair of targets across, then down, back into itself.
  function smooth(renderer, fullScreen, [first, second], width, height) {
    fullScreen.uniforms.uSize.value.set(width, height);
    for (const [from, into, x, y] of [[first, second, 1 / first.width, 0], [second, first, 0, 1 / first.height]]) {
      fullScreen.uniforms.uInput.value = from.texture;
      fullScreen.uniforms.uStep.value.set(x, y);
      renderer.setRenderTarget(into);
      renderer.render(fullScreen.scene, passCamera);
    }
  }
  const reflectPass = fullScreenPass(THREE, reflectFragment({ steps: lab.ssrSteps, hits: lab.debug === "hits", env: lab.debug === "env" }), {
    ...sceneUniforms(),
    uReach: { value: 1 }
  });
  const compositePass = fullScreenPass(THREE, COMPOSITE_FRAGMENT, {
    ...sceneUniforms(),
    uBounce: { value: bounceTargets[0].texture },
    uReflection: { value: reflectionTargets[0].texture },
    uBounceStrength: { value: 0 },
    uReflectionStrength: { value: 0 },
    uDebug: { value: 0 }
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
  const scenePasses = [bouncePass, reflectPass, compositePass];

  // The geometry draw's materials: one stand-in per material of the scene (one program between
  // them), and one that draws nothing for whatever the draw leaves out.
  const standIns = new WeakMap();
  const made = new Set();
  const hidden = new THREE.MeshBasicMaterial({ visible: false });
  const flip = new THREE.Matrix3().set(-1, 0, 0, 0, 1, 0, 0, 0, 1);
  const rotation = new THREE.Matrix4();
  const cameraRotation = new THREE.Matrix3();
  let logged = false;

  function standIn(object, material) {
    const surface = object.isMesh && material.visible !== false && material.depthWrite !== false
      && material.colorWrite !== false && material.transparent !== true
      && (material.isMeshStandardMaterial || material.isMeshPhongMaterial || material.isMeshLambertMaterial
        || material.isMeshBasicMaterial || material.isMeshToonMaterial);
    if (!surface) return hidden;
    let stand = standIns.get(material);
    if (!stand) {
      stand = new THREE.ShaderMaterial({
        glslVersion: THREE.GLSL3,
        vertexShader: GEOMETRY_VERTEX,
        fragmentShader: GEOMETRY_FRAGMENT,
        uniforms: { uBase: { value: new THREE.Color() }, uRoughness: { value: 1 }, uMetalness: { value: 0 } },
        clipping: true,
        toneMapped: false
      });
      standIns.set(material, stand);
      made.add(stand);
    }
    stand.uniforms.uBase.value.copy(material.color || { r: 1, g: 1, b: 1 });
    stand.uniforms.uRoughness.value = material.isMeshStandardMaterial ? material.roughness : 1;
    stand.uniforms.uMetalness.value = material.isMeshStandardMaterial ? material.metalness : 0;
    if (stand.side !== material.side || stand.flatShading !== (material.flatShading === true)
      || stand.vertexColors !== material.vertexColors) {
      stand.side = material.side;
      stand.flatShading = material.flatShading === true;
      stand.vertexColors = material.vertexColors;
      stand.needsUpdate = true;
    }
    stand.clippingPlanes = material.clippingPlanes;
    stand.clipIntersection = material.clipIntersection;
    return stand;
  }

  function logMaterials(scene) {
    const seen = new Map();
    scene.traverseVisible((object) => {
      if (!object.isMesh) return;
      for (const material of [object.material].flat()) {
        if (!material) continue;
        const key = [material.type, material.color?.getHexString?.(), material.roughness, material.metalness,
          material.transparent, material.depthWrite, material.specularIntensity, material.clearcoat,
          material.envMapIntensity, Boolean(material.map), material.vertexColors, material.flatShading, material.side,
          material.customProgramCacheKey?.(), object.name?.slice(0, 24)].join("|");
        seen.set(key, (seen.get(key) || 0) + 1);
      }
    });
    console.warn(`[studioFrameLab] materials (type|colour|roughness|metalness|transparent|depthWrite|specular|clearcoat|envMapIntensity|map|vertexColors|flat|side|program|name x count):\n${
      [...seen].map(([key, count]) => `${key} x${count}`).slice(0, 80).join("\n")}`);
  }

  function syncScene(renderer, scene, camera, index, occlusion, width, height) {
    const environment = scene.environment?.isCubeTexture ? scene.environment : null;
    if (environment) {
      rotation.makeRotationFromEuler(scene.environmentRotation);
      envFromView.setFromMatrix4(rotation).transpose();
      if (environment.isRenderTargetTexture === false) envFromView.premultiply(flip);
      envFromView.multiply(cameraRotation.setFromMatrix4(camera.matrixWorld));
    }
    for (const fullScreen of scenePasses) {
      const uniforms = fullScreen.uniforms;
      uniforms.uOcclusionSize.value.set(occlusionTargets[0].width, occlusionTargets[0].height);
      uniforms.uStrength.value = occlusion.strength;
      uniforms.uPower.value = occlusion.power;
      uniforms.uSize.value.set(width, height);
      uniforms.uOrthographic.value = camera.isOrthographicCamera ? 1 : 0;
      uniforms.uFrame.value = index % 256;
      uniforms.uHistoryOn.value = index > 0 && lab.history ? 1 : 0;
      uniforms.uEnv.value = environment;
      uniforms.uEnvScale.value = environment ? (scene.environmentIntensity ?? 1) * renderer.toneMappingExposure : 0;
      uniforms.uEnvMaxLod.value = environment ? Math.max((environment.mipmaps?.length || 1) - 1, 0) : 0;
    }
  }

  // The share of the lab's light each sample of a picture of `total` carries, gated and faded in
  // (the file's header): 0 for the first, rising to one constant, their mean over the picture 1.
  const shares = new Map();
  function sharesOf(total) {
    let found = shares.get(total);
    if (!found) {
      const ramp = Array.from({ length: total }, (_, index) => Math.min(1, index / lab.fade));
      const sum = ramp.reduce((a, b) => a + b, 0);
      found = ramp.map((value) => (sum > 0 ? value * total / sum : 0));
      shares.set(total, found);
    }
    return found;
  }

  return {
    compositePass,
    /** How much of the lab's light sample `index` of a picture of `total` samples carries. */
    weightAt(index, total) {
      if (!lab.gate || lab.debug) return 1;
      const count = Math.max(1, Math.round(total));
      return index < count ? sharesOf(count)[index] : 0;
    },
    resize(width, height, halfWidth, halfHeight) {
      geometryTarget.setSize(width, height);
      for (const target of reflectionTargets) target.setSize(width, height);
      for (const target of bounceTargets) target.setSize(halfWidth, halfHeight);
    },
    /** The geometry draw, from the camera as the frame's own draw just had it (its jitter on). */
    drawGeometry(renderer, scene, camera) {
      if (lab.log && !logged) {
        logged = true;
        logMaterials(scene);
      }
      const swapped = [];
      scene.traverseVisible((object) => {
        const material = object.material;
        if (!material || !(object.isMesh || object.isLine || object.isPoints || object.isSprite)) return;
        swapped.push(object, material);
        object.material = Array.isArray(material) ? material.map((entry) => standIn(object, entry)) : standIn(object, material);
      });
      const shadowMap = renderer.shadowMap;
      const autoUpdate = shadowMap?.autoUpdate;
      const background = scene.background;
      const ownHook = Object.hasOwn(scene, "onBeforeRender");
      const hook = scene.onBeforeRender;
      const clearColor = renderer.getClearColor(new THREE.Color());
      const clearAlpha = renderer.getClearAlpha();
      try {
        // Nothing of the frame's own draw is done again: no shadow pass, no mirrored floor draw.
        if (shadowMap) shadowMap.autoUpdate = false;
        scene.background = null;
        scene.onBeforeRender = () => {};
        renderer.setClearColor(0x000000, 0);
        renderer.setRenderTarget(geometryTarget);
        renderer.render(scene, camera);
      } finally {
        for (let i = 0; i < swapped.length; i += 2) swapped[i].material = swapped[i + 1];
        if (shadowMap) shadowMap.autoUpdate = autoUpdate;
        scene.background = background;
        if (ownHook) scene.onBeforeRender = hook;
        else delete scene.onBeforeRender;
        renderer.setClearColor(clearColor, clearAlpha);
      }
    },
    /** The bounce and the reflection of this sample, after its occlusion. */
    drawEffects(renderer, scene, camera, index, { occlusion, modelRadius, center, width, height, weight = 1 }) {
      if (lab.log && index === 0) {
        console.warn(`[studioFrameLab] model radius ${modelRadius}, centre ${[center.x, center.y, center.z]}, camera ${
          camera.position.toArray()} fov ${camera.fov} zoom ${camera.zoom}, ${width}x${height}`);
      }
      syncScene(renderer, scene, camera, index, occlusion, width, height);
      const pass = (fullScreen, into) => {
        renderer.setRenderTarget(into);
        renderer.render(fullScreen.scene, passCamera);
      };
      if (lab.ssgi > 0 || lab.debug) {
        bouncePass.uniforms.uReach.value = Math.max(modelRadius * lab.giReach, 1e-9);
        bouncePass.uniforms.uRadius.value = Math.max(modelRadius * occlusion.radius, 1e-9);
        bouncePass.uniforms.uMaxPixels.value = Math.max(height * occlusion.maxScreen, 4);
        pass(bouncePass, bounceTargets[0]);
        smooth(renderer, smoothPass, bounceTargets, width, height);
      }
      if (lab.ssr > 0 || lab.debug) {
        reflectPass.uniforms.uReach.value = Math.max(modelRadius * lab.ssrReach, 1e-9);
        pass(reflectPass, reflectionTargets[0]);
        smooth(renderer, reflectSmoothPass, reflectionTargets, width, height);
      }
      compositePass.uniforms.uBounceStrength.value = lab.ssgi * weight;
      compositePass.uniforms.uReflectionStrength.value = lab.ssr * weight;
      compositePass.uniforms.uDebug.value = lab.debug ? DEBUG_VIEWS[lab.debug] : 0;
    },
    /** GPU memory of its targets, in bytes, for a drawing buffer of `pixels` and its half-resolution `half`. */
    memoryBytes(pixels, half) {
      // Two half-float attachments and a depth buffer; two full half-float reflections; two half-resolution half-floats.
      return pixels * (8 * 2 + 4) + pixels * 8 * 2 + half * 8 * 2;
    },
    dispose() {
      geometryTarget.dispose();
      for (const target of [...reflectionTargets, ...bounceTargets]) target.dispose();
      for (const fullScreen of [bouncePass, smoothPass, reflectPass, reflectSmoothPass, compositePass]) {
        fullScreen.mesh.geometry.dispose();
        fullScreen.mesh.material.dispose();
      }
      for (const stand of made) stand.dispose();
      made.clear();
      hidden.dispose();
    }
  };
}
