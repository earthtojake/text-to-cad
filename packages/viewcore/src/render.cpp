// render.cpp: a still drawn in software, to the picture cad's OpenGL renderer draws from the same inputs
// (hosts/node/README.md, "Stills"). The scene names what is drawn and how; this rasterizes it as OpenGL would:
// triangles and one-pixel lines by multisampled coverage (the top-left rule, the standard sample positions), a depth
// buffer with the polygon offset, opaque surfaces first and see-through ones blended over them in the order given,
// a layer above the model with a depth of its own, a clip plane with its caps, and the frame resolved in linear
// light from an sRGB buffer. Surfaces are lit by OCCT's programs, ported from their GLSL: the PBR one (GGX, Schlick,
// the environment as nine spherical harmonics and prefiltered levels, baked from the image as OCCT bakes them) and
// Phong's. No OCCT is called and nothing is meshed: a part is the engine's XBM2 buffer.
//
// Opaque surfaces are drawn into a visibility buffer (a triangle's number per sample) and lit once a pixel and
// triangle afterwards, so a pixel costs one lighting however many triangles were drawn over it. Arithmetic is
// IEEE single and double with no contraction and the module's own libm, so the bytes are the same wherever the
// module runs.
#include "render.hpp"

#include <algorithm>
#include <cmath>
#include <cstring>
#include <map>
#include <memory>
#include <stdexcept>
#include <vector>

#include <zlib.h>
#if defined(__wasm_simd128__)
#include <wasm_simd128.h>
#endif

#include "value.hpp"

#if defined(VC_RENDER_TIMES)
#include <chrono>
#include <cstdio>
#define RENDER_CLOCK(name) auto name = std::chrono::steady_clock::now()
#define RENDER_SAY(label, since) \
  std::fprintf(stderr, "  %-12s %7.2f ms\n", label, \
               std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - since).count())
#else
#define RENDER_CLOCK(name)
#define RENDER_SAY(label, since)
#endif

namespace vc {
namespace {

const double PI = 3.14159265358979323846;
const float PI_F = 3.14159265358979323846f;
const float INV_PI = 0.31830988618379067f;

template <typename T>
inline T load(const uint8_t* at) {
  T value;
  std::memcpy(&value, at, sizeof(T));
  return value;
}

inline float clamp01(float v) { return v < 0 ? 0 : (v > 1 ? 1 : v); }

// Four pixels lit at once: four lanes of single floats, each lane doing exactly what one pixel's lighting does, in
// the same order, so a pixel's colour is the same however it was lit (WebAssembly's 128-bit SIMD where the module
// is built with it, else four of each operation).
typedef float f4 __attribute__((vector_size(16)));
typedef int32_t i4 __attribute__((vector_size(16)));
inline f4 splat(float v) { return f4{v, v, v, v}; }
inline f4 pick(i4 mask, f4 yes, f4 no) { return (f4)(((i4)yes & mask) | ((i4)no & ~mask)); }
inline i4 pick(i4 mask, i4 yes, i4 no) { return (yes & mask) | (no & ~mask); }
inline f4 root(f4 v) {
#if defined(__wasm_simd128__)
  return (f4)wasm_f32x4_sqrt((v128_t)v);
#else
  return f4{std::sqrt(v[0]), std::sqrt(v[1]), std::sqrt(v[2]), std::sqrt(v[3])};
#endif
}
inline f4 magnitude(f4 v) { return (f4)((i4)v & i4{0x7fffffff, 0x7fffffff, 0x7fffffff, 0x7fffffff}); }

// --- sRGB ------------------------------------------------------------------------------------------------------

// An sRGB frame buffer's two conversions: a byte's linear light, and the byte a linear value is stored as (the
// nearest level of its encoding).
struct Tone {
  float decode[256];
  float bound[257];  // bound[k]: the least linear value stored as level k
  uint8_t coarse[4097];
  Tone() {
    for (int k = 0; k < 256; ++k) decode[k] = (float)linear(k / 255.0);
    bound[0] = 0;
    for (int k = 1; k < 256; ++k) bound[k] = (float)linear((k - 0.5) / 255.0);
    bound[256] = 2;
    int level = 0;
    for (int i = 0; i <= 4096; ++i) {
      float v = i / 4096.0f;
      while (level < 255 && v >= bound[level + 1]) ++level;
      coarse[i] = (uint8_t)level;
    }
  }
  static double linear(double c) { return c <= 0.04045 ? c / 12.92 : std::pow((c + 0.055) / 1.055, 2.4); }
  inline uint8_t encode(float v) const {
    if (!(v > 0)) return 0;
    if (v >= 1) return 255;
    int level = coarse[(int)(v * 4096.0f)];
    while (v >= bound[level + 1]) ++level;
    return (uint8_t)level;
  }
  inline uint32_t pack(float r, float g, float b) const {
    return (uint32_t)encode(r) | ((uint32_t)encode(g) << 8) | ((uint32_t)encode(b) << 16) | 0xff000000u;
  }
};
const Tone& tone() {
  static const Tone made;
  return made;
}

// --- the environment ---------------------------------------------------------------------------------------------

// A cube map's face and the point on it (s, t in -1..1) a direction reads, by OpenGL's rule; and back.
inline void face_of(const float d[3], int& face, float& s, float& t) {
  float ax = std::fabs(d[0]), ay = std::fabs(d[1]), az = std::fabs(d[2]);
  if (ax >= ay && ax >= az) {
    float m = 1.0f / ax;
    if (d[0] > 0) face = 0, s = -d[2] * m, t = -d[1] * m;
    else face = 1, s = d[2] * m, t = -d[1] * m;
  } else if (ay >= az) {
    float m = 1.0f / ay;
    if (d[1] > 0) face = 2, s = d[0] * m, t = d[2] * m;
    else face = 3, s = d[0] * m, t = -d[2] * m;
  } else {
    float m = 1.0f / az;
    if (d[2] > 0) face = 4, s = d[0] * m, t = -d[1] * m;
    else face = 5, s = -d[0] * m, t = -d[1] * m;
  }
}
inline void dir_of(int face, float s, float t, float d[3]) {
  switch (face) {
    case 0: d[0] = 1, d[1] = -t, d[2] = -s; break;
    case 1: d[0] = -1, d[1] = -t, d[2] = s; break;
    case 2: d[0] = s, d[1] = 1, d[2] = t; break;
    case 3: d[0] = s, d[1] = -1, d[2] = -t; break;
    case 4: d[0] = s, d[1] = -t, d[2] = 1; break;
    default: d[0] = -s, d[1] = -t, d[2] = -1; break;
  }
}
inline void normalize(float d[3]) {
  float m = 1.0f / std::sqrt(d[0] * d[0] + d[1] * d[1] + d[2] * d[2]);
  d[0] *= m, d[1] *= m, d[2] *= m;
}

// One level of a cube map: six faces n a side. cad hands OCCT the environment as a cube map with the filter a
// texture has unless it asks for another: the nearest texel, of the nearest level.
struct Level {
  int n = 0;
  std::vector<float> t;
  float* at(int face, int i, int j) { return &t[(((size_t)face * n + j) * n + i) * 3]; }
  const float* at(int face, int i, int j) const { return &t[(((size_t)face * n + j) * n + i) * 3]; }
  inline void read(const float d[3], float out[3]) const {
    int face;
    float s, u;
    face_of(d, face, s, u);
    int i = std::min(n - 1, std::max(0, (int)((s * 0.5f + 0.5f) * n)));
    int j = std::min(n - 1, std::max(0, (int)((u * 0.5f + 0.5f) * n)));
    const float* p = at(face, i, j);
    out[0] = p[0], out[1] = p[1], out[2] = p[2];
  }
};

// One roughness of the prefiltered environment (OCCT's specular map, a level of it), its texels baked when first read.
struct Prefiltered {
  int n = 0;
  std::vector<float> t;
  std::vector<uint8_t> done;
  std::vector<float> taps;  // each sample of the lobe: the light's direction about the normal, N.L, the level it reads
};

const int ENVIRONMENT_SIDE = 256;  // the cube map cad hands OCCT (finish.CUBE_SIZE)
const int SPECULAR_POW2 = 9;       // OCCT's PbrEnvPow2Size
const int SPECULAR_LEVELS = 6;     // PbrEnvSpecMapNbLevels
const int SPECULAR_SAMPLES = 256;  // PbrEnvBakingSpecNbSamples
const float SPECULAR_PROBABILITY = 0.99f;
const int DIFFUSE_SAMPLES = 1024;  // PbrEnvBakingDiffNbSamples

inline float occ_roughness(float normalized) { return normalized * 0.99f + 0.01f; }
inline float distribution(float cos_h, float roughness) {
  float a = roughness * roughness;
  a = a / (cos_h * cos_h * (a * a - 1.0f) + 1.0f);
  return INV_PI * a * a;
}
inline float van_der_corput(unsigned number) {
  float found = 0, denominator = 2;
  while (number) {
    found += (float)(number & 1u) / denominator;
    number >>= 1;
    denominator *= 2;
  }
  return found;
}

// The image-based light as OCCT bakes it from the cube map of an equirectangular image (PBREnvBaking.fs): the
// irradiance's nine spherical harmonics and the specular map's levels. Directions here are the cube map's: OCCT
// reads a cube direction c as the model's (c.z, c.x, c.y).
struct Environment {
  std::vector<Level> mips;
  float sh[9][3];
  float brightest = 0;  // the cube map's 1, as cad hands the map over (finish.cube_pixmap)
  Prefiltered levels[SPECULAR_LEVELS];

  int pow2 = SPECULAR_POW2;       // the specular map's side, as a power of two
  int samples = SPECULAR_SAMPLES; // and the samples a texel of it is baked from

  Environment(const uint8_t* image, int width, int height, int pow2_, int samples_) : pow2(pow2_), samples(samples_) {
    Level base;
    base.n = ENVIRONMENT_SIDE;
    base.t.assign((size_t)6 * base.n * base.n * 3, 0.0f);
    for (int face = 0; face < 6; ++face)
      for (int j = 0; j < base.n; ++j)
        for (int i = 0; i < base.n; ++i) {
          float c[3];
          dir_of(face, (i + 0.5f) / base.n * 2 - 1, (j + 0.5f) / base.n * 2 - 1, c);
          double m = std::sqrt((double)c[0] * c[0] + (double)c[1] * c[1] + (double)c[2] * c[2]);
          equirectangular(image, width, height, c[2] / m, c[0] / m, c[1] / m, base.at(face, i, j));
        }
    for (int face = 0; face < 6; ++face)
      for (int j = 0; j < base.n; ++j)
        for (int i = 0; i < base.n; ++i)
          for (int c = 0; c < 3; ++c) brightest = std::max(brightest, base.at(face, i, j)[c]);
    if (!(brightest > 0)) brightest = 1;
    mips.push_back(std::move(base));
    while (mips.back().n > 1) {  // glGenerateMipmap: each texel the mean of the four under it
      const Level& above = mips.back();
      Level next;
      next.n = above.n / 2;
      next.t.assign((size_t)6 * next.n * next.n * 3, 0.0f);
      for (int face = 0; face < 6; ++face)
        for (int j = 0; j < next.n; ++j)
          for (int i = 0; i < next.n; ++i)
            for (int c = 0; c < 3; ++c)
              next.at(face, i, j)[c] = 0.25f * (above.at(face, 2 * i, 2 * j)[c] + above.at(face, 2 * i + 1, 2 * j)[c] +
                                                above.at(face, 2 * i, 2 * j + 1)[c] +
                                                above.at(face, 2 * i + 1, 2 * j + 1)[c]);
      mips.push_back(std::move(next));
    }
    harmonics();
  }

  // finish.sample: the image along a model direction, bilinear; columns once around +Z from -X through +Y, rows
  // from +Z to -Z.
  static void equirectangular(const uint8_t* image, int width, int height, double x, double y, double z, float* out) {
    double u = 0.5 - std::atan2(y, x) / (2 * PI);
    double v = 0.5 - std::asin(std::min(1.0, std::max(-1.0, z))) / PI;
    double fx = u * width - 0.5, fy = v * height - 0.5;
    int x0 = (int)std::floor(fx), y0 = (int)std::floor(fy);
    double tx = fx - x0, ty = fy - y0;
    int y1 = std::min(height - 1, std::max(0, y0 + 1));
    y0 = std::min(height - 1, std::max(0, y0));
    int x1 = ((x0 + 1) % width + width) % width;
    x0 = (x0 % width + width) % width;
    for (int c = 0; c < 3; ++c) {
      double a = load<float>(image + ((size_t)y0 * width + x0) * 12 + c * 4);
      double b = load<float>(image + ((size_t)y0 * width + x1) * 12 + c * 4);
      double d = load<float>(image + ((size_t)y1 * width + x0) * 12 + c * 4);
      double e = load<float>(image + ((size_t)y1 * width + x1) * 12 + c * 4);
      out[c] = (float)((a * (1 - tx) + b * tx) * (1 - ty) + (d * (1 - tx) + e * tx) * ty);
    }
  }

  void harmonics() {
    static const float basis[9] = {0.282095f * 0.282095f, 0.488603f * 0.488603f, 0.488603f * 0.488603f,
                                   0.488603f * 0.488603f, 1.092548f * 1.092548f, 1.092548f * 1.092548f,
                                   1.092548f * 1.092548f, 0.315392f * 0.315392f, 0.546274f * 0.546274f};
    static const float cosine[9] = {3.141593f, 2.094395f, 2.094395f, 2.094395f, 0.785398f,
                                    0.785398f, 0.785398f, 0.785398f, 0.785398f};
    double sums[9][3] = {};
    for (int at = 0; at < DIFFUSE_SAMPLES; ++at) {
      float phi = 2 * PI_F * ((float)at / (float)DIFFUSE_SAMPLES);
      float cos_theta = 2.0f * van_der_corput((unsigned)at) - 1.0f;
      float sin_theta = std::sqrt(1.0f - cos_theta * cos_theta);
      float d[3] = {sin_theta * std::cos(phi), sin_theta * std::sin(phi), cos_theta};
      float value[3];
      mips[0].read(d, value);
      const float f[9] = {1.0f, d[0], d[1], d[2], d[0] * d[2], d[1] * d[2], d[0] * d[1],
                          3.0f * d[2] * d[2] - 1.0f, d[0] * d[0] - d[1] * d[1]};
      for (int k = 0; k < 9; ++k)
        for (int c = 0; c < 3; ++c) sums[k][c] += (double)value[c] * f[k];
    }
    for (int k = 0; k < 9; ++k)
      for (int c = 0; c < 3; ++c) sh[k][c] = (float)(4.0 * sums[k][c] * (cosine[k] * basis[k]) / DIFFUSE_SAMPLES);
  }

  // The irradiance over pi along a model normal.
  inline void diffuse(const float n[3], float out[3]) const {
    const float x = n[1], y = n[2], z = n[0];  // the cube map's direction
    const float f[9] = {1.0f, x, y, z, x * z, y * z, x * y, 3.0f * z * z - 1.0f, x * x - y * y};
    for (int c = 0; c < 3; ++c) {
      float sum = 0;
      for (int k = 0; k < 9; ++k) sum += sh[k][c] * f[k];
      out[c] = sum;
    }
  }

  // textureCubeLod of the cube map: the level nearest `lod`.
  inline void at_lod(const float d[3], float lod, float out[3]) const {
    const int last = (int)mips.size() - 1;
    int level = lod > 0.5f ? (int)std::ceil(lod + 0.5f) - 1 : 0;
    mips[level > last ? last : level].read(d, out);
  }

  Prefiltered& level(int index) {
    Prefiltered& found = levels[index];
    if (found.n) return found;
    found.n = std::max(1, (1 << pow2) >> index);
    found.t.assign((size_t)6 * found.n * found.n * 3, 0.0f);
    found.done.assign((size_t)6 * found.n * found.n, 0);
    if (index == 0) return found;
    const float roughness = (float)index / (float)(SPECULAR_LEVELS - 1);
    const float real = occ_roughness(roughness);
    float quad = real * real;
    quad *= quad;
    // Graphic3d_PBRMaterial::SpecIBLMapSamplesFactor: fewer samples for a narrower lobe.
    float edge = std::sqrt((1.0f - SPECULAR_PROBABILITY) / (1.0f + (quad_of(roughness) - 1.0f) * SPECULAR_PROBABILITY));
    const int count = (int)(std::acos(edge) * 2.0f / PI_F * (float)samples);
    const float source = (float)(4.0 * PI / (6.0 * ENVIRONMENT_SIDE * ENVIRONMENT_SIDE));
    for (int at = 0; at < count; ++at) {
      float phi = 2 * PI_F * ((float)at / (float)count);
      float y = van_der_corput((unsigned)at);
      float cos_theta = std::sqrt((1.0f - y) / (1.0f + (quad - 1.0f) * y));
      float sin_theta = std::sqrt(1.0f - cos_theta * cos_theta);
      float h[3] = {sin_theta * std::cos(phi), sin_theta * std::sin(phi), cos_theta};
      float l[3] = {2 * cos_theta * h[0], 2 * cos_theta * h[1], 2 * cos_theta * h[2] - 1.0f};
      if (!(l[2] > 0)) continue;
      float solid = 1.0f / ((float)count * (distribution(cos_theta, roughness) * 0.25f + 0.0001f) + 0.0001f);
      float lod = 0.5f * std::log2(solid / source);
      found.taps.insert(found.taps.end(), {l[0], l[1], l[2], l[2], lod});
    }
    return found;
  }
  static float quad_of(float roughness) {
    float q = roughness * roughness;
    return q * q;
  }

  // OCCT keeps the specular map in bytes, of the cube map's own 0 to 1 (cad hands it the image over its brightest
  // texel): a texel is the nearest of 256 steps of that.
  void bake(int index, Prefiltered& found, int face, int i, int j, float* out) const {
    float exact[3];
    bake_exact(index, found, face, i, j, exact);
    for (int c = 0; c < 3; ++c)
      out[c] = std::floor(clamp01(exact[c] / brightest) * 255.0f + 0.5f) * (1.0f / 255.0f) * brightest;
  }
  void bake_exact(int index, Prefiltered& found, int face, int i, int j, float* out) const {
    float n[3];
    dir_of(face, (i + 0.5f) / found.n * 2 - 1, (j + 0.5f) / found.n * 2 - 1, n);
    normalize(n);
    if (index == 0) return mips[0].read(n, out);
    float x[3], y[3];
    if (std::fabs(n[2]) < 0.999f) x[0] = -n[1], x[1] = n[0], x[2] = 0;  // cross((0, 0, 1), n)
    else x[0] = 0, x[1] = -n[2], x[2] = n[1];                           // cross((1, 0, 0), n)
    normalize(x);
    y[0] = n[1] * x[2] - n[2] * x[1], y[1] = n[2] * x[0] - n[0] * x[2], y[2] = n[0] * x[1] - n[1] * x[0];
    float sum[3] = {0, 0, 0}, weight = 0;
    for (size_t at = 0; at < found.taps.size(); at += 5) {
      const float* tap = &found.taps[at];
      float l[3] = {x[0] * tap[0] + y[0] * tap[1] + n[0] * tap[2], x[1] * tap[0] + y[1] * tap[1] + n[1] * tap[2],
                    x[2] * tap[0] + y[2] * tap[1] + n[2] * tap[2]};
      float value[3];
      at_lod(l, tap[4], value);
      sum[0] += value[0] * tap[3], sum[1] += value[1] * tap[3], sum[2] += value[2] * tap[3];
      weight += tap[3];
    }
    out[0] = sum[0] / weight, out[1] = sum[1] / weight, out[2] = sum[2] / weight;
  }

  inline const float* texel(int index, Prefiltered& found, int face, int i, int j) {
    const int n = found.n;
    if ((unsigned)i >= (unsigned)n || (unsigned)j >= (unsigned)n) {  // over the face's edge: the face beside it
      float d[3], s, u;
      dir_of(face, (i + 0.5f) / n * 2 - 1, (j + 0.5f) / n * 2 - 1, d);
      face_of(d, face, s, u);
      i = std::min(n - 1, std::max(0, (int)((s * 0.5f + 0.5f) * n)));
      j = std::min(n - 1, std::max(0, (int)((u * 0.5f + 0.5f) * n)));
    }
    size_t at = ((size_t)face * n + j) * n + i;
    if (!found.done[at]) {
      bake(index, found, face, i, j, &found.t[at * 3]);
      found.done[at] = 1;
    }
    return &found.t[at * 3];
  }

  // A level at the point (s, u) of a face a direction reads (face_of), bilinear.
  inline void read_level(int index, int face, float s, float u, float out[3]) {
    Prefiltered& found = level(index);
    float fx = (s * 0.5f + 0.5f) * found.n - 0.5f, fy = (u * 0.5f + 0.5f) * found.n - 0.5f;
    int i = (int)std::floor(fx), j = (int)std::floor(fy);
    float tx = fx - i, ty = fy - j;
    const float *a, *b, *c, *e;
    const int n = found.n;
    const size_t at = ((size_t)face * n + j) * n + i;
    if (i >= 0 && j >= 0 && i + 1 < n && j + 1 < n &&
        (found.done[at] & found.done[at + 1] & found.done[at + n] & found.done[at + n + 1])) {
      // The four texels within the face and baked already: read as they lie.
      a = &found.t[at * 3], b = a + 3, c = a + (size_t)n * 3, e = c + 3;
    } else {
      a = texel(index, found, face, i, j);
      b = texel(index, found, face, i + 1, j);
      c = texel(index, found, face, i, j + 1);
      e = texel(index, found, face, i + 1, j + 1);
    }
    for (int k = 0; k < 3; ++k)
      out[k] = (a[k] * (1 - tx) + b[k] * tx) * (1 - ty) + (c[k] * (1 - tx) + e[k] * tx) * ty;
  }

  // `specular` of four directions (lanes): where each reads worked out four at a time, its texels read lane by lane.
  void specular4(const f4 r[3], float lod, int count, f4 out[3]) {
    const f4 zero = splat(0.0f), one = splat(1.0f);
    const f4 d0 = r[1], d1 = r[2], d2 = r[0];
    // face_of
    const f4 ax = magnitude(d0), ay = magnitude(d1), az = magnitude(d2);
    const i4 on_x = (ax >= ay) & (ax >= az), on_y = ~on_x & (ay >= az);
    const f4 m = one / pick(on_x, ax, pick(on_y, ay, az));
    const i4 up_x = d0 > zero, up_y = d1 > zero, up_z = d2 > zero;
    const f4 s = pick(on_x, pick(up_x, -d2, d2), pick(on_y, d0, pick(up_z, d0, -d0))) * m;
    const f4 u = pick(on_x, -d1, pick(on_y, pick(up_y, d2, -d2), -d1)) * m;
    const i4 bit = {1, 1, 1, 1};
    const i4 face = pick(on_x, ~up_x & bit, pick(on_y, (~up_y & bit) + bit + bit, (~up_z & bit) + (bit << 2)));
    int low = (int)lod;
    float share = lod - low;
    const bool last = low >= SPECULAR_LEVELS - 1;
    if (last) low = SPECULAR_LEVELS - 1;
    f4 a[3], b[3];
    level4(low, face, s, u, count, a);
    if (last || share <= 0) {
      out[0] = a[0], out[1] = a[1], out[2] = a[2];
      return;
    }
    level4(low + 1, face, s, u, count, b);
    for (int c = 0; c < 3; ++c) out[c] = a[c] * splat(1 - share) + b[c] * splat(share);
  }
  // `read_level` of four lanes.
  inline void level4(int index, i4 face, f4 s, f4 u, int count, f4 out[3]) {
    Prefiltered& found = level(index);
    const int n = found.n;
    const f4 size = splat((float)n), half = splat(0.5f);
    const f4 fx = (s * half + half) * size - half, fy = (u * half + half) * size - half;
    f4 low_x, low_y;
    for (int k = 0; k < 4; ++k) low_x[k] = std::floor(fx[k]), low_y[k] = std::floor(fy[k]);
    const f4 tx = fx - low_x, ty = fy - low_y;
    f4 ta[3], tb[3], tc[3], te[3];
    for (int k = 0; k < count; ++k) {
      const int i = (int)low_x[k], j = (int)low_y[k];
      const float *pa, *pb, *pc, *pe;
      const size_t at = ((size_t)face[k] * n + j) * n + i;
      if (i >= 0 && j >= 0 && i + 1 < n && j + 1 < n &&
          (found.done[at] & found.done[at + 1] & found.done[at + n] & found.done[at + n + 1])) {
        pa = &found.t[at * 3], pb = pa + 3, pc = pa + (size_t)n * 3, pe = pc + 3;
      } else {
        pa = texel(index, found, face[k], i, j);
        pb = texel(index, found, face[k], i + 1, j);
        pc = texel(index, found, face[k], i, j + 1);
        pe = texel(index, found, face[k], i + 1, j + 1);
      }
      for (int c = 0; c < 3; ++c) ta[c][k] = pa[c], tb[c][k] = pb[c], tc[c][k] = pc[c], te[c][k] = pe[c];
    }
    for (int k = count; k < 4; ++k)
      for (int c = 0; c < 3; ++c) ta[c][k] = tb[c][k] = tc[c][k] = te[c][k] = 0;
    const f4 one = splat(1.0f);
    for (int c = 0; c < 3; ++c)
      out[c] = (ta[c] * (one - tx) + tb[c] * tx) * (one - ty) + (tc[c] * (one - tx) + te[c] * tx) * ty;
  }

  // textureCubeLod(occSpecIBLMap, r, lod) along a model direction.
  inline void specular(const float r[3], float lod, float out[3]) {
    const float d[3] = {r[1], r[2], r[0]};
    int face;
    float s, u;
    face_of(d, face, s, u);
    int low = (int)lod;
    if (low >= SPECULAR_LEVELS - 1) return read_level(SPECULAR_LEVELS - 1, face, s, u, out);
    float share = lod - low;
    float a[3], b[3];
    read_level(low, face, s, u, a);
    if (share <= 0) {
      out[0] = a[0], out[1] = a[1], out[2] = a[2];
      return;
    }
    read_level(low + 1, face, s, u, b);
    for (int c = 0; c < 3; ++c) out[c] = a[c] * (1 - share) + b[c] * share;
  }
};

Environment& environment(const uint8_t* image, size_t size, int width, int height, int pow2, int samples) {
  static std::map<uint64_t, std::unique_ptr<Environment>> kept;
  uint64_t hash = 1469598103934665603ull ^ ((uint64_t)width << 32 | (uint32_t)height);
  hash = (hash ^ (uint64_t)pow2) * 1099511628211ull, hash = (hash ^ (uint64_t)samples) * 1099511628211ull;
  size_t at = 0;
  for (; at + 8 <= size; at += 8) hash = (hash ^ load<uint64_t>(image + at)) * 1099511628211ull, hash ^= hash >> 29;
  for (; at < size; ++at) hash = (hash ^ image[at]) * 1099511628211ull;
  auto found = kept.find(hash);
  if (found != kept.end()) return *found->second;
  if (kept.size() >= 2) kept.clear();
  return *(kept[hash] = std::make_unique<Environment>(image, width, height, pow2, samples));
}

// OCCT's split-sum table (Graphic3d_PBRMaterial::GenerateEnvLUT): the scale and the bias of F0 in the environment's
// reflection, by N.V and the normalized roughness.
const int LUT_SIDE = 32;
struct SplitSum {
  float table[LUT_SIDE][LUT_SIDE][2];
  SplitSum() {
    const int samples = 512;
    for (int row = 0; row < LUT_SIDE; ++row) {
      float roughness = occ_roughness((float)row / (LUT_SIDE - 1));
      float quad = roughness * roughness;
      float k = quad * 0.5f;
      quad *= quad;
      for (int column = 0; column < LUT_SIDE; ++column) {
        float cos_v = (float)column / (LUT_SIDE - 1);
        float view[3] = {0, std::sqrt(1.0f - cos_v * cos_v), cos_v};
        float scale = 0, bias = 0;
        for (int at = 0; at < samples; ++at) {
          float x = (float)at / (float)samples;
          float phi = 2 * PI_F * van_der_corput((unsigned)at);
          float divisor = 1.0f + (quad - 1.0f) * x;
          float cos_theta = divisor != 0 ? std::sqrt((1.0f - x) / divisor) : 0.0f;
          float sin_theta = std::sqrt(1.0f - cos_theta * cos_theta);
          float h[3] = {sin_theta * std::cos(phi), sin_theta * std::sin(phi), cos_theta};
          float vh = view[1] * h[1] + view[2] * h[2];
          float light_z = h[2] * vh * 2 - view[2];
          if (!(light_z >= 0)) continue;
          float g = light_z;
          g /= light_z * (1 - k) + k;
          g /= cos_v * (1 - k) + k;
          float f = 1 - vh;
          f *= f;
          f *= f;
          f *= 1 - vh;
          scale += g * (vh / h[2]) * (1 - f);
          bias += g * (vh / h[2]) * f;
        }
        table[row][column][0] = scale / samples;
        table[row][column][1] = bias / samples;
      }
    }
  }
  // The table's row at a normalized roughness: LUT_SIDE pairs by N.V.
  void row(float normalized, float out[LUT_SIDE][2]) const {
    float at = clamp01(normalized) * (LUT_SIDE - 1);
    int low = std::min(LUT_SIDE - 2, (int)at);
    float share = at - low;
    for (int column = 0; column < LUT_SIDE; ++column)
      for (int c = 0; c < 2; ++c)
        out[column][c] = table[low][column][c] * (1 - share) + table[low + 1][column][c] * share;
  }
};
const SplitSum& split_sum() {
  static const SplitSum made;
  return made;
}

// --- the scene ---------------------------------------------------------------------------------------------------

double number(const Value* value, double fallback) { return value && value->is_number() ? value->number() : fallback; }
double need(const Value& from, const char* name) {
  const Value* value = from.get(name);
  if (!value || !value->is_number()) throw std::invalid_argument(std::string("the scene has no ") + name);
  return value->number();
}
void numbers(const Value* value, double* out, size_t count, const char* name) {
  if (!value || value->kind != Value::LIST || value->items.size() < count)
    throw std::invalid_argument(std::string("the scene's ") + name + " is not " + std::to_string(count) + " numbers");
  for (size_t at = 0; at < count; ++at) out[at] = value->items[at].number();
}
std::string text(const Value* value, const char* fallback) {
  return value && value->kind == Value::STRING ? value->text : std::string(fallback);
}

struct Span {
  const uint8_t* data = nullptr;
  size_t size = 0;
};

// A part's XBM2 buffer (cad's mesh_format.py), its tables where they lie.
struct Mesh {
  const uint8_t* positions = nullptr;
  const uint8_t* normals = nullptr;
  const uint8_t* indices = nullptr;
  const uint8_t* edges = nullptr;
  const uint8_t* edge_points = nullptr;
  uint32_t nodes = 0, nindices = 0, nedges = 0, npoints = 0;
  double low[3] = {0, 0, 0}, high[3] = {0, 0, 0};
  bool boxed = false;

  explicit Mesh(Span span) {
    if (span.size < 80 || std::memcmp(span.data, "XBM2", 4) != 0) throw std::invalid_argument("not a mesh buffer");
    uint32_t header[20];
    std::memcpy(header, span.data, 80);
    nodes = header[2], nindices = header[3], nedges = header[5], npoints = header[6];
    auto table = [&](uint32_t offset, uint64_t bytes) {
      if ((uint64_t)offset + bytes > span.size) throw std::invalid_argument("a mesh buffer is cut short");
      return span.data + offset;
    };
    positions = table(header[8], (uint64_t)nodes * 12);
    normals = table(header[9], (uint64_t)nodes * 12);
    indices = table(header[10], (uint64_t)nindices * 4);
    edges = table(header[12], (uint64_t)nedges * 16);
    edge_points = table(header[13], (uint64_t)npoints * 12);
  }
  void box() {
    if (boxed) return;
    boxed = true;
    const uint8_t* from = nodes ? positions : edge_points;
    uint32_t count = nodes ? nodes : npoints;
    for (uint32_t at = 0; at < count; ++at)
      for (int c = 0; c < 3; ++c) {
        double v = load<float>(from + (size_t)at * 12 + c * 4);
        if (!at || v < low[c]) low[c] = v;
        if (!at || v > high[c]) high[c] = v;
      }
  }
};

enum { PBR = 0, PHONG = 1, UNLIT = 2 };
enum { FACES = 0, EDGES = 1, CAP = 2, TRIANGLES = 3 };

struct Item {
  int kind = FACES, layer = 0, shading = PBR;
  bool blend = false, cut = true, mirrored = false, textured = false, colored = false, infinite = false;
  bool repeat = false;  // its texture wraps (a face's), else it is clamped at its edges
  int texels = -1;      // a face's texture coordinates: the payload of two floats a node of its mesh
  int mesh = -1;
  double matrix[16];
  float color[3] = {1, 1, 1}, alpha = 1;
  float metallic = 0, normalized = 0.5f, roughness = 0.5f, ior = 1.5f, emission[3] = {0, 0, 0};
  float f0[3] = {0.04f, 0.04f, 0.04f};
  float lut[LUT_SIDE][2];
  float offset_factor = 0, offset_units = 0;
  float width = 1;
  uint32_t flat = 0;  // an unlit colour's number
  uint32_t first = 0, count = 0;  // its triangles or its segments
  Span texture;
  int texture_width = 0, texture_height = 0;
};

struct Light {
  float to[3];  // toward the light
  float intensity;
  int shadow_size = 0;  // the side of its shadow map, where it casts one
  float shadow_bias = 0;
};

struct Point {
  float x, y, z, iw;  // the pixel (x right, y down), the depth 0..1, 1/w
};

struct Triangle {
  uint32_t v[3];
  uint32_t item;
};

const int SAMPLE_AT[9][8][2] = {
    {},
    {{8, 8}},
    {{12, 12}, {4, 4}},
    {},
    {{6, 2}, {14, 6}, {2, 10}, {10, 14}},
    {},
    {},
    {},
    {{9, 5}, {7, 11}, {13, 9}, {5, 3}, {3, 13}, {1, 7}, {11, 15}, {15, 1}},
};

const uint32_t FLAT = 0x80000000u;
const float DEPTH_UNIT = 1.0f / 16777216.0f;  // a 24-bit depth buffer's least step: glPolygonOffset's unit
const float DEPTH_FAR = 16777215.0f;
// A depth as OpenGL's 24-bit buffer keeps it: the nearest of its steps (held as a float, which holds each exactly).
// Two surfaces a hair apart are then at one depth, and the later drawn has the pixel, as on OpenGL.
inline float kept_depth(float z) {
  return (float)(int32_t)((z < 0 ? 0.0f : (z > 2 ? 2.0f : z)) * DEPTH_FAR + 0.5f);
}
// The same of four samples.
inline f4 kept_depth4(f4 z) {
  const f4 zero = splat(0.0f), two = splat(2.0f);
  const f4 kept = pick(z < zero, zero, pick(z > two, two, z)) * splat(DEPTH_FAR) + splat(0.5f);
  return __builtin_convertvector(__builtin_convertvector(kept, i4), f4);
}
inline f4 load4(const float* at) {
  f4 v;
  std::memcpy(&v, at, sizeof v);
  return v;
}
inline i4 load4(const uint32_t* at) {
  i4 v;
  std::memcpy(&v, at, sizeof v);
  return v;
}
inline int bits_of(i4 mask) { return (mask[0] & 1) | (mask[1] & 2) | (mask[2] & 4) | (mask[3] & 8); }
const double GUARD = 8192;                    // pixels beyond the picture a triangle may reach before it is clipped

// A triangle set up for the rasterizer: its edges as integer functions of the pixel (8 bits below it), its depth a
// plane.
struct Setup {
  int x0, x1, y0, y1;
  int64_t a[4], b[4], c[4];  // a triangle's fourth edge holds everywhere
  int64_t off[4][8], off_low[4], off_high[4];
  float zx, zy, z0;
  float zoff[8];
  bool cut;
  float cx, cy, c0;  // the clip plane's distance over w, a plane too
};

struct Renderer {
  int width = 0, height = 0, samples = 8;
  bool perspective = false;
  double eye[3], right[3], up[3], ahead[3];
  double pixel = 1, focal = 1, near = 0, far = 1;
  float background[3] = {1, 1, 1};
  bool lit = false, phong = false, has_clip = false;
  double clip[4] = {0, 0, 0, 0};
  std::vector<Light> lights;
  float ambient = 0;      // the environment's strength, or Phong's ambient light
  float specular = 0, shininess = 0;
  Environment* env = nullptr;

  bool shadow_pass = false;  // this is a light's view of the scene: its opaque faces' depth, for the shadow map
  bool depth_only = false;   // the picture asked for is the depth
  int shadow_light = -1;     // the light that casts a shadow (the first that asks)
  std::vector<float> shadow_map;  // the depth it sees, a texel a float 0..1, rows from the top
  int shadow_size = 0;
  double shadow_axes[3][4];  // a point of the model to the map's texel (x, y) and its depth there
  std::vector<float> lit_at;  // three a point: where the shadow's light sees it
  std::vector<float> fourth;  // one a point: a vertex colour's alpha
  bool has_texels = false;    // some face is textured: every point has texture coordinates
  std::vector<float> texcoords;  // two a point, where has_texels
  Span backdrop;              // a picture behind everything, stretched over the frame: RGB bytes, sRGB
  int backdrop_width = 0, backdrop_height = 0;
  std::vector<uint32_t> behind;  // it, a pixel of the frame each
  std::vector<float> own_depth;
  std::vector<uint32_t> own_color;
  std::vector<Span> payloads;
  Span matrices;  // sixteen doubles each, column-major: what an item's "matrix" numbers
  std::vector<Mesh> meshes;
  std::vector<Item> items;
  std::vector<Point> points;
  std::vector<float> attributes;  // three a point: a face's normal (the model's), or a texture coordinate
  std::vector<float> cuts;        // a point's distance from the clip plane, over w
  std::vector<uint8_t> outside;   // a point before the near plane or far outside the picture
  std::vector<Triangle> triangles;
  std::vector<uint32_t> segments;  // pairs of points
  std::vector<uint32_t> flats;     // the unlit colours, as stored
  std::map<std::string, uint32_t> placed;

  // Per sample: the depth, and a triangle's number while the opaque are drawn, then the colour stored. Kept from
  // one still to the next (the module is one thread): a frame's worth is not asked of the allocator each time.
  static std::vector<float>& depths() {
    static std::vector<float> kept;
    return kept;
  }
  static std::vector<uint32_t>& colors() {
    static std::vector<uint32_t> kept;
    return kept;
  }
  explicit Renderer(bool light = false)
      : shadow_pass(light), depth(light ? own_depth : depths()), color(light ? own_color : colors()) {}
  std::vector<float>& depth;
  std::vector<uint32_t>& color;
  float* depth_at = nullptr;
  uint32_t* color_at = nullptr;
  bool depth_written = false;  // since the depth was cleared: while nothing has, what lies between the planes passes it
  int sx[8], sy[8];  // the samples of a pixel, in 1/256 of it
  int sx_low = 0, sx_high = 0, sy_low = 0, sy_high = 0;
  double fsx[8], fsy[8];

  // --- reading ---

  Span payload(const Value* index, const char* name) const {
    if (!index || !index->is_number() || index->number() < 0 || index->number() >= payloads.size())
      throw std::invalid_argument(std::string("the scene's ") + name + " names no payload");
    return payloads[(size_t)index->number()];
  }

  uint32_t flat_of(const float rgb[3]) {
    uint32_t stored = tone().pack(clamp01(rgb[0]), clamp01(rgb[1]), clamp01(rgb[2]));
    for (size_t at = 0; at < flats.size(); ++at)
      if (flats[at] == stored) return FLAT | (uint32_t)at;
    flats.push_back(stored);
    return FLAT | (uint32_t)(flats.size() - 1);
  }

  void read(const Value& scene, const uint8_t* blob, size_t size) {
    width = (int)need(scene, "width"), height = (int)need(scene, "height");
    if (width < 1 || height < 1 || width > 16384 || height > 16384)
      throw std::invalid_argument("the scene's picture is not 1 to 16384 pixels a side");
    samples = (int)number(scene.get("samples"), 8);
    if (shadow_pass) width = height = shadow_size, samples = 1;
    if (samples != 1 && samples != 2 && samples != 4 && samples != 8)
      throw std::invalid_argument("the scene's samples are not 1, 2, 4 or 8");
    // OpenGL's y runs up the picture, and its samples and its fill rule with it.
    for (int s = 0; s < samples; ++s) {
      sx[s] = SAMPLE_AT[samples][s][0] * 16, sy[s] = (16 - SAMPLE_AT[samples][s][1]) * 16;
      fsx[s] = sx[s] / 256.0, fsy[s] = sy[s] / 256.0;
      sx_low = s ? std::min(sx_low, sx[s]) : sx[s], sx_high = s ? std::max(sx_high, sx[s]) : sx[s];
      sy_low = s ? std::min(sy_low, sy[s]) : sy[s], sy_high = s ? std::max(sy_high, sy[s]) : sy[s];
    }
    double three[3];
    if (scene.get("background")) {
      numbers(scene.get("background"), three, 3, "background");
      for (int c = 0; c < 3; ++c) background[c] = (float)three[c];
    }
    size_t at = 0;
    if (const Value* lengths = scene.get("payloads"))
      for (const Value& length : lengths->items) {
        size_t bytes = (size_t)length.number();
        if (at + bytes > size) throw std::invalid_argument("the scene's payloads are longer than what came with it");
        payloads.push_back({blob + at, bytes});
        at += bytes;
      }
    if (const Value* list = scene.get("meshes"))
      for (const Value& index : list->items) meshes.emplace_back(payload(&index, "mesh"));
    if (const Value* shared = scene.get("matrices")) matrices = payload(shared, "matrices");
    if (const Value* picture = scene.get("backdrop")) {
      backdrop = payload(picture->get("payload"), "backdrop");
      backdrop_width = (int)need(*picture, "width"), backdrop_height = (int)need(*picture, "height");
      if (backdrop_width < 1 || backdrop_height < 1 || (size_t)backdrop_width * backdrop_height * 3 != backdrop.size)
        throw std::invalid_argument("the scene's backdrop is not width x height RGB bytes");
    }
    if (const Value* plane = scene.get("clip")) {
      numbers(plane, clip, 4, "clip");
      has_clip = true;
    }
    read_lights(scene);
    const Value* draw = scene.get("draw");
    if (draw)
      for (const Value& entry : draw->items) read_item(entry);
    if (!shadow_pass) read_camera(scene);
  }

  void read_lights(const Value& scene) {
    const Value* light = scene.get("light");
    const Value* colour_only = scene.get("phong");
    const Value* from = light ? light : colour_only;
    if (!from) return;
    if (const Value* list = from->get("lights"))
      for (const Value& entry : list->items) {
        double d[3];
        numbers(entry.get("direction"), d, 3, "light's direction");
        double m = std::sqrt(d[0] * d[0] + d[1] * d[1] + d[2] * d[2]);
        Light found;
        for (int c = 0; c < 3; ++c) found.to[c] = (float)(-d[c] / m);
        found.intensity = (float)number(entry.get("intensity"), 1);
        if (const Value* cast = entry.get("shadow")) {
          found.shadow_size = (int)number(cast->get("resolution"), 4096);
          found.shadow_bias = (float)number(cast->get("bias"), 0.002);
          if (found.shadow_size < 16 || found.shadow_size > 8192)
            throw std::invalid_argument("the scene's shadow map is not 16 to 8192 texels a side");
          if (shadow_light < 0) shadow_light = (int)lights.size();
        }
        lights.push_back(found);
      }
    if (light) {
      lit = true;
      if (const Value* image = light->get("environment")) {
        Span span = payload(image->get("payload"), "environment");
        int w = (int)need(*image, "width"), h = (int)need(*image, "height");
        if (w < 1 || h < 1 || (size_t)w * h * 12 != span.size)
          throw std::invalid_argument("the scene's environment is not width x height x 3 floats");
        int pow2 = (int)number(image->get("specularSize"), SPECULAR_POW2);
        int baked = (int)number(image->get("specularSamples"), SPECULAR_SAMPLES);
        if (pow2 < 1 || pow2 > 11 || baked < 1 || baked > 65536)
          throw std::invalid_argument("the scene's environment is baked at no size OCCT bakes one");
        if (!shadow_pass) env = &environment(span.data, span.size, w, h, pow2, baked);
        ambient = (float)number(image->get("intensity"), 1);
      }
    } else {
      phong = true;
      ambient = (float)number(from->get("ambient"), 0);
      specular = (float)number(from->get("specular"), 0);
      shininess = (float)number(from->get("shininess"), 0) * 128.0f;
    }
  }

  static int layer_of(const Value& entry) {
    std::string name = text(entry.get("layer"), "default");
    if (name == "default") return 0;
    if (name == "top") return 1;
    if (name == "topmost") return 2;
    throw std::invalid_argument("the scene has no layer " + name);
  }

  void read_texture(Item& item, const Value& picture) {
    item.texture = payload(picture.get("payload"), "texture");
    item.texture_width = (int)need(picture, "width"), item.texture_height = (int)need(picture, "height");
    if (item.texture_width < 1 || item.texture_height < 1 ||
        (size_t)item.texture_width * item.texture_height * 4 != item.texture.size)
      throw std::invalid_argument("the scene's texture is not width x height RGBA bytes");
    item.textured = true;
  }

  void read_item(const Value& entry) {
    Item item;
    static const double identity[16] = {1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1};
    std::memcpy(item.matrix, identity, sizeof identity);
    if (const Value* given = entry.get("matrix")) {
      if (given->is_number()) {  // its place in the scene's "matrices"
        double at = given->number();
        if (at < 0 || (at + 1) * 128 > matrices.size) throw std::invalid_argument("the scene has no matrix " + given->text);
        for (int k = 0; k < 16; ++k) item.matrix[k] = load<double>(matrices.data + (size_t)at * 128 + k * 8);
      } else {
        numbers(given, item.matrix, 16, "matrix");
      }
    }
    const double* m = item.matrix;
    double det = m[0] * (m[5] * m[10] - m[6] * m[9]) - m[4] * (m[1] * m[10] - m[2] * m[9]) +
                 m[8] * (m[1] * m[6] - m[2] * m[5]);
    item.mirrored = det < 0;
    item.layer = layer_of(entry);
    double four[4];
    const Value* named;
    auto mesh_of = [&](const Value* index) {
      if (!index->is_number() || index->number() < 0 || index->number() >= meshes.size())
        throw std::invalid_argument("the scene draws a mesh it has not");
      return (int)index->number();
    };
    if ((named = entry.get("faces"))) {
      item.kind = FACES;
      item.mesh = mesh_of(named);
      std::string shading = text(entry.get("shading"), "pbr");
      item.shading = shading == "pbr" ? PBR : shading == "phong" ? PHONG : shading == "unlit" ? UNLIT : -1;
      if (item.shading < 0) throw std::invalid_argument("the scene has no shading " + shading);
      if ((item.shading == PBR && !lit) || (item.shading == PHONG && !phong))
        throw std::invalid_argument("the scene lights nothing by " + shading);
      numbers(entry.get("color"), four, 3, "color");
      for (int c = 0; c < 3; ++c) item.color[c] = (float)four[c];
      item.alpha = (float)number(entry.get("alpha"), 1);
      item.blend = item.alpha < 1;
      if (item.shading == PBR) {
        item.metallic = (float)number(entry.get("metallic"), 0);
        float rough = (float)number(entry.get("roughness"), 0.5);
        item.normalized = clamp01((rough - 0.01f) / 0.99f);  // finish.occt_roughness
        item.roughness = occ_roughness(item.normalized);
        item.ior = (float)number(entry.get("ior"), 1.5);
        if (entry.get("emission")) {
          numbers(entry.get("emission"), four, 3, "emission");
          for (int c = 0; c < 3; ++c) item.emission[c] = (float)four[c];
        }
        float dielectric = (1.0f - item.ior) / (1.0f + item.ior);
        dielectric *= dielectric;
        for (int c = 0; c < 3; ++c) item.f0[c] = dielectric + (item.color[c] - dielectric) * item.metallic;
        split_sum().row(item.normalized, item.lut);
      } else if (item.shading == UNLIT) {
        item.flat = flat_of(item.color);
      }
      if (entry.get("offset")) {
        numbers(entry.get("offset"), four, 2, "offset");
        item.offset_factor = (float)four[0], item.offset_units = (float)four[1];
      }
      if (const Value* picture = entry.get("texture")) {  // a base colour texture over the colour, by `texels`
        const Value* given = entry.get("texels");
        Span coordinates = payload(given, "texels");
        if (coordinates.size < (size_t)meshes[item.mesh].nodes * 8)
          throw std::invalid_argument("the scene's texels are fewer than the mesh's nodes");
        item.texels = (int)given->number();
        read_texture(item, *picture);
        item.repeat = true;
        has_texels = true;
      }
      place_faces(item, entry.get("ranges"));
    } else if ((named = entry.get("edges"))) {
      item.kind = EDGES;
      item.mesh = mesh_of(named);
      numbers(entry.get("color"), four, 3, "color");
      for (int c = 0; c < 3; ++c) item.color[c] = (float)four[c];
      item.flat = flat_of(item.color);
      item.width = (float)number(entry.get("width"), 1);
      uint32_t classes = 0;
      if (const Value* list = entry.get("classes"))
        for (const Value& code : list->items) classes |= 1u << ((unsigned)code.number() & 31u);
      else classes = ~0u;
      place_edges(item, classes);
    } else if ((named = entry.get("lines"))) {
      item.kind = EDGES;
      numbers(entry.get("color"), four, 3, "color");
      for (int c = 0; c < 3; ++c) item.color[c] = (float)four[c];
      item.flat = flat_of(item.color);
      item.width = (float)number(entry.get("width"), 1);
      const Value* cut = entry.get("clip");
      item.cut = !(cut && cut->kind == Value::BOOL && !cut->flag);
      place_triangles(item, *named);
    } else if ((named = entry.get("cap"))) {
      item.kind = CAP;
      item.mesh = mesh_of(named);
      numbers(entry.get("color"), four, 3, "color");
      for (int c = 0; c < 3; ++c) item.color[c] = (float)four[c];
      item.flat = flat_of(item.color);
      item.cut = false;
      place_faces(item, nullptr);
    } else if ((named = entry.get("triangles"))) {
      item.kind = TRIANGLES;
      item.shading = UNLIT;
      if (entry.get("color")) {
        numbers(entry.get("color"), four, 4, "color");
        for (int c = 0; c < 3; ++c) item.color[c] = (float)four[c];
        item.alpha = (float)four[3];
      }
      const Value* blend = entry.get("blend");
      item.blend = (blend && blend->kind == Value::BOOL && blend->flag) || item.alpha < 1;
      const Value* cut = entry.get("clip");
      item.cut = !(cut && cut->kind == Value::BOOL && !cut->flag);
      const Value* endless = entry.get("infinite");
      item.infinite = endless && endless->kind == Value::BOOL && endless->flag;
      if (const Value* colors = named->get("colors")) {
        item.colored = colors->is_number();
        if (item.colored) item.blend = true;  // a vertex's colour has its alpha
      }
      if (entry.get("offset")) {
        numbers(entry.get("offset"), four, 2, "offset");
        item.offset_factor = (float)four[0], item.offset_units = (float)four[1];
      }
      if (const Value* picture = entry.get("texture")) read_texture(item, *picture);
      place_triangles(item, *named);
    } else {
      throw std::invalid_argument("the scene draws something that is no faces, edges, lines, cap or triangles");
    }
    items.push_back(item);
  }

  // --- the camera ---

  // The box of what is drawn (V3d's primary box: an item kept out of the fit is its box's centre there), and the
  // box of all of it (its graphic box, an item kept out of the fit whole), which the planes are fitted to.
  double low[3], high[3], all_low[3], all_high[3];
  bool bounded = false, all_bounded = false;
  void bound(const double p[3]) {
    for (int c = 0; c < 3; ++c) {
      if (!bounded || p[c] < low[c]) low[c] = p[c];
      if (!bounded || p[c] > high[c]) high[c] = p[c];
    }
    bounded = true;
    bound_all(p);
  }
  void bound_all(const double p[3]) {
    for (int c = 0; c < 3; ++c) {
      if (!all_bounded || p[c] < all_low[c]) all_low[c] = p[c];
      if (!all_bounded || p[c] > all_high[c]) all_high[c] = p[c];
    }
    all_bounded = true;
  }
  static void transform(const double* m, const double p[3], double out[3]) {
    for (int c = 0; c < 3; ++c) out[c] = m[c] * p[0] + m[4 + c] * p[1] + m[8 + c] * p[2] + m[12 + c];
  }

  // The camera is read last, the points placed since by `project`: so the items above keep what they need to be
  // placed (`pending`) until the near and far planes are fitted to what is drawn, as V3d_View::ZFitAll fits them.
  struct Pending {
    size_t item;
    const Value* source;
    const Value* ranges;
    uint32_t classes;
  };
  std::vector<Pending> pending;
  std::vector<const Value*> sources;

  void place_faces(Item& item, const Value* ranges) {
    Mesh& mesh = meshes[item.mesh];
    mesh.box();
    box_of(mesh, item.matrix);
    pending.push_back({items.size(), nullptr, ranges, 0});
  }
  void place_edges(Item& item, uint32_t classes) {
    Mesh& mesh = meshes[item.mesh];
    mesh.box();
    box_of(mesh, item.matrix);
    pending.push_back({items.size(), nullptr, nullptr, classes});
  }
  void place_triangles(Item& item, const Value& source) {
    Span positions = payload(source.get("positions"), "positions");
    double own_low[3], own_high[3];
    for (size_t at = 0; at + 12 <= positions.size; at += 12) {
      double p[3] = {load<float>(positions.data + at), load<float>(positions.data + at + 4),
                     load<float>(positions.data + at + 8)}, w[3];
      transform(item.matrix, p, w);
      if (!item.infinite) {
        bound(w);
        continue;
      }
      bound_all(w);
      for (int c = 0; c < 3; ++c) {
        if (!at || w[c] < own_low[c]) own_low[c] = w[c];
        if (!at || w[c] > own_high[c]) own_high[c] = w[c];
      }
    }
    if (item.infinite && positions.size >= 12) {  // Graphic3d_Layer's centerOfinfiniteBndBox
      const double centre[3] = {(own_low[0] + own_high[0]) / 2, (own_low[1] + own_high[1]) / 2,
                                (own_low[2] + own_high[2]) / 2};
      bound(centre);
    }
    pending.push_back({items.size(), &source, nullptr, 0});
  }
  void box_of(const Mesh& mesh, const double* matrix) {
    if (!mesh.nodes && !mesh.npoints) return;
    double lo[3], hi[3];
    bool any = false;
    for (int corner = 0; corner < 8; ++corner) {
      double p[3] = {corner & 1 ? mesh.high[0] : mesh.low[0], corner & 2 ? mesh.high[1] : mesh.low[1],
                     corner & 4 ? mesh.high[2] : mesh.low[2]}, w[3];
      transform(matrix, p, w);
      for (int c = 0; c < 3; ++c) {
        if (!any || w[c] < lo[c]) lo[c] = w[c];
        if (!any || w[c] > hi[c]) hi[c] = w[c];
      }
      any = true;
    }
    bound(lo);
    bound(hi);
  }

  void read_camera(const Value& scene) {
    const Value* camera = scene.get("camera");
    if (!camera) throw std::invalid_argument("the scene has no camera");
    double target[3], given_up[3], back[3];
    numbers(camera->get("eye"), eye, 3, "camera's eye");
    numbers(camera->get("target"), target, 3, "camera's target");
    numbers(camera->get("up"), given_up, 3, "camera's up");
    std::string projection = text(camera->get("projection"), "orthographic");
    perspective = projection == "perspective";
    if (!perspective && projection != "orthographic")
      throw std::invalid_argument("the scene has no projection " + projection);
    double m = 0;
    for (int c = 0; c < 3; ++c) back[c] = eye[c] - target[c], m += back[c] * back[c];
    m = std::sqrt(m);
    if (!(m > 0)) throw std::invalid_argument("the scene's camera stands on its target");
    for (int c = 0; c < 3; ++c) back[c] /= m, ahead[c] = -back[c];
    right[0] = given_up[1] * back[2] - given_up[2] * back[1];
    right[1] = given_up[2] * back[0] - given_up[0] * back[2];
    right[2] = given_up[0] * back[1] - given_up[1] * back[0];
    m = std::sqrt(right[0] * right[0] + right[1] * right[1] + right[2] * right[2]);
    if (!(m > 0)) throw std::invalid_argument("the scene's camera looks along its up");
    for (int c = 0; c < 3; ++c) right[c] /= m;
    up[0] = back[1] * right[2] - back[2] * right[1];
    up[1] = back[2] * right[0] - back[0] * right[2];
    up[2] = back[0] * right[1] - back[1] * right[0];
    if (perspective) focal = (height / 2.0) / std::tan(need(*camera, "fov") * PI / 360.0);
    else pixel = need(*camera, "height") / height;
    if (!(perspective ? focal > 0 : pixel > 0)) throw std::invalid_argument("the scene's camera sees nothing");
    // Graphic3d_Camera::ZFitAll at scale 1: the box of all that is drawn between the planes; in perspective the
    // near plane no nearer than the primary box's middle allows.
    auto reach = [&](const double* lo, const double* hi, double& least, double& most) {
      for (int corner = 0; corner < 8; ++corner) {
        double d = 0;
        for (int c = 0; c < 3; ++c) d += ((corner >> c & 1 ? hi[c] : lo[c]) - eye[c]) * ahead[c];
        if (!corner || d < least) least = d;
        if (!corner || d > most) most = d;
      }
    };
    double least = 0, most = 1;
    if (all_bounded) reach(all_low, all_high, least, most);
    double slack = 1e-6 * (std::fabs(least) + std::fabs(most) + (most - least)) + 1e-9;
    near = least - slack, far = most + slack;
    if (perspective) {
      if (bounded) reach(low, high, least, most);
      double range = most - least;
      double z = least < 0 ? range / 2 : range / 2 + least;
      if (near < z * 5.97e-4) near = z * 5.97e-4;
      if (near < 1e-9) near = 1e-9;
      if (far <= near) far = near * 2;
    }
    if (const Value* given = camera->get("near")) near = given->number();
    if (const Value* given = camera->get("far")) far = given->number();
    if (!(far > near)) far = near + 1;
  }

  // A point of the model, placed: view coordinates (right, up, depth along the view).
  inline void view_of(const double w[3], double v[3]) const {
    double d[3] = {w[0] - eye[0], w[1] - eye[1], w[2] - eye[2]};
    v[0] = d[0] * right[0] + d[1] * right[1] + d[2] * right[2];
    v[1] = d[0] * up[0] + d[1] * up[1] + d[2] * up[2];
    v[2] = d[0] * ahead[0] + d[1] * ahead[1] + d[2] * ahead[2];
  }
  // And on the picture; false where it cannot be drawn as it is (before the near plane, or far outside).
  inline bool project(const double v[3], Point& out) const {
    if (perspective) {
      if (v[2] < near) return false;
      double iw = 1.0 / v[2];
      double x = width / 2.0 + focal * v[0] * iw, y = height / 2.0 - focal * v[1] * iw;
      out.x = (float)x, out.y = (float)y;
      out.z = (float)(far / (far - near) * (1.0 - near * iw));
      out.iw = (float)iw;
      return x > -GUARD && x < width + GUARD && y > -GUARD && y < height + GUARD;
    }
    double x = width / 2.0 + v[0] / pixel, y = height / 2.0 - v[1] / pixel;
    out.x = (float)x, out.y = (float)y;
    out.z = (float)((v[2] - near) / (far - near));
    out.iw = 1.0f;
    return x > -GUARD && x < width + GUARD && y > -GUARD && y < height + GUARD;
  }

  inline double cut_of(const double w[3]) const {
    return clip[0] * w[0] + clip[1] * w[1] + clip[2] * w[2] + clip[3];
  }

  uint32_t add_point(const double w[3], const float attribute[3], float alpha = 1) {
    double v[3];
    view_of(w, v);
    Point p = {0, 0, 0, 1};
    bool inside = project(v, p);
    points.push_back(p);
    attributes.insert(attributes.end(), attribute, attribute + 3);
    cuts.push_back(has_clip ? (float)(cut_of(w) * (perspective && inside ? p.iw : 1.0f)) : 0.0f);
    outside.push_back(inside ? 0 : 1);
    fourth.push_back(alpha);
    if (has_texels) texcoords.insert(texcoords.end(), {0.0f, 0.0f});
    if (shadow_size) {
      float seen[3];
      shadow_of(w, seen);
      lit_at.insert(lit_at.end(), seen, seen + 3);
    }
    return (uint32_t)(points.size() - 1);
  }
  // Where the shadow's light sees a point of the model: the map's texel (x, y) and the depth there.
  inline void shadow_of(const double w[3], float out[3]) const {
    for (int r = 0; r < 3; ++r)
      out[r] = (float)(shadow_axes[r][0] * w[0] + shadow_axes[r][1] * w[1] + shadow_axes[r][2] * w[2] + shadow_axes[r][3]);
  }

  // A mesh's nodes (or its edges' points) placed by a matrix, once for every item that draws them.
  uint32_t place(int mesh_index, const double* matrix, bool edge_points, int texels = -1) {
    std::string key((const char*)matrix, 16 * sizeof(double));
    key.push_back((char)edge_points);
    key.append((const char*)&mesh_index, sizeof mesh_index);
    key.append((const char*)&texels, sizeof texels);
    auto found = placed.find(key);
    if (found != placed.end()) return found->second;
    const Mesh& mesh = meshes[mesh_index];
    const uint32_t base = (uint32_t)points.size();
    const double* m = matrix;
    // A normal goes by the inverse transpose: the cofactors (here a column after a column), by the determinant's sign.
    double co[9] = {m[5] * m[10] - m[6] * m[9], m[6] * m[8] - m[4] * m[10], m[4] * m[9] - m[5] * m[8],
                    m[2] * m[9] - m[1] * m[10], m[0] * m[10] - m[2] * m[8], m[1] * m[8] - m[0] * m[9],
                    m[1] * m[6] - m[2] * m[5], m[2] * m[4] - m[0] * m[6], m[0] * m[5] - m[1] * m[4]};
    if (m[0] * co[0] + m[4] * co[3] + m[8] * co[6] < 0)
      for (double& value : co) value = -value;
    // The placement and the camera as one matrix (a row of it the view's right, up or depth), and the clip
    // plane as the part's own.
    const double* axes[3] = {right, up, ahead};
    double vm[3][4], cut[4] = {0, 0, 0, 0};
    for (int r = 0; r < 3; ++r) {
      for (int c = 0; c < 3; ++c) vm[r][c] = axes[r][0] * m[c * 4] + axes[r][1] * m[c * 4 + 1] + axes[r][2] * m[c * 4 + 2];
      vm[r][3] = axes[r][0] * (m[12] - eye[0]) + axes[r][1] * (m[13] - eye[1]) + axes[r][2] * (m[14] - eye[2]);
    }
    if (has_clip) {
      for (int c = 0; c < 3; ++c) cut[c] = clip[0] * m[c * 4] + clip[1] * m[c * 4 + 1] + clip[2] * m[c * 4 + 2];
      cut[3] = clip[0] * m[12] + clip[1] * m[13] + clip[2] * m[14] + clip[3];
    }
    const uint32_t count = edge_points ? mesh.npoints : mesh.nodes;
    const uint8_t* from = edge_points ? mesh.edge_points : mesh.positions;
    points.resize((size_t)base + count), attributes.resize(((size_t)base + count) * 3);
    cuts.resize((size_t)base + count), outside.resize((size_t)base + count);
    fourth.resize((size_t)base + count, 1.0f);
    if (has_texels) {
      texcoords.resize(((size_t)base + count) * 2, 0.0f);
      if (texels >= 0)
        for (uint32_t at = 0; at < count; ++at)
          texcoords[((size_t)base + at) * 2] = load<float>(payloads[texels].data + (size_t)at * 8),
          texcoords[((size_t)base + at) * 2 + 1] = load<float>(payloads[texels].data + (size_t)at * 8 + 4);
    }
    double seen[3][4];  // the shadow's light, of the part's own coordinates
    if (shadow_size) {
      lit_at.resize(((size_t)base + count) * 3);
      for (int r = 0; r < 3; ++r) {
        for (int c = 0; c < 3; ++c)
          seen[r][c] = shadow_axes[r][0] * m[c * 4] + shadow_axes[r][1] * m[c * 4 + 1] + shadow_axes[r][2] * m[c * 4 + 2];
        seen[r][3] = shadow_axes[r][0] * m[12] + shadow_axes[r][1] * m[13] + shadow_axes[r][2] * m[14] + shadow_axes[r][3];
      }
    }
    for (uint32_t at = 0; at < count; ++at) {
      const double p[3] = {load<float>(from + (size_t)at * 12), load<float>(from + (size_t)at * 12 + 4),
                           load<float>(from + (size_t)at * 12 + 8)};
      const double v[3] = {vm[0][0] * p[0] + vm[0][1] * p[1] + vm[0][2] * p[2] + vm[0][3],
                           vm[1][0] * p[0] + vm[1][1] * p[1] + vm[1][2] * p[2] + vm[1][3],
                           vm[2][0] * p[0] + vm[2][1] * p[1] + vm[2][2] * p[2] + vm[2][3]};
      Point& point = points[base + at];
      point = {0, 0, 0, 1};
      const bool inside = project(v, point);
      outside[base + at] = inside ? 0 : 1;
      cuts[base + at] = has_clip ? (float)((cut[0] * p[0] + cut[1] * p[1] + cut[2] * p[2] + cut[3]) *
                                           (perspective && inside ? point.iw : 1.0f))
                                 : 0.0f;
      if (shadow_size)
        for (int r = 0; r < 3; ++r)
          lit_at[((size_t)base + at) * 3 + r] = (float)(seen[r][0] * p[0] + seen[r][1] * p[1] + seen[r][2] * p[2] + seen[r][3]);
      float* attribute = &attributes[((size_t)base + at) * 3];
      if (edge_points) {
        attribute[0] = attribute[1] = attribute[2] = 0;
      } else {
        const double n[3] = {load<float>(mesh.normals + (size_t)at * 12), load<float>(mesh.normals + (size_t)at * 12 + 4),
                             load<float>(mesh.normals + (size_t)at * 12 + 8)};
        attribute[0] = (float)(co[0] * n[0] + co[3] * n[1] + co[6] * n[2]);
        attribute[1] = (float)(co[1] * n[0] + co[4] * n[1] + co[7] * n[2]);
        attribute[2] = (float)(co[2] * n[0] + co[5] * n[1] + co[8] * n[2]);
      }
    }
    placed[key] = base;
    return base;
  }

  // --- clipping what cannot be drawn as it is ---

  struct Corner {
    double v[3];  // view coordinates
    float attribute[3];
    double cut;
    float alpha = 1;
    float seen[3] = {0, 0, 0};
    float uv[2] = {0, 0};
  };
  // The view's planes as functions of view coordinates, each kept where it is not negative: the near plane, and
  // the four sides a guard band beyond the picture.
  double plane_value(int plane, const double v[3]) const {
    double reach_x = (width / 2.0 + GUARD * 0.5), reach_y = (height / 2.0 + GUARD * 0.5);
    double depth = perspective ? v[2] : 1.0, scale = perspective ? focal : 1.0 / pixel;
    switch (plane) {
      case 0: return perspective ? v[2] - near : 1.0;
      case 1: return reach_x * depth - scale * v[0];
      case 2: return reach_x * depth + scale * v[0];
      case 3: return reach_y * depth - scale * v[1];
      default: return reach_y * depth + scale * v[1];
    }
  }
  int clip_polygon(Corner* polygon, int count) const {
    Corner next[12];
    for (int plane = 0; plane < 5 && count; ++plane) {
      int made = 0;
      for (int at = 0; at < count; ++at) {
        const Corner& a = polygon[at];
        const Corner& b = polygon[(at + 1) % count];
        double da = plane_value(plane, a.v), db = plane_value(plane, b.v);
        if (da >= 0) next[made++] = a;
        if ((da >= 0) != (db >= 0)) {
          double share = da / (da - db);
          Corner c;
          for (int k = 0; k < 3; ++k) {
            c.v[k] = a.v[k] + (b.v[k] - a.v[k]) * share;
            c.attribute[k] = (float)(a.attribute[k] + (b.attribute[k] - a.attribute[k]) * share);
          }
          if (plane == 0) c.v[2] = near;
          c.cut = a.cut + (b.cut - a.cut) * share;
          c.alpha = (float)(a.alpha + (b.alpha - a.alpha) * share);
          for (int k = 0; k < 3; ++k) c.seen[k] = (float)(a.seen[k] + (b.seen[k] - a.seen[k]) * share);
          for (int k = 0; k < 2; ++k) c.uv[k] = (float)(a.uv[k] + (b.uv[k] - a.uv[k]) * share);
          next[made++] = c;
        }
      }
      count = made;
      std::memcpy(polygon, next, sizeof(Corner) * count);
    }
    return count;
  }
  uint32_t add_corner(const Corner& corner) {
    Point p = {0, 0, 0, 1};
    project(corner.v, p);
    points.push_back(p);
    attributes.insert(attributes.end(), corner.attribute, corner.attribute + 3);
    cuts.push_back((float)(corner.cut * (perspective ? p.iw : 1.0f)));
    outside.push_back(0);
    fourth.push_back(corner.alpha);
    if (has_texels) texcoords.insert(texcoords.end(), corner.uv, corner.uv + 2);
    if (shadow_size) lit_at.insert(lit_at.end(), corner.seen, corner.seen + 3);
    return (uint32_t)(points.size() - 1);
  }

  template <typename World>
  void add_triangle(uint32_t item, uint32_t a, uint32_t b, uint32_t c, World&& world) {
    if (!(outside[a] | outside[b] | outside[c])) {
      triangles.push_back({{a, b, c}, item});
      return;
    }
    Corner polygon[12];
    const uint32_t given[3] = {a, b, c};
    for (int k = 0; k < 3; ++k) {
      double w[3];
      world(k, w);
      view_of(w, polygon[k].v);
      std::memcpy(polygon[k].attribute, &attributes[(size_t)given[k] * 3], 3 * sizeof(float));
      polygon[k].cut = has_clip ? cut_of(w) : 0;
      polygon[k].alpha = fourth[given[k]];
      if (has_texels) std::memcpy(polygon[k].uv, &texcoords[(size_t)given[k] * 2], 2 * sizeof(float));
      if (shadow_size) shadow_of(w, polygon[k].seen);
    }
    int count = clip_polygon(polygon, 3);
    if (count < 3) return;
    uint32_t first = add_corner(polygon[0]), previous = add_corner(polygon[1]);
    for (int k = 2; k < count; ++k) {
      uint32_t next = add_corner(polygon[k]);
      triangles.push_back({{first, previous, next}, item});
      previous = next;
    }
  }

  void place_all() {
    size_t most = 0;
    for (const Pending& wait : pending) {
      const Item& item = items[wait.item];
      if (item.kind != TRIANGLES && item.mesh >= 0) most += item.kind == EDGES ? meshes[item.mesh].npoints : meshes[item.mesh].nodes;
    }
    points.reserve(most), attributes.reserve(most * 3), cuts.reserve(most), outside.reserve(most);
    for (const Pending& wait : pending) {
      Item& item = items[wait.item];
      item.first = (uint32_t)(item.kind == EDGES ? segments.size() / 2 : triangles.size());
      if (shadow_pass && !(item.kind == FACES && !item.blend && item.layer == 0)) continue;
      if (item.kind == FACES || item.kind == CAP) {
        const Mesh& mesh = meshes[item.mesh];
        uint32_t base = place(item.mesh, item.matrix, false, item.kind == FACES ? item.texels : -1);
        auto run = [&](uint32_t first, uint32_t count) {
          if ((uint64_t)first + count > mesh.nindices) throw std::invalid_argument("a face's range leaves its mesh");
          for (uint32_t at = first; at + 3 <= first + count; at += 3) {
            uint32_t local[3];
            for (int k = 0; k < 3; ++k) {
              local[k] = load<uint32_t>(mesh.indices + (size_t)(at + k) * 4);
              if (local[k] >= mesh.nodes) throw std::invalid_argument("a triangle names a node its mesh has not");
            }
            add_triangle((uint32_t)wait.item, base + local[0], base + local[1], base + local[2],
                         [&](int k, double w[3]) {
                           double p[3] = {load<float>(mesh.positions + (size_t)local[k] * 12),
                                          load<float>(mesh.positions + (size_t)local[k] * 12 + 4),
                                          load<float>(mesh.positions + (size_t)local[k] * 12 + 8)};
                           transform(item.matrix, p, w);
                         });
          }
        };
        if (wait.ranges && wait.ranges->kind == Value::LIST) {
          for (const Value& range : wait.ranges->items) {
            double pair[2];
            numbers(&range, pair, 2, "range");
            run((uint32_t)pair[0], (uint32_t)pair[1]);
          }
        } else {
          run(0, mesh.nindices);
        }
        item.count = (uint32_t)triangles.size() - item.first;
      } else if (item.kind == EDGES && wait.source) {
        // Polylines of the scene's own: their points end to end, and each one's count.
        Span positions = payload(wait.source->get("positions"), "positions");
        Span counts = payload(wait.source->get("counts"), "counts");
        const uint32_t total = (uint32_t)(positions.size / 12);
        const uint32_t base = (uint32_t)points.size();
        const float none[3] = {0, 0, 0};
        for (uint32_t at = 0; at < total; ++at) {
          double p[3] = {load<float>(positions.data + (size_t)at * 12), load<float>(positions.data + (size_t)at * 12 + 4),
                         load<float>(positions.data + (size_t)at * 12 + 8)}, w[3];
          transform(item.matrix, p, w);
          add_point(w, none);
        }
        uint32_t first = 0;
        for (size_t at = 0; at + 4 <= counts.size; at += 4) {
          const uint32_t count = load<uint32_t>(counts.data + at);
          if ((uint64_t)first + count > total) throw std::invalid_argument("a line leaves the scene's points");
          for (uint32_t k = first; k + 1 < first + count; ++k) add_segment(item, positions.data, base, k);
          first += count;
        }
        item.count = (uint32_t)(segments.size() / 2) - item.first;
      } else if (item.kind == EDGES) {
        const Mesh& mesh = meshes[item.mesh];
        uint32_t base = place(item.mesh, item.matrix, true);
        for (uint32_t edge = 0; edge < mesh.nedges; ++edge) {
          uint32_t first = load<uint32_t>(mesh.edges + (size_t)edge * 16 + 4);
          uint32_t count = load<uint32_t>(mesh.edges + (size_t)edge * 16 + 8);
          uint32_t kind = load<uint32_t>(mesh.edges + (size_t)edge * 16 + 12);
          if (count < 2 || !(wait.classes >> (kind & 31u) & 1u)) continue;
          if ((uint64_t)first + count > mesh.npoints) throw std::invalid_argument("an edge leaves its mesh");
          for (uint32_t at = first; at + 1 < first + count; ++at) add_segment(item, mesh.edge_points, base, at);
        }
        item.count = (uint32_t)(segments.size() / 2) - item.first;
      } else {
        const Value& source = *wait.source;
        Span positions = payload(source.get("positions"), "positions");
        Span indices = payload(source.get("indices"), "indices");
        Span texels;
        if (const Value* named = source.get("texels"))
          if (named->is_number()) texels = payload(named, "texels");
        uint32_t count = (uint32_t)(positions.size / 12);
        if (texels.data && texels.size / 8 < count) throw std::invalid_argument("the scene's texels are too few");
        Span colors;
        if (item.colored) colors = payload(source.get("colors"), "colors");
        if (colors.data && (texels.data || colors.size / 4 < count))
          throw std::invalid_argument("the scene's vertex colours are too few, or beside texels");
        uint32_t base = (uint32_t)points.size();
        auto world_of = [&](uint32_t at, double w[3]) {
          double p[3] = {load<float>(positions.data + (size_t)at * 12), load<float>(positions.data + (size_t)at * 12 + 4),
                         load<float>(positions.data + (size_t)at * 12 + 8)};
          transform(item.matrix, p, w);
        };
        for (uint32_t at = 0; at < count; ++at) {
          double w[3];
          world_of(at, w);
          float attribute[3] = {0, 0, 0}, alpha = 1;
          if (texels.data)
            attribute[0] = load<float>(texels.data + (size_t)at * 8), attribute[1] = load<float>(texels.data + (size_t)at * 8 + 4);
          if (colors.data) {  // a vertex's colour as OpenGL takes its bytes: each over 255, no curve
            for (int c = 0; c < 3; ++c) attribute[c] = colors.data[(size_t)at * 4 + c] * (1.0f / 255.0f);
            alpha = colors.data[(size_t)at * 4 + 3] * (1.0f / 255.0f);
          }
          add_point(w, attribute, alpha);
        }
        for (size_t at = 0; at + 12 <= indices.size; at += 12) {
          uint32_t local[3];
          for (int k = 0; k < 3; ++k) {
            local[k] = load<uint32_t>(indices.data + at + k * 4);
            if (local[k] >= count) throw std::invalid_argument("a triangle names a point the scene has not");
          }
          add_triangle((uint32_t)wait.item, base + local[0], base + local[1], base + local[2],
                       [&](int k, double w[3]) { world_of(local[k], w); });
        }
        item.count = (uint32_t)triangles.size() - item.first;
      }
    }
  }

  // The segment from point `at` of `count` float triples at `from` to the next, placed at `base`.
  void add_segment(const Item& item, const uint8_t* from, uint32_t base, uint32_t at) {
    uint32_t a = base + at, b = a + 1;
    if (!(outside[a] | outside[b])) {
      segments.push_back(a), segments.push_back(b);
      return;
    }
    Corner ends[2];
    for (int k = 0; k < 2; ++k) {
      double p[3] = {load<float>(from + (size_t)(at + k) * 12), load<float>(from + (size_t)(at + k) * 12 + 4),
                     load<float>(from + (size_t)(at + k) * 12 + 8)}, w[3];
      transform(item.matrix, p, w);
      view_of(w, ends[k].v);
      ends[k].attribute[0] = ends[k].attribute[1] = ends[k].attribute[2] = 0;
      ends[k].cut = has_clip ? cut_of(w) : 0;
    }
    for (int plane = 0; plane < 5; ++plane) {
      double da = plane_value(plane, ends[0].v), db = plane_value(plane, ends[1].v);
      if (da < 0 && db < 0) return;
      if (da >= 0 && db >= 0) continue;
      double share = da / (da - db);
      Corner c;
      for (int k = 0; k < 3; ++k) c.v[k] = ends[0].v[k] + (ends[1].v[k] - ends[0].v[k]) * share, c.attribute[k] = 0;
      if (plane == 0) c.v[2] = near;
      c.cut = ends[0].cut + (ends[1].cut - ends[0].cut) * share;
      ends[da < 0 ? 0 : 1] = c;
    }
    segments.push_back(add_corner(ends[0]));
    segments.push_back(add_corner(ends[1]));
  }

  // --- the rasterizer ---

  // A coordinate of the picture in 1/256 of a pixel, the nearest.
  static inline int64_t snap(float v) { return (int64_t)((double)v * 256.0 + 2147483648.5) - 2147483648LL; }
  // A triangle's setup; false where it covers nothing. `factor` and `units` are glPolygonOffset's.
  bool setup(const Point& p0, const Point& p1, const Point& p2, float factor, float units, Setup& s) const {
    const Point* corners[3] = {&p0, &p1, &p2};
    return setup(corners, 3, factor, units, s);
  }
  // The same of a convex figure of three or four corners in order (a line's rectangle is four).
  bool setup(const Point* const* corners, int count, float factor, float units, Setup& s) const {
    int64_t x[4], y[4];
    float z[4];
    int64_t low_x = INT64_MAX, high_x = INT64_MIN, low_y = INT64_MAX, high_y = INT64_MIN;
    for (int k = 0; k < count; ++k) {
      x[k] = snap(corners[k]->x), y[k] = snap(corners[k]->y), z[k] = corners[k]->z;
      low_x = std::min(low_x, x[k]), high_x = std::max(high_x, x[k]);
      low_y = std::min(low_y, y[k]), high_y = std::max(high_y, y[k]);
    }
    s.x0 = (int)std::max<int64_t>(0, low_x >> 8), s.x1 = (int)std::min<int64_t>(width - 1, high_x >> 8);
    s.y0 = (int)std::max<int64_t>(0, low_y >> 8), s.y1 = (int)std::min<int64_t>(height - 1, high_y >> 8);
    if (s.x0 > s.x1 || s.y0 > s.y1) return false;
    const int64_t area = (x[1] - x[0]) * (y[2] - y[0]) - (x[2] - x[0]) * (y[1] - y[0]);
    if (area == 0) return false;
    const int64_t turn = area < 0 ? -1 : 1;  // the edges' functions are positive inside whichever way it winds
    for (int e = 0; e < count; ++e) {
      const int from = e, to = e == count - 1 ? 0 : e + 1;
      const int64_t dx = (x[to] - x[from]) * turn, dy = (y[to] - y[from]) * turn;
      const int64_t a = -dy, b = dx;
      s.a[e] = a, s.b[e] = b;
      // A left edge or OpenGL's top holds its own points; another does not.
      s.c[e] = dy * x[from] - dx * y[from] - ((dy < 0 || (dy == 0 && dx < 0)) ? 0 : 1);
      // The least and the most the function gains from a pixel's corner to a sample of it (bounds, over the
      // samples' box): what tells a pixel wholly outside or wholly inside without asking each sample.
      s.off_low[e] = a * (a > 0 ? sx_low : sx_high) + b * (b > 0 ? sy_low : sy_high);
      s.off_high[e] = a * (a > 0 ? sx_high : sx_low) + b * (b > 0 ? sy_high : sy_low);
      if (samples == 4) {
        s.off[e][0] = a * sx[0] + b * sy[0], s.off[e][1] = a * sx[1] + b * sy[1];
        s.off[e][2] = a * sx[2] + b * sy[2], s.off[e][3] = a * sx[3] + b * sy[3];
      } else {
        for (int k = 0; k < samples; ++k) s.off[e][k] = a * sx[k] + b * sy[k];
      }
    }
    if (count == 3) {
      s.a[3] = s.b[3] = s.c[3] = s.off_low[3] = s.off_high[3] = 0;
      for (int k = 0; k < samples; ++k) s.off[3][k] = 0;
    }
    // The depth's plane over the picture, in pixels.
    const double scale = 1.0 / 256.0;
    const double ax = (x[1] - x[0]) * scale, ay = (y[1] - y[0]) * scale, bx = (x[2] - x[0]) * scale, by = (y[2] - y[0]) * scale;
    const double inverse = 1.0 / (ax * by - bx * ay);
    const double zx = ((z[1] - z[0]) * by - (z[2] - z[0]) * ay) * inverse;
    const double zy = ((z[2] - z[0]) * ax - (z[1] - z[0]) * bx) * inverse;
    double z0 = z[0] - zx * (x[0] * scale) - zy * (y[0] * scale);
    if (factor != 0 || units != 0)
      z0 += factor * std::max(std::fabs(zx), std::fabs(zy)) + units * DEPTH_UNIT;
    s.zx = (float)zx, s.zy = (float)zy, s.z0 = (float)z0;
    if (samples == 4) {
      s.zoff[0] = (float)(zx * fsx[0] + zy * fsy[0]), s.zoff[1] = (float)(zx * fsx[1] + zy * fsy[1]);
      s.zoff[2] = (float)(zx * fsx[2] + zy * fsy[2]), s.zoff[3] = (float)(zx * fsx[3] + zy * fsy[3]);
    } else {
      for (int k = 0; k < samples; ++k) s.zoff[k] = (float)(zx * fsx[k] + zy * fsy[k]);
    }
    s.cut = false;
    return true;
  }
  // The clip plane's side at each pixel of a triangle the plane crosses; false where the plane takes it whole.
  bool setup_cut(const Point& p0, const Point& p1, const Point& p2, float c0, float c1, float c2, Setup& s) const {
    if (c0 < 0 && c1 < 0 && c2 < 0) return false;
    if (c0 >= 0 && c1 >= 0 && c2 >= 0) return true;
    double ax = p1.x - p0.x, ay = p1.y - p0.y, bx = p2.x - p0.x, by = p2.y - p0.y;
    double det = ax * by - bx * ay;
    if (det == 0) return true;
    double gx = ((c1 - c0) * by - (c2 - c0) * ay) / det, gy = ((c2 - c0) * ax - (c1 - c0) * bx) / det;
    s.cut = true;
    s.cx = (float)gx, s.cy = (float)gy;
    s.c0 = (float)(c0 - gx * p0.x - gy * p0.y + (gx + gy) * 0.5);  // at a pixel's centre
    return true;
  }

  // Each pixel the triangle touches: `sink(pixel index, mask of the samples covered, the depth at the pixel's
  // corner)`.
  template <typename Sink>
  inline void raster(const Setup& s, Sink&& sink) const {
    const int full = (1 << samples) - 1;
    const int64_t step[4] = {s.a[0] * 256, s.a[1] * 256, s.a[2] * 256, s.a[3] * 256};
    const int64_t down[4] = {s.b[0] * 256, s.b[1] * 256, s.b[2] * 256, s.b[3] * 256};
    int64_t row[4];
    for (int e = 0; e < 4; ++e) row[e] = s.a[e] * ((int64_t)s.x0 * 256) + s.b[e] * ((int64_t)s.y0 * 256) + s.c[e];
    for (int py = s.y0; py <= s.y1; ++py, row[0] += down[0], row[1] += down[1], row[2] += down[2], row[3] += down[3]) {
      // The row's span: where each edge function can be non-negative at some sample.
      int from = s.x0, to = s.x1;
      if (to - from > 6) {
        for (int e = 0; e < 4; ++e) {
          int64_t most = row[e] + s.off_high[e];
          if (step[e] > 0) {
            if (most < 0) from = (int)std::min<int64_t>(s.x1 + 1, std::max<int64_t>(from, s.x0 + (-most) / step[e]));
          } else if (step[e] < 0) {
            if (most < 0) {
              to = -1;
              break;
            }
            to = (int)std::min<int64_t>(to, s.x0 + most / (-step[e]));
          } else if (most < 0) {
            to = -1;
            break;
          }
        }
        if (to < from) continue;
      }
      const int64_t along = from - s.x0;
      int64_t e0 = row[0] + step[0] * along, e1 = row[1] + step[1] * along, e2 = row[2] + step[2] * along,
              e3 = row[3] + step[3] * along;
      const float zrow = s.z0 + s.zy * (float)py;
      const float crow = s.cut ? s.c0 + s.cy * (float)py : 0.0f;
      size_t pixel = (size_t)py * width + from;
      for (int px = from; px <= to; ++px, ++pixel, e0 += step[0], e1 += step[1], e2 += step[2], e3 += step[3]) {
        if (((e0 + s.off_high[0]) | (e1 + s.off_high[1]) | (e2 + s.off_high[2]) | (e3 + s.off_high[3])) < 0) continue;
        int mask;
        if (((e0 + s.off_low[0]) | (e1 + s.off_low[1]) | (e2 + s.off_low[2]) | (e3 + s.off_low[3])) >= 0) {
          mask = full;
        } else {
#define VC_INSIDE(k) \
  (int)((uint64_t) ~((e0 + s.off[0][k]) | (e1 + s.off[1][k]) | (e2 + s.off[2][k]) | (e3 + s.off[3][k])) >> 63)
          if (samples == 4) {
            mask = VC_INSIDE(0) | VC_INSIDE(1) << 1 | VC_INSIDE(2) << 2 | VC_INSIDE(3) << 3;
          } else {
            mask = 0;
            for (int k = 0; k < samples; ++k) mask |= VC_INSIDE(k) << k;
          }
#undef VC_INSIDE
          if (!mask) continue;
        }
        if (s.cut && crow + s.cx * (float)px < 0) continue;
        sink(pixel, px, py, mask, zrow + s.zx * (float)px, s.zoff);
      }
    }
  }

  template <typename Sink>
  void raster_triangle(const Triangle& t, float factor, float units, bool cut, Sink&& sink) const {
    Setup s;
    const Point &a = points[t.v[0]], &b = points[t.v[1]], &c = points[t.v[2]];
    if (!setup(a, b, c, factor, units, s)) return;
    if (cut && !setup_cut(a, b, c, cuts[t.v[0]], cuts[t.v[1]], cuts[t.v[2]], s)) return;
    raster(s, sink);
  }

  // A segment as OpenGL draws a multisampled line: the rectangle `line` pixels wide about it.
  template <typename Sink>
  void raster_segment(uint32_t ia, uint32_t ib, float line, bool cut, Sink&& sink) const {
    const Point &a = points[ia], &b = points[ib];
    float dx = b.x - a.x, dy = b.y - a.y;
    float length = std::sqrt(dx * dx + dy * dy);
    if (!(length > 0)) return;
    // Its ends and its half-width each to 1/256 of a pixel before they are put together, as the rasterizers do.
    const float scale = 1.0f / 256.0f;
    const float nx = snap(-dy / length * (line * 0.5f)) * scale, ny = snap(dx / length * (line * 0.5f)) * scale;
    const float ax = snap(a.x) * scale, ay = snap(a.y) * scale, bx = snap(b.x) * scale, by = snap(b.y) * scale;
    Point corner[4] = {{ax + nx, ay + ny, a.z, a.iw}, {ax - nx, ay - ny, a.z, a.iw},
                       {bx - nx, by - ny, b.z, b.iw}, {bx + nx, by + ny, b.z, b.iw}};
    const float ca = cuts[ia], cb = cuts[ib];
    const Point* corners[4] = {&corner[0], &corner[1], &corner[2], &corner[3]};
    Setup s;
    if (setup(corners, 4, 0, 0, s) && (!cut || setup_cut(corner[0], corner[1], corner[2], ca, ca, cb, s))) raster(s, sink);
  }

  // --- lighting ---

  // The direction from a point of the picture's surface to the eye.
  inline void view_at(float x, float y, float v[3]) const {
    double px = (x - width / 2.0) / focal, py = -(y - height / 2.0) / focal;
    double d[3] = {ahead[0] + right[0] * px + up[0] * py, ahead[1] + right[1] * px + up[1] * py,
                   ahead[2] + right[2] * px + up[2] * py};
    double m = -1.0 / std::sqrt(d[0] * d[0] + d[1] * d[1] + d[2] * d[2]);
    v[0] = (float)(d[0] * m), v[1] = (float)(d[1] * m), v[2] = (float)(d[2] * m);
  }

  // How much of the shadow's light reaches a point (LightShadow.glsl): sixteen readings of the map about where
  // the light sees it, each in shadow where the point is deeper than the map by more than the bias.
  inline float shadowed(float x, float y, float z, const float n[3]) const {
    static const float disk[16][2] = {
        {-0.94201624f, -0.39906216f}, {0.94558609f, -0.76890725f}, {-0.09418410f, -0.92938870f}, {0.34495938f, 0.29387760f},
        {-0.91588581f, 0.45771432f},  {-0.81544232f, -0.87912464f}, {-0.38277543f, 0.27676845f}, {0.97484398f, 0.75648379f},
        {0.44323325f, -0.97511554f},  {0.53742981f, -0.47373420f},  {-0.26496911f, -0.41893023f}, {0.79197514f, 0.19090188f},
        {-0.24188840f, 0.99706507f},  {-0.81409955f, 0.91437590f},  {0.19984126f, 0.78641367f},  {0.14383161f, -0.14100790f}};
    const float size = (float)shadow_size;
    if (x < 0 || x > size || y < 0 || y > size || z > 1) return 1;
    const Light& light = lights[shadow_light];
    const float toward = n[0] * light.to[0] + n[1] * light.to[1] + n[2] * light.to[2];
    const float bias = std::max(light.shadow_bias * (1.0f - toward), light.shadow_bias * 0.1f);
    int dark = 0;
    for (int k = 0; k < 16; ++k) {
      // The map's rows run down where OpenGL's run up: a step up the texture is a step up the picture.
      int i = (int)std::floor(x + disk[k][0]), j = (int)std::floor(y - disk[k][1]);
      i = i < 0 ? 0 : (i >= shadow_size ? shadow_size - 1 : i), j = j < 0 ? 0 : (j >= shadow_size ? shadow_size - 1 : j);
      if (z - bias > shadow_map[(size_t)j * shadow_size + i]) ++dark;
    }
    return 1.0f - dark * (1.0f / 16.0f);
  }

  // OCCT's PBR program (Graphic3d_ShaderManager's computeLighting, PBRIllumination.glsl): the colour, linear, and
  // the alpha a see-through face is blended by.
  // A face seen from behind (`back`) is lit by its normal turned over, as the program's lights turn it; the
  // environment's light is read by the normal as it is, as the program reads it.
  inline void pbr(const Item& m, const float n[3], bool back, const float v[3], float shadow, float out[4]) const {
    pbr(m, m.color, m.alpha, m.f0, n, back, v, shadow, out);
  }
  // The same of a base colour, alpha and F0 of the face's own at the pixel (a texture's).
  inline void pbr(const Item& m, const float base[3], float alpha, const float f0[3], const float n[3], bool back,
                  const float v[3], float shadow, float out[4]) const {
    const float nv = n[0] * v[0] + n[1] * v[1] + n[2] * v[2];
    const float side = back ? -1.0f : 1.0f;
    const float cos_v = nv * side > 0 ? nv * side : 0;
    float sum[3] = {0, 0, 0};
    for (const Light& light : lights) {
      const float lit_share = &light - lights.data() == shadow_light ? shadow : 1.0f;
      const float* l = light.to;
      float nl = (n[0] * l[0] + n[1] * l[1] + n[2] * l[2]) * side;
      if (!(nl > 0)) continue;
      float h[3] = {v[0] + l[0], v[1] + l[1], v[2] + l[2]};
      float hm = 1.0f / std::sqrt(h[0] * h[0] + h[1] * h[1] + h[2] * h[2]);
      h[0] *= hm, h[1] *= hm, h[2] *= hm;
      float vh = v[0] * h[0] + v[1] * h[1] + v[2] * h[2];
      if (vh < 0) vh = 0;
      float nh = (n[0] * h[0] + n[1] * h[1] + n[2] * h[2]) * side;
      if (nh < 0) nh = 0;
      float fresnel = 1.0f - vh;
      fresnel *= fresnel;
      fresnel *= fresnel * fresnel * fresnel * fresnel;
      float k = m.roughness + 1.0f;
      k *= 0.125f * k;
      float g = 1.0f / ((cos_v * (1.0f - k) + k) * (nl * (1.0f - k) + k));
      float dg = distribution(nh, m.roughness) * g * 0.25f;
      for (int c = 0; c < 3; ++c) {
        float f = f0[c] + (1.0f - f0[c]) * fresnel;
        float diffuse = (1.0f - f) * (1.0f - m.metallic) * INV_PI * base[c] * alpha;
        sum[c] += (diffuse + dg * f) * light.intensity * nl * lit_share;
      }
    }
    float refraction_x = 1;
    if (env) {
      const float anv = std::fabs(nv);
      float at = anv * (LUT_SIDE - 1);
      int low = std::min(LUT_SIDE - 2, (int)at);
      float share = at - low;
      float scale = m.lut[low][0] * (1 - share) + m.lut[low + 1][0] * share;
      float bias = m.lut[low][1] * (1 - share) + m.lut[low + 1][1] * share;
      const float r[3] = {2 * nv * n[0] - v[0], 2 * nv * n[1] - v[1], 2 * nv * n[2] - v[2]};
      float reflected[3], irradiance[3];
      env->specular(r, m.normalized * (SPECULAR_LEVELS - 1), reflected);
      env->diffuse(n, irradiance);
      float fresnel = 1.0f - anv;
      fresnel *= fresnel;
      fresnel *= fresnel * fresnel * fresnel * fresnel;
      for (int c = 0; c < 3; ++c) {
        float toward = std::max(1.0f - m.normalized, f0[c]);
        float refraction = (1.0f - (f0[c] + (toward - f0[c]) * fresnel)) * (1.0f - m.metallic);
        if (c == 0) refraction_x = refraction;
        float indirect = refraction * base[c] * alpha * irradiance[c] + (f0[c] * scale + bias) * reflected[c];
        sum[c] += ambient * indirect;
      }
    } else {
      float fresnel = 1.0f - std::fabs(nv);
      fresnel *= fresnel;
      fresnel *= fresnel * fresnel * fresnel * fresnel;
      float toward = std::max(1.0f - m.normalized, f0[0]);
      refraction_x = (1.0f - (f0[0] + (toward - f0[0]) * fresnel)) * (1.0f - m.metallic);
    }
    for (int c = 0; c < 3; ++c) out[c] = sum[c] + m.emission[c];
    out[3] = 1.0f + (alpha - 1.0f) * refraction_x;
  }

  // OCCT's Phong program as X-ray is given it (cad's look.py): the colour times itself under an ambient light and
  // white directional lights, a white highlight.
  inline void colour_only(const Item& m, const float n[3], const float v[3], float out[4]) const {
    float diffuse = ambient, highlight = 0;
    for (const Light& light : lights) {
      const float* l = light.to;
      float nl = n[0] * l[0] + n[1] * l[1] + n[2] * l[2];
      if (!(nl > 0)) continue;
      float h[3] = {v[0] + l[0], v[1] + l[1], v[2] + l[2]};
      float hm = 1.0f / std::sqrt(h[0] * h[0] + h[1] * h[1] + h[2] * h[2]);
      float nh = (n[0] * h[0] + n[1] * h[1] + n[2] * h[2]) * hm;
      diffuse += nl;
      if (nh > 0) highlight += std::pow(nh, shininess);
    }
    for (int c = 0; c < 3; ++c) out[c] = m.color[c] * m.color[c] * diffuse + specular * highlight;
    out[3] = m.alpha;
  }

  // A texture's colour at a coordinate: sRGB texels decoded, then bilinear, clamped at its edges; v up.
  inline void texel(const Item& m, float u, float v, float out[4]) const {
    const Tone& t = tone();
    float fx = u * m.texture_width - 0.5f, fy = (1.0f - v) * m.texture_height - 0.5f;
    int x0 = (int)std::floor(fx), y0 = (int)std::floor(fy);
    float tx = fx - x0, ty = fy - y0;
    int x1, y1;
    if (m.repeat) {  // GL_REPEAT
      const int w = m.texture_width, h = m.texture_height;
      x1 = ((x0 + 1) % w + w) % w, y1 = ((y0 + 1) % h + h) % h, x0 = (x0 % w + w) % w, y0 = (y0 % h + h) % h;
    } else {
      x1 = std::min(m.texture_width - 1, std::max(0, x0 + 1)), y1 = std::min(m.texture_height - 1, std::max(0, y0 + 1));
      x0 = std::min(m.texture_width - 1, std::max(0, x0)), y0 = std::min(m.texture_height - 1, std::max(0, y0));
    }
    const uint8_t* a = m.texture.data + ((size_t)y0 * m.texture_width + x0) * 4;
    const uint8_t* b = m.texture.data + ((size_t)y0 * m.texture_width + x1) * 4;
    const uint8_t* c = m.texture.data + ((size_t)y1 * m.texture_width + x0) * 4;
    const uint8_t* d = m.texture.data + ((size_t)y1 * m.texture_width + x1) * 4;
    for (int k = 0; k < 3; ++k)
      out[k] = (t.decode[a[k]] * (1 - tx) + t.decode[b[k]] * tx) * (1 - ty) +
               (t.decode[c[k]] * (1 - tx) + t.decode[d[k]] * tx) * ty;
    out[3] = ((a[3] * (1 - tx) + b[3] * tx) * (1 - ty) + (c[3] * (1 - tx) + d[3] * tx) * ty) * (1.0f / 255.0f);
  }

  // `texel` of four lanes.
  inline void texel4(const Item& m, f4 u, f4 v, int count, f4 out[4]) const {
    const Tone& t = tone();
    const f4 half = splat(0.5f), one = splat(1.0f);
    const f4 fx = u * splat((float)m.texture_width) - half, fy = (one - v) * splat((float)m.texture_height) - half;
    f4 low_x, low_y;
    for (int k = 0; k < 4; ++k) low_x[k] = std::floor(fx[k]), low_y[k] = std::floor(fy[k]);
    const f4 tx = fx - low_x, ty = fy - low_y;
    f4 ta[4], tb[4], tc[4], td[4];
    for (int k = 0; k < 4; ++k) {
      if (k >= count) {
        for (int c = 0; c < 4; ++c) ta[c][k] = tb[c][k] = tc[c][k] = td[c][k] = 0;
        continue;
      }
      int x0 = (int)low_x[k], y0 = (int)low_y[k];
      int x1 = std::min(m.texture_width - 1, std::max(0, x0 + 1)), y1 = std::min(m.texture_height - 1, std::max(0, y0 + 1));
      x0 = std::min(m.texture_width - 1, std::max(0, x0)), y0 = std::min(m.texture_height - 1, std::max(0, y0));
      const uint8_t* a = m.texture.data + ((size_t)y0 * m.texture_width + x0) * 4;
      const uint8_t* b = m.texture.data + ((size_t)y0 * m.texture_width + x1) * 4;
      const uint8_t* c = m.texture.data + ((size_t)y1 * m.texture_width + x0) * 4;
      const uint8_t* d = m.texture.data + ((size_t)y1 * m.texture_width + x1) * 4;
      for (int j = 0; j < 3; ++j)
        ta[j][k] = t.decode[a[j]], tb[j][k] = t.decode[b[j]], tc[j][k] = t.decode[c[j]], td[j][k] = t.decode[d[j]];
      ta[3][k] = a[3], tb[3][k] = b[3], tc[3][k] = c[3], td[3][k] = d[3];
    }
    for (int j = 0; j < 4; ++j)
      out[j] = (ta[j] * (one - tx) + tb[j] * tx) * (one - ty) + (tc[j] * (one - tx) + td[j] * tx) * ty;
    out[3] *= splat(1.0f / 255.0f);
  }

  // A triangle's colour at a pixel's centre (linear, and its alpha), its attributes read there as OpenGL reads
  // them: by the pixel's place in the triangle, through the perspective.
  // What a triangle's lighting asks once, kept while its pixels follow one another: its place in the picture as
  // the rasterizer placed it (to 1/256 of a pixel), and its corners' view directions.
  struct Kept {
    uint32_t index = ~0u;
    float x0, y0, ax, ay, bx, by, area;
    float view[3][3];
  };
  mutable Kept kept;

  inline void keep(const Triangle& t) const {
    const uint32_t index = (uint32_t)(&t - triangles.data());
    if (kept.index == index) return;
    const Point &p0 = points[t.v[0]], &p1 = points[t.v[1]], &p2 = points[t.v[2]];
    kept.index = index;
    kept.x0 = snap(p0.x) * (1.0f / 256.0f), kept.y0 = snap(p0.y) * (1.0f / 256.0f);
    kept.ax = snap(p1.x) * (1.0f / 256.0f) - kept.x0, kept.ay = snap(p1.y) * (1.0f / 256.0f) - kept.y0;
    kept.bx = snap(p2.x) * (1.0f / 256.0f) - kept.x0, kept.by = snap(p2.y) * (1.0f / 256.0f) - kept.y0;
    kept.area = kept.ax * kept.by - kept.bx * kept.ay;
    if (perspective && items[t.item].shading != UNLIT)
      view_at(p0.x, p0.y, kept.view[0]), view_at(p1.x, p1.y, kept.view[1]), view_at(p2.x, p2.y, kept.view[2]);
  }

  inline void shade(const Triangle& t, int px, int py, float out[4]) const {
    const Item& m = items[t.item];
    const Point &p0 = points[t.v[0]], &p1 = points[t.v[1]], &p2 = points[t.v[2]];
    keep(t);
    const float ax = kept.ax, ay = kept.ay, bx = kept.bx, by = kept.by, area = kept.area;
    const float qx = px + 0.5f - kept.x0, qy = py + 0.5f - kept.y0;
    float l1 = (qx * by - bx * qy) / area, l2 = (ax * qy - qx * ay) / area;
    float l0 = 1.0f - l1 - l2;
    if (perspective) {
      l0 *= p0.iw, l1 *= p1.iw, l2 *= p2.iw;
      float sum = 1.0f / (l0 + l1 + l2);
      l0 *= sum, l1 *= sum, l2 *= sum;
    }
    const float* a0 = &attributes[(size_t)t.v[0] * 3];
    const float* a1 = &attributes[(size_t)t.v[1] * 3];
    const float* a2 = &attributes[(size_t)t.v[2] * 3];
    float a[3] = {a0[0] * l0 + a1[0] * l1 + a2[0] * l2, a0[1] * l0 + a1[1] * l1 + a2[1] * l2,
                  a0[2] * l0 + a1[2] * l1 + a2[2] * l2};
    if (m.shading == UNLIT) {
      if (m.textured) {
        texel(m, a[0], a[1], out);
        for (int c = 0; c < 3; ++c) out[c] *= m.color[c];
        out[3] *= m.alpha;
      } else if (m.colored) {
        for (int c = 0; c < 3; ++c) out[c] = a[c] * m.color[c];
        out[3] = (fourth[t.v[0]] * l0 + fourth[t.v[1]] * l1 + fourth[t.v[2]] * l2) * m.alpha;
      } else {
        out[0] = m.color[0], out[1] = m.color[1], out[2] = m.color[2], out[3] = m.alpha;
      }
      return;
    }
    float scale = a[0] * a[0] + a[1] * a[1] + a[2] * a[2];
    scale = scale > 0 ? 1.0f / std::sqrt(scale) : 0.0f;
    // The face's other side is lit by its normal turned over: front is counter-clockwise, a mirrored part's clockwise.
    const bool back = (area < 0) == m.mirrored;
    if (back && m.shading != PBR) scale = -scale;
    a[0] *= scale, a[1] *= scale, a[2] *= scale;
    // The view direction is the program's: a vertex's own, read across the triangle like its normal.
    float v[3];
    if (perspective) {
      for (int c = 0; c < 3; ++c) v[c] = kept.view[0][c] * l0 + kept.view[1][c] * l1 + kept.view[2][c] * l2;
      float m = 1.0f / std::sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]);
      v[0] *= m, v[1] *= m, v[2] *= m;
    } else {
      v[0] = (float)-ahead[0], v[1] = (float)-ahead[1], v[2] = (float)-ahead[2];
    }
    if (m.shading == PBR) {
      float shadow = 1;
      if (shadow_size) {
        const float* s0 = &lit_at[(size_t)t.v[0] * 3];
        const float* s1 = &lit_at[(size_t)t.v[1] * 3];
        const float* s2 = &lit_at[(size_t)t.v[2] * 3];
        shadow = shadowed(s0[0] * l0 + s1[0] * l1 + s2[0] * l2, s0[1] * l0 + s1[1] * l1 + s2[1] * l2,
                          s0[2] * l0 + s1[2] * l1 + s2[2] * l2, a);
      }
      if (m.textured) {  // the base colour times the texture's (OCCT's occTextureColor), F0 from it
        const float* t0 = &texcoords[(size_t)t.v[0] * 2];
        const float* t1 = &texcoords[(size_t)t.v[1] * 2];
        const float* t2 = &texcoords[(size_t)t.v[2] * 2];
        float tex[4], base[3], f0[3];
        texel(m, t0[0] * l0 + t1[0] * l1 + t2[0] * l2, t0[1] * l0 + t1[1] * l1 + t2[1] * l2, tex);
        float dielectric = (1.0f - m.ior) / (1.0f + m.ior);
        dielectric *= dielectric;
        for (int c = 0; c < 3; ++c) base[c] = m.color[c] * tex[c], f0[c] = dielectric + (base[c] - dielectric) * m.metallic;
        pbr(m, base, m.alpha * tex[3], f0, a, back, v, shadow, out);
      } else {
        pbr(m, a, back, v, shadow, out);
      }
    }
    else colour_only(m, a, v, out);
  }

  // Whether a triangle of `m` may be lit four pixels at a time (shade4): a PBR face under the environment.
  inline bool by_four(const Item& m) const {
    return (m.shading == PBR && !m.textured && !m.colored && env != nullptr) || (m.shading == UNLIT && m.textured);
  }

  // `shade` of the first `count` (1 to 4) of four pixels of one triangle, each lane the same arithmetic as one
  // pixel's, in the same order; what reads a table (the split-sum row, the specular map, the shadow map) is read
  // lane by lane.
  void shade4(const Triangle& t, const int px[4], const int py[4], int count, float out[4][4]) const {
    const Item& m = items[t.item];
    const Point &p0 = points[t.v[0]], &p1 = points[t.v[1]], &p2 = points[t.v[2]];
    keep(t);
    const f4 ax = splat(kept.ax), ay = splat(kept.ay), bx = splat(kept.bx), by = splat(kept.by),
             area = splat(kept.area);
    const f4 qx = (f4{(float)px[0], (float)px[1], (float)px[2], (float)px[3]} + splat(0.5f)) - splat(kept.x0);
    const f4 qy = (f4{(float)py[0], (float)py[1], (float)py[2], (float)py[3]} + splat(0.5f)) - splat(kept.y0);
    f4 l1 = (qx * by - bx * qy) / area, l2 = (ax * qy - qx * ay) / area;
    f4 l0 = (splat(1.0f) - l1) - l2;
    if (perspective) {
      l0 *= splat(p0.iw), l1 *= splat(p1.iw), l2 *= splat(p2.iw);
      const f4 sum = splat(1.0f) / ((l0 + l1) + l2);
      l0 *= sum, l1 *= sum, l2 *= sum;
    }
    const float* a0 = &attributes[(size_t)t.v[0] * 3];
    const float* a1 = &attributes[(size_t)t.v[1] * 3];
    const float* a2 = &attributes[(size_t)t.v[2] * 3];
    f4 n[3];
    for (int c = 0; c < 3; ++c) n[c] = (splat(a0[c]) * l0 + splat(a1[c]) * l1) + splat(a2[c]) * l2;
    if (m.shading == UNLIT) {  // textured (by_four)
      f4 rgba[4];
      texel4(m, n[0], n[1], count, rgba);
      for (int k = 0; k < count; ++k) {
        for (int c = 0; c < 3; ++c) out[k][c] = rgba[c][k] * m.color[c];
        out[k][3] = rgba[3][k] * m.alpha;
      }
      return;
    }
    f4 scale = (n[0] * n[0] + n[1] * n[1]) + n[2] * n[2];
    scale = pick(scale > splat(0.0f), splat(1.0f) / root(scale), splat(0.0f));
    const bool back = (kept.area < 0) == m.mirrored;
    n[0] *= scale, n[1] *= scale, n[2] *= scale;
    f4 v[3];
    if (perspective) {
      for (int c = 0; c < 3; ++c)
        v[c] = (splat(kept.view[0][c]) * l0 + splat(kept.view[1][c]) * l1) + splat(kept.view[2][c]) * l2;
      const f4 inverse = splat(1.0f) / root((v[0] * v[0] + v[1] * v[1]) + v[2] * v[2]);
      v[0] *= inverse, v[1] *= inverse, v[2] *= inverse;
    } else {
      v[0] = splat((float)-ahead[0]), v[1] = splat((float)-ahead[1]), v[2] = splat((float)-ahead[2]);
    }
    f4 shadow = splat(1.0f);
    if (shadow_size) {
      const float* s0 = &lit_at[(size_t)t.v[0] * 3];
      const float* s1 = &lit_at[(size_t)t.v[1] * 3];
      const float* s2 = &lit_at[(size_t)t.v[2] * 3];
      f4 at[3];
      for (int c = 0; c < 3; ++c) at[c] = (splat(s0[c]) * l0 + splat(s1[c]) * l1) + splat(s2[c]) * l2;
      for (int k = 0; k < count; ++k) {
        const float normal[3] = {n[0][k], n[1][k], n[2][k]};
        shadow[k] = shadowed(at[0][k], at[1][k], at[2][k], normal);
      }
    }
    pbr4(m, n, back, v, shadow, count, out);
  }

  // `pbr` of four lanes.
  void pbr4(const Item& m, const f4 n[3], bool back, const f4 v[3], f4 shadow, int count, float out[4][4]) const {
    const f4 zero = splat(0.0f), one = splat(1.0f);
    const f4 nv = (n[0] * v[0] + n[1] * v[1]) + n[2] * v[2];
    const f4 side = splat(back ? -1.0f : 1.0f);
    const f4 cos_v = pick(nv * side > zero, nv * side, zero);
    f4 sum[3] = {zero, zero, zero};
    for (const Light& light : lights) {
      const f4 lit_share = &light - lights.data() == shadow_light ? shadow : one;
      const float* l = light.to;
      const f4 nl = ((n[0] * splat(l[0]) + n[1] * splat(l[1])) + n[2] * splat(l[2])) * side;
      const i4 lit = nl > zero;
      if (!(lit[0] | lit[1] | lit[2] | lit[3])) continue;
      f4 h[3] = {v[0] + splat(l[0]), v[1] + splat(l[1]), v[2] + splat(l[2])};
      const f4 hm = one / root((h[0] * h[0] + h[1] * h[1]) + h[2] * h[2]);
      h[0] *= hm, h[1] *= hm, h[2] *= hm;
      f4 vh = (v[0] * h[0] + v[1] * h[1]) + v[2] * h[2];
      vh = pick(vh < zero, zero, vh);
      f4 nh = ((n[0] * h[0] + n[1] * h[1]) + n[2] * h[2]) * side;
      nh = pick(nh < zero, zero, nh);
      f4 fresnel = one - vh;
      fresnel *= fresnel;
      fresnel *= ((fresnel * fresnel) * fresnel) * fresnel;
      float k = m.roughness + 1.0f;
      k *= 0.125f * k;
      const f4 g = one / ((cos_v * splat(1.0f - k) + splat(k)) * (nl * splat(1.0f - k) + splat(k)));
      const float rough = m.roughness * m.roughness;
      f4 d = splat(rough) / ((nh * nh) * splat(rough * rough - 1.0f) + one);
      d = (splat(INV_PI) * d) * d;
      const f4 dg = (d * g) * splat(0.25f);
      for (int c = 0; c < 3; ++c) {
        const f4 f = splat(m.f0[c]) + splat(1.0f - m.f0[c]) * fresnel;
        const f4 diffuse = (((one - f) * splat(1.0f - m.metallic)) * splat(INV_PI)) * splat(m.color[c]) * splat(m.alpha);
        sum[c] += pick(lit, (((diffuse + dg * f) * splat(light.intensity)) * nl) * lit_share, zero);
      }
    }
    // The environment's light (env is there: by_four).
    const f4 anv = magnitude(nv);
    const f4 at = anv * splat((float)(LUT_SIDE - 1));
    f4 scale, bias;
    for (int k = 0; k < count; ++k) {
      int low = std::min(LUT_SIDE - 2, (int)at[k]);
      float share = at[k] - low;
      scale[k] = m.lut[low][0] * (1 - share) + m.lut[low + 1][0] * share;
      bias[k] = m.lut[low][1] * (1 - share) + m.lut[low + 1][1] * share;
    }
    f4 r[3];
    for (int c = 0; c < 3; ++c) r[c] = (splat(2.0f) * nv) * n[c] - v[c];
    f4 reflected[3];
    env->specular4(r, m.normalized * (SPECULAR_LEVELS - 1), count, reflected);
    // The irradiance (Environment::diffuse), along the cube map's direction (n.y, n.z, n.x).
    const f4 x = n[1], y = n[2], z = n[0];
    const f4 f[9] = {one, x, y, z, x * z, y * z, x * y, (splat(3.0f) * z) * z - one, x * x - y * y};
    f4 irradiance[3];
    for (int c = 0; c < 3; ++c) {
      f4 total = zero;
      for (int k = 0; k < 9; ++k) total += splat(env->sh[k][c]) * f[k];
      irradiance[c] = total;
    }
    f4 fresnel = one - anv;
    fresnel *= fresnel;
    fresnel *= ((fresnel * fresnel) * fresnel) * fresnel;
    f4 refraction_x = one;
    for (int c = 0; c < 3; ++c) {
      const float toward = std::max(1.0f - m.normalized, m.f0[c]);
      const f4 refraction = (one - (splat(m.f0[c]) + splat(toward - m.f0[c]) * fresnel)) * splat(1.0f - m.metallic);
      if (c == 0) refraction_x = refraction;
      const f4 indirect = ((refraction * splat(m.color[c])) * splat(m.alpha)) * irradiance[c] +
                          (splat(m.f0[c]) * scale + bias) * reflected[c];
      sum[c] += splat(ambient) * indirect;
    }
    const f4 alpha = one + splat(m.alpha - 1.0f) * refraction_x;
    for (int k = 0; k < count; ++k) {
      for (int c = 0; c < 3; ++c) out[k][c] = sum[c][k] + m.emission[c];
      out[k][3] = alpha[k];
    }
  }

  inline uint32_t stored(const float c[4]) const { return tone().pack(c[0], c[1], c[2]); }

  // --- the passes ---

  // The backdrop's picture stretched over the frame, as OpenGL draws a background image: its texels' light read
  // bilinearly at each pixel's centre, clamped at its edges.
  void stretch_backdrop() {
    const Tone& t = tone();
    behind.resize((size_t)width * height);
    for (int py = 0; py < height; ++py)
      for (int px = 0; px < width; ++px) {
        float fx = (px + 0.5f) / width * backdrop_width - 0.5f, fy = (py + 0.5f) / height * backdrop_height - 0.5f;
        int x0 = (int)std::floor(fx), y0 = (int)std::floor(fy);
        float tx = fx - x0, ty = fy - y0;
        int x1 = std::min(backdrop_width - 1, std::max(0, x0 + 1)), y1 = std::min(backdrop_height - 1, std::max(0, y0 + 1));
        x0 = std::min(backdrop_width - 1, std::max(0, x0)), y0 = std::min(backdrop_height - 1, std::max(0, y0));
        float rgb[3];
        for (int c = 0; c < 3; ++c) {
          float a = t.decode[backdrop.data[((size_t)y0 * backdrop_width + x0) * 3 + c]];
          float b = t.decode[backdrop.data[((size_t)y0 * backdrop_width + x1) * 3 + c]];
          float d = t.decode[backdrop.data[((size_t)y1 * backdrop_width + x0) * 3 + c]];
          float e = t.decode[backdrop.data[((size_t)y1 * backdrop_width + x1) * 3 + c]];
          rgb[c] = (a * (1 - tx) + b * tx) * (1 - ty) + (d * (1 - tx) + e * tx) * ty;
        }
        behind[(size_t)py * width + px] = t.pack(rgb[0], rgb[1], rgb[2]);
      }
  }

  // The shadow's light as a camera, as OpenGl_ShadowMap fits one to what is drawn: looking the way the light
  // travels, Y up (X where it travels along Y), a square a tenth wider than the box, its depth the box's.
  void light_camera(const Light& light) {
    perspective = false;
    double d[3] = {-light.to[0], -light.to[1], -light.to[2]}, y[3] = {0, 1, 0};
    if (std::fabs(d[0]) < 1e-12 && std::fabs(d[2]) < 1e-12) y[0] = 1, y[1] = 0;
    double side[3] = {d[1] * y[2] - d[2] * y[1], d[2] * y[0] - d[0] * y[2], d[0] * y[1] - d[1] * y[0]};
    double m = std::sqrt(side[0] * side[0] + side[1] * side[1] + side[2] * side[2]);
    for (int c = 0; c < 3; ++c) side[c] /= m, ahead[c] = d[c], right[c] = side[c];
    up[0] = side[1] * d[2] - side[2] * d[1], up[1] = side[2] * d[0] - side[0] * d[2], up[2] = side[0] * d[1] - side[1] * d[0];
    double centre[3] = {0, 0, 0}, across = 0, along_up = 0, least = 0, most = 1;
    if (bounded) {
      for (int c = 0; c < 3; ++c) centre[c] = (low[c] + high[c]) / 2;
      for (int corner = 0; corner < 8; ++corner) {
        double x = 0, yy = 0, z = 0;
        for (int c = 0; c < 3; ++c) {
          double from = (corner >> c & 1 ? high[c] : low[c]) - centre[c];
          x += from * right[c], yy += from * up[c], z += from * ahead[c];
        }
        across = std::max(across, std::fabs(x)), along_up = std::max(along_up, std::fabs(yy));
        if (!corner || z < least) least = z;
        if (!corner || z > most) most = z;
      }
    }
    double size = std::max(2 * across, 2 * along_up) * 1.1;
    if (!(size > 0)) size = 1;
    pixel = size / height;
    for (int c = 0; c < 3; ++c) eye[c] = centre[c];
    double slack = 1e-6 * (std::fabs(least) + std::fabs(most) + (most - least)) + 1e-9;
    near = least - slack, far = most + slack;
  }
  // Its view of the model's opaque faces: their depth alone, a texel a sample.
  void draw_shadow() {
    depth.assign((size_t)width * height, DEPTH_FAR);
    depth_at = depth.data();
    for (const Item& item : items) {
      if (item.kind != FACES || item.blend || item.layer != 0) continue;
      for (uint32_t at = item.first; at < item.first + item.count; ++at)
        raster_triangle(triangles[at], item.offset_factor, item.offset_units, has_clip && item.cut,
                        [&](size_t pixel, int, int, int, float z, const float* zoff) {
                          const float zs = kept_depth(z + zoff[0]);
                          if (zs <= depth_at[pixel]) depth_at[pixel] = zs;
                        });
    }
    for (float& value : depth) value *= 1.0f / DEPTH_FAR;
  }

  void draw() {
    const size_t count = (size_t)width * height * samples;
    depth.assign(count, DEPTH_FAR);
    color.assign(count, 0u);
    depth_at = depth.data(), color_at = color.data();
    depth_written = false;
    if (backdrop.data && !depth_only) stretch_backdrop();
    bool after = false;  // anything drawn once the opaque are lit: see-through surfaces, the layers above
    for (const Item& item : items)
      if (item.layer != 0 || item.blend || item.kind == TRIANGLES) after = true;
    RENDER_CLOCK(started);
    // The opaque of the model's layer, into the visibility buffer.
    for (size_t index = 0; index < items.size(); ++index) {
      const Item& item = items[index];
      if (item.layer != 0 || item.blend) continue;
      if (item.kind != TRIANGLES && item.count) depth_written = true;
      if (item.kind == FACES) {
        const bool flat = item.shading == UNLIT;
        for (uint32_t at = item.first; at < item.first + item.count; ++at) {
          const uint32_t id = flat ? item.flat : at + 1;
          raster_triangle(triangles[at], item.offset_factor, item.offset_units, has_clip && item.cut,
                          [&](size_t pixel, int, int, int mask, float z, const float* zoff) { visible(pixel, mask, z, zoff, id); });
        }
      } else if (item.kind == EDGES) {
        for (uint32_t at = item.first; at < item.first + item.count; ++at)
          raster_segment(segments[(size_t)at * 2], segments[(size_t)at * 2 + 1], item.width, has_clip && item.cut,
                         [&](size_t pixel, int, int, int mask, float z, const float* zoff) { visible(pixel, mask, z, zoff, item.flat); });
      } else if (item.kind == CAP && has_clip) {
        cap(item);
      }
    }
    RENDER_SAY("opaque", started);
    if (depth_only) return;
    RENDER_CLOCK(lighting);
    if (!after) {
      resolve_visible();
      RENDER_SAY("light", lighting);
      return;
    }
    light_visible();
    RENDER_SAY("light", lighting);
    RENDER_CLOCK(over);
    for (int layer = 0; layer < 3; ++layer) {
      bool any = false;
      for (const Item& item : items)
        if (item.layer == layer && (layer > 0 || item.blend || item.kind == TRIANGLES)) any = true;
      if (!any) continue;
      if (layer == 2 && depth_written) std::fill(depth.begin(), depth.end(), DEPTH_FAR), depth_written = false;
      for (int pass = 0; pass < 2; ++pass)  // the opaque of a layer above first, then the see-through in order
        for (const Item& item : items) {
          if (item.layer != layer || (item.blend ? pass == 0 : pass == 1)) continue;
          if (layer == 0 && !item.blend && item.kind != TRIANGLES) continue;  // drawn already
          forward(item, layer != 1 && !item.blend);
        }
    }
    RENDER_SAY("over", over);
    RENDER_CLOCK(resolving);
    resolve_colors();
    RENDER_SAY("resolve", resolving);
  }

  __attribute__((always_inline)) inline void visible(size_t pixel, int mask, float z, const float* zoff, uint32_t id) {
    float* d = depth_at + pixel * samples;
    uint32_t* c = color_at + pixel * samples;
    if (samples == 4 && mask == 15) {
      const f4 zs = kept_depth4(splat(z) + load4(zoff)), was = load4(d);
      const i4 nearer = zs <= was;
      const f4 depths = pick(nearer, zs, was);
      const i4 ids = pick(nearer, i4{(int32_t)id, (int32_t)id, (int32_t)id, (int32_t)id}, load4(c));
      std::memcpy(d, &depths, sizeof depths), std::memcpy(c, &ids, sizeof ids);
      return;
    }
    for (int k = 0; k < samples; ++k) {
      if (!(mask >> k & 1)) continue;
      float zs = kept_depth(z + zoff[k]);
      if (zs <= d[k]) d[k] = zs, c[k] = id;
    }
  }

  // An instance's cut, capped as OpenGl_CappingAlgo caps it: every face of the part inverts a stencil bit where
  // it is drawn on the kept side, no depth asked; where the bit is left set the eye looks into the part through
  // the plane, and the plane is drawn there, flat, against the depth.
  void cap(const Item& item) {
    if (parity.empty()) parity.assign((size_t)width * height, 0);
    int x0 = width, x1 = -1, y0 = height, y1 = -1;
    for (uint32_t at = item.first; at < item.first + item.count; ++at) {
      Setup s;
      const Triangle& t = triangles[at];
      const Point &a = points[t.v[0]], &b = points[t.v[1]], &c = points[t.v[2]];
      if (!setup(a, b, c, 0, 0, s) || !setup_cut(a, b, c, cuts[t.v[0]], cuts[t.v[1]], cuts[t.v[2]], s)) continue;
      x0 = std::min(x0, s.x0), x1 = std::max(x1, s.x1), y0 = std::min(y0, s.y0), y1 = std::max(y1, s.y1);
      raster(s, [&](size_t pixel, int, int, int mask, float, const float*) { parity[pixel] ^= (uint8_t)mask; });
    }
    if (x1 < x0) return;
    // The plane's depth over the picture, a plane itself: where the ray through a pixel meets it.
    const double at_eye = cut_of(eye);
    const double nr = clip[0] * right[0] + clip[1] * right[1] + clip[2] * right[2];
    const double nu = clip[0] * up[0] + clip[1] * up[1] + clip[2] * up[2];
    const double nf = clip[0] * ahead[0] + clip[1] * ahead[1] + clip[2] * ahead[2];
    double zx = 0, zy = 0, z0 = 0;
    bool placed_all = true;
    if (perspective) {
      // 1 / depth along the view = -(n . ray) / (n . eye + d), the ray forward + right x + up y.
      if (at_eye == 0) placed_all = false;
      else {
        const double scale = far / (far - near), k = scale * near / at_eye;
        zx = k * nr / focal, zy = -k * nu / focal;
        z0 = scale + k * nf - zx * (width / 2.0) - zy * (height / 2.0);
      }
    } else {
      if (std::fabs(nf) < 1e-12) placed_all = false;
      else {
        const double k = -1.0 / (nf * (far - near));
        zx = k * nr * pixel, zy = -k * nu * pixel;
        z0 = k * at_eye - near / (far - near) - zx * (width / 2.0) - zy * (height / 2.0);
      }
    }
    for (int py = y0; py <= y1; ++py)
      for (int px = x0; px <= x1; ++px) {
        size_t pixel = (size_t)py * width + px;
        int mask = parity[pixel];
        if (!mask) continue;
        parity[pixel] = 0;
        if (!placed_all) continue;
        float* d = &depth[pixel * samples];
        uint32_t* c = &color[pixel * samples];
        for (int k = 0; k < samples; ++k) {
          if (!(mask >> k & 1)) continue;
          const float exact = (float)(z0 + zx * (px + sx[k] / 256.0) + zy * (py + sy[k] / 256.0));
          const float zs = kept_depth(exact);
          if (exact >= 0 && zs < d[k]) d[k] = zs, c[k] = item.flat;  // the capping's own depth test: nearer alone
        }
      }
  }
  std::vector<uint8_t> parity;

  inline uint32_t light(uint32_t id, int px, int py) {
    if (id == 0) return behind.empty() ? background_stored : behind[(size_t)py * width + px];
    if (id & FLAT) return flats[id & ~FLAT];
    if (id == even_id) return even_color;
    const Triangle& t = triangles[id - 1];
    float c[4];
    shade(t, px, py, c);
    const uint32_t found = stored(c);
    // A flat face under an orthographic camera is one colour all over: the next pixel of it asks nothing.
    if (!perspective && !shadow_size && items[t.item].shading != UNLIT && !items[t.item].textured &&
        std::memcmp(&attributes[(size_t)t.v[0] * 3], &attributes[(size_t)t.v[1] * 3], 3 * sizeof(float)) == 0 &&
        std::memcmp(&attributes[(size_t)t.v[0] * 3], &attributes[(size_t)t.v[2] * 3], 3 * sizeof(float)) == 0)
      even_id = id, even_color = found;
    return found;
  }
  uint32_t background_stored = 0, even_id = 0, even_color = 0;

  // Whether a pixel's samples hold one value.
  inline bool uniform(const uint32_t* c) const {
    if (samples == 4) {
      uint64_t low, high;
      std::memcpy(&low, c, 8), std::memcpy(&high, c + 2, 8);
      return low == high && (uint32_t)low == (uint32_t)(low >> 32);
    }
    for (int k = 1; k < samples; ++k)
      if (c[k] != c[0]) return false;
    return true;
  }

  inline uint32_t mean(const uint32_t* c) const {
    const Tone& t = tone();
    float r = 0, g = 0, b = 0;
    for (int k = 0; k < samples; ++k) {
      r += t.decode[c[k] & 255], g += t.decode[c[k] >> 8 & 255], b += t.decode[c[k] >> 16 & 255];
    }
    float share = 1.0f / samples;
    return t.pack(r * share, g * share, b * share);
  }

  // Pixels one triangle has whole, waiting to be lit four at a time (shade4); `put` takes each one's colour.
  struct Waiting {
    uint32_t id = 0;
    int count = 0, px[4], py[4];
    size_t pixel[4];
  };
  uint32_t not_by_four = 0;  // the last triangle found not to be lit four at a time
  // Whether the pixels triangle `id` has whole are lit four at a time: not one lit once all over (`light`).
  inline bool four_of(uint32_t id) {
    if (id == 0 || (id & FLAT) || id == not_by_four || id == even_id) return false;
    const Triangle& t = triangles[id - 1];
    const Item& m = items[t.item];
    const bool even = !perspective && !shadow_size && !m.textured &&
                      std::memcmp(&attributes[(size_t)t.v[0] * 3], &attributes[(size_t)t.v[1] * 3], 3 * sizeof(float)) == 0 &&
                      std::memcmp(&attributes[(size_t)t.v[0] * 3], &attributes[(size_t)t.v[2] * 3], 3 * sizeof(float)) == 0;
    if (even || !by_four(m)) {
      not_by_four = id;
      return false;
    }
    return true;
  }
  template <typename Put>
  inline void wait(Waiting& w, uint32_t id, int px, int py, size_t pixel, Put&& put) {
    if (w.count && w.id != id) lit_four(w, put);
    w.id = id, w.px[w.count] = px, w.py[w.count] = py, w.pixel[w.count] = pixel;
    if (++w.count == 4) lit_four(w, put);
  }
  template <typename Put>
  inline void lit_four(Waiting& w, Put&& put) {
    if (!w.count) return;
    float c[4][4];
    for (int k = w.count; k < 4; ++k) w.px[k] = w.px[0], w.py[k] = w.py[0];
    shade4(triangles[w.id - 1], w.px, w.py, w.count, c);
    for (int k = 0; k < w.count; ++k) put(w.pixel[k], stored(c[k]));
    w.count = 0;
  }

  // Each sample's triangle lit, into the picture: once a pixel where one triangle has it whole.
  void resolve_visible() {
    picture.resize((size_t)width * height);
    Waiting waiting;
    auto put = [&](size_t pixel, uint32_t found) { picture[pixel] = found; };
    for (int py = 0; py < height; ++py)
      for (int px = 0; px < width; ++px) {
        size_t pixel = (size_t)py * width + px;
        const uint32_t* ids = &color[pixel * samples];
        const bool one = uniform(ids);
        if (one) {
          if ((waiting.count && ids[0] == waiting.id) || four_of(ids[0])) wait(waiting, ids[0], px, py, pixel, put);
          else picture[pixel] = light(ids[0], px, py);
          continue;
        }
        uint32_t lit_as[8];
        for (int k = 0; k < samples; ++k) {
          int same = -1;
          for (int j = 0; j < k; ++j)
            if (ids[j] == ids[k]) same = j;
          lit_as[k] = same >= 0 ? lit_as[same] : light(ids[k], px, py);
        }
        picture[pixel] = mean(lit_as);
      }
    lit_four(waiting, put);
  }
  // The same, left in the sample buffer for what is drawn over it.
  void light_visible() {
    if (!depth_written) {  // nothing opaque was drawn: the backdrop all over
      if (behind.empty()) {
        std::fill(color.begin(), color.end(), background_stored);
      } else {
        for (size_t pixel = 0; pixel < behind.size(); ++pixel)
          for (int k = 0; k < samples; ++k) color[pixel * samples + k] = behind[pixel];
      }
      return;
    }
    Waiting waiting;
    auto put = [&](size_t pixel, uint32_t found) {
      uint32_t* ids = &color[pixel * samples];
      for (int k = 0; k < samples; ++k) ids[k] = found;
    };
    for (int py = 0; py < height; ++py)
      for (int px = 0; px < width; ++px) {
        uint32_t* ids = &color[((size_t)py * width + px) * samples];
        const bool one = uniform(ids);
        if (one) {
          if ((waiting.count && ids[0] == waiting.id) || four_of(ids[0])) {
            wait(waiting, ids[0], px, py, (size_t)py * width + px, put);
            continue;
          }
          const uint32_t found = light(ids[0], px, py);
          for (int k = 0; k < samples; ++k) ids[k] = found;
          continue;
        }
        uint32_t lit_as[8];
        for (int k = 0; k < samples; ++k) {
          int same = -1;
          for (int j = 0; j < k; ++j)
            if (ids[j] == ids[k]) same = j;
          lit_as[k] = same >= 0 ? lit_as[same] : light(ids[k], px, py);
        }
        for (int k = 0; k < samples; ++k) ids[k] = lit_as[k];
      }
    lit_four(waiting, put);
  }
  void resolve_colors() {
    picture.resize((size_t)width * height);
    for (size_t pixel = 0; pixel < picture.size(); ++pixel) {
      const uint32_t* c = &color[pixel * samples];
      const bool one = uniform(c);
      picture[pixel] = one ? c[0] : mean(c);
    }
  }
  std::vector<uint32_t> picture;

  // An item drawn straight into the colours: depth-tested, lit once a pixel and triangle, and either stored
  // (`write`: its depth too) or blended over what is there, source over, in linear light.
  void forward(const Item& item, bool write) {
    const Tone& t = tone();
    const bool blend = item.blend;
    const bool cut = has_clip && item.cut;
    const int full = (1 << samples) - 1;
    float alpha = 1, src[3] = {0, 0, 0};  // what is being drawn, its colour times its alpha
    uint32_t solid = 0;
    auto take = [&](const float rgba[4]) {
      alpha = clamp01(rgba[3]);
      for (int c = 0; c < 3; ++c) src[c] = clamp01(rgba[c]) * alpha;
      if (!blend) solid = stored(rgba);
    };
    auto over = [&](uint32_t under) {
      const float rest = 1 - alpha;
      return t.pack(src[0] + t.decode[under & 255] * rest, src[1] + t.decode[under >> 8 & 255] * rest,
                    src[2] + t.decode[under >> 16 & 255] * rest);
    };
    // The samples of `mask` that pass the depth, written where the item writes it.
    bool unhidden = false;  // the triangle being drawn passes the depth wherever it is
    auto passing = [&](size_t pixel, int mask, float z, const float* zoff) {
      if (unhidden) return mask;
      float* d = depth_at + pixel * samples;
      if (samples == 4) {
        const f4 exact = splat(z) + load4(zoff), zs = kept_depth4(exact), was = load4(d);
        const i4 lanes = i4{1, 2, 4, 8};
        const i4 ok = ((lanes & i4{mask, mask, mask, mask}) != i4{0, 0, 0, 0}) & (zs <= was) & (exact >= splat(0.0f));
        if (write) {
          const f4 depths = pick(ok, zs, was);
          std::memcpy(d, &depths, sizeof depths);
        }
        return bits_of(ok);
      }
      int pass = 0;
      for (int k = 0; k < samples; ++k) {
        const float exact = z + zoff[k], zs = kept_depth(exact);
        if ((mask >> k & 1) && zs <= d[k] && exact >= 0) {
          pass |= 1 << k;
          if (write) d[k] = zs;
        }
      }
      return pass;
    };
    auto apply = [&](size_t pixel, int pass) {
      uint32_t* c = color_at + pixel * samples;
      if (!blend) {
        for (int k = 0; k < samples; ++k)
          if (pass >> k & 1) c[k] = solid;
        return;
      }
      if (pass == full) {
        if (samples == 4) {
          if (c[0] == c[1] && c[0] == c[2] && c[0] == c[3]) {
            c[0] = c[1] = c[2] = c[3] = over(c[0]);
            return;
          }
        } else {
          const bool one = uniform(c);
          if (one) {
            const uint32_t found = over(c[0]);
            for (int k = 0; k < samples; ++k) c[k] = found;
            return;
          }
        }
      }
      uint32_t last_in = 0, last_out = 0;
      bool have = false;
      for (int k = 0; k < samples; ++k) {
        if (!(pass >> k & 1)) continue;
        if (!have || c[k] != last_in) last_in = c[k], last_out = over(last_in), have = true;
        c[k] = last_out;
      }
    };
    if (write && item.count) depth_written = true;
    if (item.kind == EDGES) {
      const float rgba[4] = {item.color[0], item.color[1], item.color[2], 1};
      take(rgba);
      solid = flats[item.flat & ~FLAT];
      for (uint32_t at = item.first; at < item.first + item.count; ++at)
        raster_segment(segments[(size_t)at * 2], segments[(size_t)at * 2 + 1], item.width, cut,
                       [&](size_t pixel, int, int, int mask, float z, const float* zoff) {
                         if (int pass = passing(pixel, mask, z, zoff)) apply(pixel, pass);
                       });
      return;
    }
    if (item.kind == CAP) return;
    for (uint32_t at = item.first; at < item.first + item.count; ++at) {
      const Triangle& tri = triangles[at];
      // One colour all over: an unlit face without a texture, or a flat lit one under an orthographic camera.
      const bool even = item.shading == UNLIT
                            ? !item.textured && !item.colored
                            : !perspective && !shadow_size && !item.textured &&
                                  std::memcmp(&attributes[(size_t)tri.v[0] * 3], &attributes[(size_t)tri.v[1] * 3], 12) == 0 &&
                                  std::memcmp(&attributes[(size_t)tri.v[0] * 3], &attributes[(size_t)tri.v[2] * 3], 12) == 0;
      bool lit_once = false;
      // Over a depth nothing has written, a triangle that writes none and lies between the planes (its offset and
      // a margin for the rounding counted) asks no sample for its depth.
      if (!write && !depth_written) {
        const float z0 = points[tri.v[0]].z, z1 = points[tri.v[1]].z, z2 = points[tri.v[2]].z;
        const float low = std::min(z0, std::min(z1, z2)), high = std::max(z0, std::max(z1, z2));
        const float reach = (high - low) * std::fabs(item.offset_factor) + std::fabs(item.offset_units) * DEPTH_UNIT + 1e-5f;
        unhidden = item.offset_factor == 0 && low - reach >= 0 && high + reach <= 1;
      } else {
        unhidden = false;
      }
      if (!even && by_four(item)) {
        // Lit four pixels at a time: the pixels that pass are kept, then lit and applied together.
        int qx[4], qy[4], passes[4], held = 0;
        size_t at_pixel[4];
        auto flush = [&]() {
          float rgba[4][4];
          for (int k = held; k < 4; ++k) qx[k] = qx[0], qy[k] = qy[0];
          shade4(tri, qx, qy, held, rgba);
          for (int k = 0; k < held; ++k) take(rgba[k]), apply(at_pixel[k], passes[k]);
          held = 0;
        };
        raster_triangle(tri, item.offset_factor, item.offset_units, cut,
                        [&](size_t pixel, int px, int py, int mask, float z, const float* zoff) {
                          const int pass = passing(pixel, mask, z, zoff);
                          if (!pass) return;
                          qx[held] = px, qy[held] = py, passes[held] = pass, at_pixel[held] = pixel;
                          if (++held == 4) flush();
                        });
        if (held) flush();
        continue;
      }
      raster_triangle(tri, item.offset_factor, item.offset_units, cut,
                      [&](size_t pixel, int px, int py, int mask, float z, const float* zoff) {
                        const int pass = passing(pixel, mask, z, zoff);
                        if (!pass) return;  // lit only where a sample passes the depth
                        if (!even || !lit_once) {
                          float rgba[4];
                          shade(tri, px, py, rgba);
                          take(rgba);
                          lit_once = true;
                        }
                        apply(pixel, pass);
                      });
    }
  }
};

std::string png(const std::vector<uint32_t>& picture, int width, int height) {
  std::string rows;
  rows.reserve((size_t)height * (1 + (size_t)width * 3));
  for (int y = 0; y < height; ++y) {
    rows.push_back('\0');
    for (int x = 0; x < width; ++x) {
      uint32_t c = picture[(size_t)y * width + x];
      rows.push_back((char)(c & 255)), rows.push_back((char)(c >> 8 & 255)), rows.push_back((char)(c >> 16 & 255));
    }
  }
  z_stream z{};
  if (deflateInit(&z, 6) != Z_OK) throw std::runtime_error("deflate failed to start");
  std::string packed(deflateBound(&z, (uLong)rows.size()) + 16, '\0');
  z.next_in = (Bytef*)rows.data(), z.avail_in = (uInt)rows.size();
  z.next_out = (Bytef*)&packed[0], z.avail_out = (uInt)packed.size();
  if (deflate(&z, Z_FINISH) != Z_STREAM_END) {
    deflateEnd(&z);
    throw std::runtime_error("the picture could not be deflated");
  }
  packed.resize(z.total_out);
  deflateEnd(&z);
  std::string out("\x89PNG\r\n\x1a\n", 8);
  auto chunk = [&](const char* kind, const std::string& body) {
    uint32_t length = (uint32_t)body.size();
    const char be[4] = {(char)(length >> 24), (char)(length >> 16), (char)(length >> 8), (char)length};
    out.append(be, 4);
    std::string checked(kind, 4);
    checked += body;
    out += checked;
    uint32_t crc = (uint32_t)crc32(0L, (const Bytef*)checked.data(), (uInt)checked.size());
    const char ce[4] = {(char)(crc >> 24), (char)(crc >> 16), (char)(crc >> 8), (char)crc};
    out.append(ce, 4);
  };
  std::string header(13, '\0');
  header[0] = (char)(width >> 24), header[1] = (char)(width >> 16), header[2] = (char)(width >> 8), header[3] = (char)width;
  header[4] = (char)(height >> 24), header[5] = (char)(height >> 16), header[6] = (char)(height >> 8), header[7] = (char)height;
  header[8] = 8, header[9] = 2;
  chunk("IHDR", header);
  chunk("IDAT", packed);
  chunk("IEND", std::string());
  return out;
}

}  // namespace

std::string render(const std::string& scene_text, const uint8_t* blob, size_t size) {
  RENDER_CLOCK(started);
  Value scene = Value::parse(scene_text);
  if (scene.kind != Value::OBJECT) throw std::invalid_argument("the scene is no object");
  Renderer renderer;
  std::string format = text(scene.get("format"), "rgba");
  renderer.depth_only = format == "depth";
  renderer.read(scene, blob, size);
  RENDER_SAY("read", started);
  if (renderer.shadow_light >= 0 && !renderer.depth_only) {
    // The shadow's light looks at the scene first: its map, and where it sees each point.
    RENDER_CLOCK(casting);
    const Light& light = renderer.lights[renderer.shadow_light];
    Renderer seen(true);
    seen.shadow_size = light.shadow_size;
    seen.read(scene, blob, size);
    seen.light_camera(light);
    seen.shadow_size = 0;  // its own points ask for no shadow
    seen.place_all();
    seen.draw_shadow();
    renderer.shadow_map = std::move(seen.own_depth);
    renderer.shadow_size = light.shadow_size;
    for (int c = 0; c < 3; ++c) {
      renderer.shadow_axes[0][c] = seen.right[c] / seen.pixel;
      renderer.shadow_axes[1][c] = -seen.up[c] / seen.pixel;
      renderer.shadow_axes[2][c] = seen.ahead[c] / (seen.far - seen.near);
    }
    double from[3] = {0, 0, 0};
    for (int c = 0; c < 3; ++c)
      from[0] += seen.eye[c] * seen.right[c], from[1] += seen.eye[c] * seen.up[c], from[2] += seen.eye[c] * seen.ahead[c];
    renderer.shadow_axes[0][3] = light.shadow_size / 2.0 - from[0] / seen.pixel;
    renderer.shadow_axes[1][3] = light.shadow_size / 2.0 + from[1] / seen.pixel;
    renderer.shadow_axes[2][3] = (-from[2] - seen.near) / (seen.far - seen.near);
    RENDER_SAY("shadow", casting);
  }
  RENDER_CLOCK(placing);
  renderer.place_all();
  RENDER_SAY("place", placing);
  renderer.background_stored = tone().pack(clamp01(renderer.background[0]), clamp01(renderer.background[1]),
                                           clamp01(renderer.background[2]));
  renderer.draw();
  RENDER_CLOCK(writing);
  std::string out;
  if (format == "depth") {
    // The depth of each pixel's first sample, 0 at the near plane to 1 at the far and where nothing is: floats.
    std::vector<float> values((size_t)renderer.width * renderer.height);
    for (size_t pixel = 0; pixel < values.size(); ++pixel)
      values[pixel] = renderer.depth[pixel * renderer.samples] * (1.0f / DEPTH_FAR);
    out.assign((const char*)values.data(), values.size() * 4);
  } else if (format == "png") {
    out = png(renderer.picture, renderer.width, renderer.height);
  } else if (format == "rgba") {
    out.assign((const char*)renderer.picture.data(), renderer.picture.size() * 4);
  } else {
    throw std::invalid_argument("the scene asks for a picture as " + format + ": rgba, png or depth");
  }
  RENDER_SAY("write", writing);
  RENDER_SAY("all", started);
  // A very large still's buffers are given back; an ordinary one's are kept for the next.
  if (Renderer::depths().capacity() > (size_t)1 << 24) {
    std::vector<float>().swap(Renderer::depths());
    std::vector<uint32_t>().swap(Renderer::colors());
  }
  return out;
}

}  // namespace vc
