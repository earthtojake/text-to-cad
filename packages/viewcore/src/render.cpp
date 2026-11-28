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

  Environment(const uint8_t* image, int width, int height) {
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
    found.n = 1 << (SPECULAR_POW2 - index);
    found.t.assign((size_t)6 * found.n * found.n * 3, 0.0f);
    found.done.assign((size_t)6 * found.n * found.n, 0);
    if (index == 0) return found;
    const float roughness = (float)index / (float)(SPECULAR_LEVELS - 1);
    const float real = occ_roughness(roughness);
    float quad = real * real;
    quad *= quad;
    // Graphic3d_PBRMaterial::SpecIBLMapSamplesFactor: fewer samples for a narrower lobe.
    float edge = std::sqrt((1.0f - SPECULAR_PROBABILITY) / (1.0f + (quad_of(roughness) - 1.0f) * SPECULAR_PROBABILITY));
    const int count = (int)(std::acos(edge) * 2.0f / PI_F * (float)SPECULAR_SAMPLES);
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

  inline void read_level(int index, const float d[3], float out[3]) {
    Prefiltered& found = level(index);
    int face;
    float s, u;
    face_of(d, face, s, u);
    float fx = (s * 0.5f + 0.5f) * found.n - 0.5f, fy = (u * 0.5f + 0.5f) * found.n - 0.5f;
    int i = (int)std::floor(fx), j = (int)std::floor(fy);
    float tx = fx - i, ty = fy - j;
    const float* a = texel(index, found, face, i, j);
    const float* b = texel(index, found, face, i + 1, j);
    const float* c = texel(index, found, face, i, j + 1);
    const float* e = texel(index, found, face, i + 1, j + 1);
    for (int k = 0; k < 3; ++k)
      out[k] = (a[k] * (1 - tx) + b[k] * tx) * (1 - ty) + (c[k] * (1 - tx) + e[k] * tx) * ty;
  }

  // textureCubeLod(occSpecIBLMap, r, lod) along a model direction.
  inline void specular(const float r[3], float lod, float out[3]) {
    const float d[3] = {r[1], r[2], r[0]};
    int low = (int)lod;
    if (low >= SPECULAR_LEVELS - 1) return read_level(SPECULAR_LEVELS - 1, d, out);
    float share = lod - low;
    float a[3], b[3];
    read_level(low, d, a);
    if (share <= 0) {
      out[0] = a[0], out[1] = a[1], out[2] = a[2];
      return;
    }
    read_level(low + 1, d, b);
    for (int c = 0; c < 3; ++c) out[c] = a[c] * (1 - share) + b[c] * share;
  }
};

Environment& environment(const uint8_t* image, size_t size, int width, int height) {
  static std::map<uint64_t, std::unique_ptr<Environment>> kept;
  uint64_t hash = 1469598103934665603ull ^ ((uint64_t)width << 32 | (uint32_t)height);
  for (size_t at = 0; at < size; ++at) hash = (hash ^ image[at]) * 1099511628211ull;
  auto found = kept.find(hash);
  if (found != kept.end()) return *found->second;
  if (kept.size() >= 2) kept.clear();
  return *(kept[hash] = std::make_unique<Environment>(image, width, height));
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
  bool blend = false, cut = true, mirrored = false, textured = false;
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
const double GUARD = 8192;                    // pixels beyond the picture a triangle may reach before it is clipped

// A triangle set up for the rasterizer: its edges as integer functions of the pixel (8 bits below it), its depth a
// plane.
struct Setup {
  int x0, x1, y0, y1;
  int64_t a[3], b[3], c[3];
  int64_t off[3][8], off_low[3], off_high[3];
  float zx, zy, z0;
  float zoff[8];
  bool front;
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

  std::vector<Span> payloads;
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

  std::vector<float> depth;
  std::vector<uint32_t> color;  // per sample: a triangle's number while the opaque are drawn, then the colour stored
  int sx[8], sy[8];

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
    if (samples != 1 && samples != 2 && samples != 4 && samples != 8)
      throw std::invalid_argument("the scene's samples are not 1, 2, 4 or 8");
    // OpenGL's y runs up the picture, and its samples and its fill rule with it.
    for (int s = 0; s < samples; ++s) sx[s] = SAMPLE_AT[samples][s][0] * 16, sy[s] = (16 - SAMPLE_AT[samples][s][1]) * 16;
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
    if (const Value* plane = scene.get("clip")) {
      numbers(plane, clip, 4, "clip");
      has_clip = true;
    }
    read_lights(scene);
    const Value* draw = scene.get("draw");
    if (draw)
      for (const Value& entry : draw->items) read_item(entry);
    read_camera(scene);
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
        lights.push_back(found);
      }
    if (light) {
      lit = true;
      if (const Value* image = light->get("environment")) {
        Span span = payload(image->get("payload"), "environment");
        int w = (int)need(*image, "width"), h = (int)need(*image, "height");
        if (w < 1 || h < 1 || (size_t)w * h * 12 != span.size)
          throw std::invalid_argument("the scene's environment is not width x height x 3 floats");
        env = &environment(span.data, span.size, w, h);
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

  void read_item(const Value& entry) {
    Item item;
    static const double identity[16] = {1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1};
    std::memcpy(item.matrix, identity, sizeof identity);
    if (entry.get("matrix")) numbers(entry.get("matrix"), item.matrix, 16, "matrix");
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
      if (entry.get("offset")) {
        numbers(entry.get("offset"), four, 2, "offset");
        item.offset_factor = (float)four[0], item.offset_units = (float)four[1];
      }
      if (const Value* picture = entry.get("texture")) {
        item.texture = payload(picture->get("payload"), "texture");
        item.texture_width = (int)need(*picture, "width"), item.texture_height = (int)need(*picture, "height");
        if (item.texture_width < 1 || item.texture_height < 1 ||
            (size_t)item.texture_width * item.texture_height * 4 != item.texture.size)
          throw std::invalid_argument("the scene's texture is not width x height RGBA bytes");
        item.textured = true;
      }
      place_triangles(item, *named);
    } else {
      throw std::invalid_argument("the scene draws something that is no faces, edges, cap or triangles");
    }
    items.push_back(item);
  }

  // --- the camera ---

  double low[3], high[3];
  bool bounded = false;
  void bound(const double p[3]) {
    for (int c = 0; c < 3; ++c) {
      if (!bounded || p[c] < low[c]) low[c] = p[c];
      if (!bounded || p[c] > high[c]) high[c] = p[c];
    }
    bounded = true;
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
    for (size_t at = 0; at + 12 <= positions.size; at += 12) {
      double p[3] = {load<float>(positions.data + at), load<float>(positions.data + at + 4),
                     load<float>(positions.data + at + 8)}, w[3];
      transform(item.matrix, p, w);
      bound(w);
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
    // Graphic3d_Camera::ZFitAll at scale 1: the box of what is drawn, between the planes.
    double least = 0, most = 1;
    if (bounded) {
      for (int corner = 0; corner < 8; ++corner) {
        double d = 0;
        for (int c = 0; c < 3; ++c) d += ((corner >> c & 1 ? high[c] : low[c]) - eye[c]) * ahead[c];
        if (!corner || d < least) least = d;
        if (!corner || d > most) most = d;
      }
    }
    double slack = 1e-6 * (std::fabs(least) + std::fabs(most) + (most - least)) + 1e-9;
    near = least - slack, far = most + slack;
    if (perspective) {
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

  uint32_t add_point(const double w[3], const float attribute[3]) {
    double v[3];
    view_of(w, v);
    Point p = {0, 0, 0, 1};
    bool inside = project(v, p);
    points.push_back(p);
    attributes.insert(attributes.end(), attribute, attribute + 3);
    cuts.push_back(has_clip ? (float)(cut_of(w) * (perspective && inside ? p.iw : 1.0f)) : 0.0f);
    outside.push_back(inside ? 0 : 1);
    return (uint32_t)(points.size() - 1);
  }

  // A mesh's nodes (or its edges' points) placed by a matrix, once for every item that draws them.
  uint32_t place(int mesh_index, const double* matrix, bool edge_points) {
    std::string key((const char*)matrix, 16 * sizeof(double));
    key.push_back((char)edge_points);
    key.append((const char*)&mesh_index, sizeof mesh_index);
    auto found = placed.find(key);
    if (found != placed.end()) return found->second;
    const Mesh& mesh = meshes[mesh_index];
    uint32_t base = (uint32_t)points.size();
    const double* m = matrix;
    // A normal goes by the inverse transpose: the cofactors (here a column after a column), by the determinant's sign.
    double co[9] = {m[5] * m[10] - m[6] * m[9], m[6] * m[8] - m[4] * m[10], m[4] * m[9] - m[5] * m[8],
                    m[2] * m[9] - m[1] * m[10], m[0] * m[10] - m[2] * m[8], m[1] * m[8] - m[0] * m[9],
                    m[1] * m[6] - m[2] * m[5], m[2] * m[4] - m[0] * m[6], m[0] * m[5] - m[1] * m[4]};
    double det = m[0] * co[0] + m[4] * co[3] + m[8] * co[6];
    double sign = det < 0 ? -1 : 1;
    uint32_t count = edge_points ? mesh.npoints : mesh.nodes;
    const uint8_t* from = edge_points ? mesh.edge_points : mesh.positions;
    for (uint32_t at = 0; at < count; ++at) {
      double p[3] = {load<float>(from + (size_t)at * 12), load<float>(from + (size_t)at * 12 + 4),
                     load<float>(from + (size_t)at * 12 + 8)}, w[3];
      transform(m, p, w);
      float attribute[3] = {0, 0, 0};
      if (!edge_points) {
        double n[3] = {load<float>(mesh.normals + (size_t)at * 12), load<float>(mesh.normals + (size_t)at * 12 + 4),
                       load<float>(mesh.normals + (size_t)at * 12 + 8)};
        attribute[0] = (float)(sign * (co[0] * n[0] + co[3] * n[1] + co[6] * n[2]));
        attribute[1] = (float)(sign * (co[1] * n[0] + co[4] * n[1] + co[7] * n[2]));
        attribute[2] = (float)(sign * (co[2] * n[0] + co[5] * n[1] + co[8] * n[2]));
      }
      add_point(w, attribute);
    }
    placed[key] = base;
    return base;
  }

  // --- clipping what cannot be drawn as it is ---

  struct Corner {
    double v[3];  // view coordinates
    float attribute[3];
    double cut;
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
      if (item.kind != TRIANGLES) most += item.kind == EDGES ? meshes[item.mesh].npoints : meshes[item.mesh].nodes;
    }
    points.reserve(most), attributes.reserve(most * 3), cuts.reserve(most), outside.reserve(most);
    for (const Pending& wait : pending) {
      Item& item = items[wait.item];
      item.first = (uint32_t)(item.kind == EDGES ? segments.size() / 2 : triangles.size());
      if (item.kind == FACES || item.kind == CAP) {
        const Mesh& mesh = meshes[item.mesh];
        uint32_t base = place(item.mesh, item.matrix, false);
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
      } else if (item.kind == EDGES) {
        const Mesh& mesh = meshes[item.mesh];
        uint32_t base = place(item.mesh, item.matrix, true);
        for (uint32_t edge = 0; edge < mesh.nedges; ++edge) {
          uint32_t first = load<uint32_t>(mesh.edges + (size_t)edge * 16 + 4);
          uint32_t count = load<uint32_t>(mesh.edges + (size_t)edge * 16 + 8);
          uint32_t kind = load<uint32_t>(mesh.edges + (size_t)edge * 16 + 12);
          if (count < 2 || !(wait.classes >> (kind & 31u) & 1u)) continue;
          if ((uint64_t)first + count > mesh.npoints) throw std::invalid_argument("an edge leaves its mesh");
          for (uint32_t at = first; at + 1 < first + count; ++at) add_segment(item, mesh, base, at);
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
        uint32_t base = (uint32_t)points.size();
        auto world_of = [&](uint32_t at, double w[3]) {
          double p[3] = {load<float>(positions.data + (size_t)at * 12), load<float>(positions.data + (size_t)at * 12 + 4),
                         load<float>(positions.data + (size_t)at * 12 + 8)};
          transform(item.matrix, p, w);
        };
        for (uint32_t at = 0; at < count; ++at) {
          double w[3];
          world_of(at, w);
          float attribute[3] = {0, 0, 0};
          if (texels.data)
            attribute[0] = load<float>(texels.data + (size_t)at * 8), attribute[1] = load<float>(texels.data + (size_t)at * 8 + 4);
          add_point(w, attribute);
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

  void add_segment(const Item& item, const Mesh& mesh, uint32_t base, uint32_t at) {
    uint32_t a = base + at, b = a + 1;
    if (!(outside[a] | outside[b])) {
      segments.push_back(a), segments.push_back(b);
      return;
    }
    Corner ends[2];
    for (int k = 0; k < 2; ++k) {
      double p[3] = {load<float>(mesh.edge_points + (size_t)(at + k) * 12),
                     load<float>(mesh.edge_points + (size_t)(at + k) * 12 + 4),
                     load<float>(mesh.edge_points + (size_t)(at + k) * 12 + 8)}, w[3];
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

  // A triangle's setup; false where it covers nothing. `factor` and `units` are glPolygonOffset's.
  bool setup(const Point& p0, const Point& p1, const Point& p2, float factor, float units, Setup& s) const {
    int64_t x[3] = {(int64_t)std::lround(p0.x * 256.0f), (int64_t)std::lround(p1.x * 256.0f),
                    (int64_t)std::lround(p2.x * 256.0f)};
    int64_t y[3] = {(int64_t)std::lround(p0.y * 256.0f), (int64_t)std::lround(p1.y * 256.0f),
                    (int64_t)std::lround(p2.y * 256.0f)};
    float z[3] = {p0.z, p1.z, p2.z};
    int64_t area = (x[1] - x[0]) * (y[2] - y[0]) - (x[2] - x[0]) * (y[1] - y[0]);
    if (area == 0) return false;
    s.front = area < 0;  // counter-clockwise as the eye sees it, the picture's y running down
    if (area < 0) {
      std::swap(x[1], x[2]), std::swap(y[1], y[2]), std::swap(z[1], z[2]);
      area = -area;
    }
    int64_t low_x = std::min(x[0], std::min(x[1], x[2])), high_x = std::max(x[0], std::max(x[1], x[2]));
    int64_t low_y = std::min(y[0], std::min(y[1], y[2])), high_y = std::max(y[0], std::max(y[1], y[2]));
    s.x0 = (int)std::max<int64_t>(0, low_x >> 8), s.x1 = (int)std::min<int64_t>(width - 1, high_x >> 8);
    s.y0 = (int)std::max<int64_t>(0, low_y >> 8), s.y1 = (int)std::min<int64_t>(height - 1, high_y >> 8);
    if (s.x0 > s.x1 || s.y0 > s.y1) return false;
    for (int e = 0; e < 3; ++e) {
      int from = e, to = (e + 1) % 3;
      int64_t dx = x[to] - x[from], dy = y[to] - y[from];
      s.a[e] = -dy, s.b[e] = dx;
      s.c[e] = dy * x[from] - dx * y[from];
      if (!(dy < 0 || (dy == 0 && dx < 0))) s.c[e] -= 1;  // not a left edge or OpenGL's top: its own points are outside
      s.off_low[e] = INT64_MAX, s.off_high[e] = INT64_MIN;
      for (int k = 0; k < samples; ++k) {
        s.off[e][k] = s.a[e] * sx[k] + s.b[e] * sy[k];
        s.off_low[e] = std::min(s.off_low[e], s.off[e][k]);
        s.off_high[e] = std::max(s.off_high[e], s.off[e][k]);
      }
    }
    // The depth's plane over the picture, in pixels.
    double fx[3] = {x[0] / 256.0, x[1] / 256.0, x[2] / 256.0}, fy[3] = {y[0] / 256.0, y[1] / 256.0, y[2] / 256.0};
    double inverse = 1.0 / ((fx[1] - fx[0]) * (fy[2] - fy[0]) - (fx[2] - fx[0]) * (fy[1] - fy[0]));
    double zx = ((z[1] - z[0]) * (fy[2] - fy[0]) - (z[2] - z[0]) * (fy[1] - fy[0])) * inverse;
    double zy = ((z[2] - z[0]) * (fx[1] - fx[0]) - (z[1] - z[0]) * (fx[2] - fx[0])) * inverse;
    double z0 = z[0] - zx * fx[0] - zy * fy[0];
    if (factor != 0 || units != 0)
      z0 += factor * std::max(std::fabs(zx), std::fabs(zy)) + units * DEPTH_UNIT;
    s.zx = (float)zx, s.zy = (float)zy, s.z0 = (float)z0;
    for (int k = 0; k < samples; ++k) s.zoff[k] = (float)(zx * (sx[k] / 256.0) + zy * (sy[k] / 256.0));
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
    const int64_t step[3] = {s.a[0] * 256, s.a[1] * 256, s.a[2] * 256};
    for (int py = s.y0; py <= s.y1; ++py) {
      int64_t row[3];
      for (int e = 0; e < 3; ++e) row[e] = s.a[e] * ((int64_t)s.x0 * 256) + s.b[e] * ((int64_t)py * 256) + s.c[e];
      // The row's span: where each edge function can be non-negative at some sample.
      int from = s.x0, to = s.x1;
      if (to - from > 6) {
        for (int e = 0; e < 3; ++e) {
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
      int64_t e0 = row[0] + step[0] * (from - s.x0), e1 = row[1] + step[1] * (from - s.x0),
              e2 = row[2] + step[2] * (from - s.x0);
      const float zrow = s.z0 + s.zy * (float)py;
      const float crow = s.cut ? s.c0 + s.cy * (float)py : 0.0f;
      size_t pixel = (size_t)py * width + from;
      for (int px = from; px <= to; ++px, ++pixel, e0 += step[0], e1 += step[1], e2 += step[2]) {
        if (((e0 + s.off_high[0]) | (e1 + s.off_high[1]) | (e2 + s.off_high[2])) < 0) continue;
        int mask;
        if (((e0 + s.off_low[0]) | (e1 + s.off_low[1]) | (e2 + s.off_low[2])) >= 0) {
          mask = full;
        } else {
          mask = 0;
          for (int k = 0; k < samples; ++k)
            if (((e0 + s.off[0][k]) | (e1 + s.off[1][k]) | (e2 + s.off[2][k])) >= 0) mask |= 1 << k;
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
    float nx = -dy / length * (line * 0.5f), ny = dx / length * (line * 0.5f);
    Point corner[4] = {{a.x + nx, a.y + ny, a.z, a.iw}, {a.x - nx, a.y - ny, a.z, a.iw},
                       {b.x - nx, b.y - ny, b.z, b.iw}, {b.x + nx, b.y + ny, b.z, b.iw}};
    float ca = cuts[ia], cb = cuts[ib];
    Setup s;
    if (setup(corner[0], corner[1], corner[2], 0, 0, s) && (!cut || setup_cut(corner[0], corner[1], corner[2], ca, ca, cb, s)))
      raster(s, sink);
    if (setup(corner[0], corner[2], corner[3], 0, 0, s) && (!cut || setup_cut(corner[0], corner[2], corner[3], ca, cb, cb, s)))
      raster(s, sink);
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

  // OCCT's PBR program (Graphic3d_ShaderManager's computeLighting, PBRIllumination.glsl): the colour, linear, and
  // the alpha a see-through face is blended by.
  // A face seen from behind (`back`) is lit by its normal turned over, as the program's lights turn it; the
  // environment's light is read by the normal as it is, as the program reads it.
  inline void pbr(const Item& m, const float n[3], bool back, const float v[3], float out[4]) const {
    const float nv = n[0] * v[0] + n[1] * v[1] + n[2] * v[2];
    const float side = back ? -1.0f : 1.0f;
    const float cos_v = nv * side > 0 ? nv * side : 0;
    float sum[3] = {0, 0, 0};
    for (const Light& light : lights) {
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
        float f = m.f0[c] + (1.0f - m.f0[c]) * fresnel;
        float diffuse = (1.0f - f) * (1.0f - m.metallic) * INV_PI * m.color[c] * m.alpha;
        sum[c] += (diffuse + dg * f) * light.intensity * nl;
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
        float toward = std::max(1.0f - m.normalized, m.f0[c]);
        float refraction = (1.0f - (m.f0[c] + (toward - m.f0[c]) * fresnel)) * (1.0f - m.metallic);
        if (c == 0) refraction_x = refraction;
        float indirect = refraction * m.color[c] * m.alpha * irradiance[c] + (m.f0[c] * scale + bias) * reflected[c];
        sum[c] += ambient * indirect;
      }
    } else {
      float fresnel = 1.0f - std::fabs(nv);
      fresnel *= fresnel;
      fresnel *= fresnel * fresnel * fresnel * fresnel;
      float toward = std::max(1.0f - m.normalized, m.f0[0]);
      refraction_x = (1.0f - (m.f0[0] + (toward - m.f0[0]) * fresnel)) * (1.0f - m.metallic);
    }
    for (int c = 0; c < 3; ++c) out[c] = sum[c] + m.emission[c];
    out[3] = 1.0f + (m.alpha - 1.0f) * refraction_x;
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
    int x1 = std::min(m.texture_width - 1, std::max(0, x0 + 1)), y1 = std::min(m.texture_height - 1, std::max(0, y0 + 1));
    x0 = std::min(m.texture_width - 1, std::max(0, x0)), y0 = std::min(m.texture_height - 1, std::max(0, y0));
    const uint8_t* a = m.texture.data + ((size_t)y0 * m.texture_width + x0) * 4;
    const uint8_t* b = m.texture.data + ((size_t)y0 * m.texture_width + x1) * 4;
    const uint8_t* c = m.texture.data + ((size_t)y1 * m.texture_width + x0) * 4;
    const uint8_t* d = m.texture.data + ((size_t)y1 * m.texture_width + x1) * 4;
    for (int k = 0; k < 3; ++k)
      out[k] = (t.decode[a[k]] * (1 - tx) + t.decode[b[k]] * tx) * (1 - ty) +
               (t.decode[c[k]] * (1 - tx) + t.decode[d[k]] * tx) * ty;
    out[3] = ((a[3] * (1 - tx) + b[3] * tx) * (1 - ty) + (c[3] * (1 - tx) + d[3] * tx) * ty) * (1.0f / 255.0f);
  }

  // A triangle's colour at a pixel's centre (linear, and its alpha), its attributes read there as OpenGL reads
  // them: by the pixel's place in the triangle, through the perspective.
  inline void shade(const Triangle& t, int px, int py, float out[4]) const {
    const Item& m = items[t.item];
    const Point &p0 = points[t.v[0]], &p1 = points[t.v[1]], &p2 = points[t.v[2]];
    // The points as the rasterizer placed them, to 1/256 of a pixel.
    const float x0 = std::nearbyint(p0.x * 256.0f) * (1.0f / 256.0f), y0 = std::nearbyint(p0.y * 256.0f) * (1.0f / 256.0f);
    const float ax = std::nearbyint(p1.x * 256.0f) * (1.0f / 256.0f) - x0, ay = std::nearbyint(p1.y * 256.0f) * (1.0f / 256.0f) - y0;
    const float bx = std::nearbyint(p2.x * 256.0f) * (1.0f / 256.0f) - x0, by = std::nearbyint(p2.y * 256.0f) * (1.0f / 256.0f) - y0;
    const float area = ax * by - bx * ay;
    const float qx = px + 0.5f - x0, qy = py + 0.5f - y0;
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
      float v0[3], v1[3], v2[3];
      view_at(p0.x, p0.y, v0), view_at(p1.x, p1.y, v1), view_at(p2.x, p2.y, v2);
      for (int c = 0; c < 3; ++c) v[c] = v0[c] * l0 + v1[c] * l1 + v2[c] * l2;
      float m = 1.0f / std::sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]);
      v[0] *= m, v[1] *= m, v[2] *= m;
    } else {
      v[0] = (float)-ahead[0], v[1] = (float)-ahead[1], v[2] = (float)-ahead[2];
    }
    if (m.shading == PBR) pbr(m, a, back, v, out);
    else colour_only(m, a, v, out);
  }

  inline uint32_t stored(const float c[4]) const { return tone().pack(c[0], c[1], c[2]); }

  // --- the passes ---

  void draw() {
    const size_t count = (size_t)width * height * samples;
    depth.assign(count, 1.0f);
    color.assign(count, 0u);
    bool after = false;  // anything drawn once the opaque are lit: see-through surfaces, the layers above
    for (const Item& item : items)
      if (item.layer != 0 || item.blend || item.kind == TRIANGLES) after = true;
    RENDER_CLOCK(started);
    // The opaque of the model's layer, into the visibility buffer.
    for (size_t index = 0; index < items.size(); ++index) {
      const Item& item = items[index];
      if (item.layer != 0 || item.blend) continue;
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
      if (layer == 2) std::fill(depth.begin(), depth.end(), 1.0f);
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

  inline void visible(size_t pixel, int mask, float z, const float* zoff, uint32_t id) {
    float* d = &depth[pixel * samples];
    uint32_t* c = &color[pixel * samples];
    for (int k = 0; k < samples; ++k) {
      if (!(mask >> k & 1)) continue;
      float zs = z + zoff[k];
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
          float zs = (float)(z0 + zx * (px + sx[k] / 256.0) + zy * (py + sy[k] / 256.0));
          if (zs >= 0 && zs < d[k]) d[k] = zs, c[k] = item.flat;  // the capping's own depth test: nearer alone
        }
      }
  }
  std::vector<uint8_t> parity;

  inline uint32_t light(uint32_t id, int px, int py) const {
    if (id == 0) return background_stored;
    if (id & FLAT) return flats[id & ~FLAT];
    float c[4];
    shade(triangles[id - 1], px, py, c);
    return stored(c);
  }
  uint32_t background_stored = 0;

  inline uint32_t mean(const uint32_t* c) const {
    const Tone& t = tone();
    float r = 0, g = 0, b = 0;
    for (int k = 0; k < samples; ++k) {
      r += t.decode[c[k] & 255], g += t.decode[c[k] >> 8 & 255], b += t.decode[c[k] >> 16 & 255];
    }
    float share = 1.0f / samples;
    return t.pack(r * share, g * share, b * share);
  }

  // Each sample's triangle lit, into the picture: once a pixel where one triangle has it whole.
  void resolve_visible() {
    picture.resize((size_t)width * height);
    for (int py = 0; py < height; ++py)
      for (int px = 0; px < width; ++px) {
        size_t pixel = (size_t)py * width + px;
        const uint32_t* ids = &color[pixel * samples];
        bool one = true;
        for (int k = 1; k < samples; ++k) one &= ids[k] == ids[0];
        if (one) {
          picture[pixel] = light(ids[0], px, py);
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
  }
  // The same, left in the sample buffer for what is drawn over it.
  void light_visible() {
    for (int py = 0; py < height; ++py)
      for (int px = 0; px < width; ++px) {
        uint32_t* ids = &color[((size_t)py * width + px) * samples];
        uint32_t lit_as[8];
        for (int k = 0; k < samples; ++k) {
          int same = -1;
          for (int j = 0; j < k; ++j)
            if (ids[j] == ids[k]) same = j;
          lit_as[k] = same >= 0 ? lit_as[same] : light(ids[k], px, py);
        }
        for (int k = 0; k < samples; ++k) ids[k] = lit_as[k];
      }
  }
  void resolve_colors() {
    picture.resize((size_t)width * height);
    for (size_t pixel = 0; pixel < picture.size(); ++pixel) {
      const uint32_t* c = &color[pixel * samples];
      bool one = true;
      for (int k = 1; k < samples; ++k) one &= c[k] == c[0];
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
    auto apply = [&](size_t pixel, int mask, float z, const float* zoff, const float rgba[4], uint32_t solid) {
      float* d = &depth[pixel * samples];
      uint32_t* c = &color[pixel * samples];
      float alpha = clamp01(rgba[3]);
      float src[3] = {clamp01(rgba[0]) * alpha, clamp01(rgba[1]) * alpha, clamp01(rgba[2]) * alpha};
      uint32_t last_in = 0, last_out = 0;
      bool have = false;
      for (int k = 0; k < samples; ++k) {
        if (!(mask >> k & 1)) continue;
        float zs = z + zoff[k];
        if (!(zs <= d[k]) || zs < 0) continue;
        if (write) d[k] = zs;
        if (!blend) {
          c[k] = solid;
          continue;
        }
        if (!have || c[k] != last_in) {
          last_in = c[k];
          last_out = t.pack(src[0] + t.decode[last_in & 255] * (1 - alpha), src[1] + t.decode[last_in >> 8 & 255] * (1 - alpha),
                            src[2] + t.decode[last_in >> 16 & 255] * (1 - alpha));
          have = true;
        }
        c[k] = last_out;
      }
    };
    if (item.kind == EDGES) {
      const float rgba[4] = {item.color[0], item.color[1], item.color[2], 1};
      const uint32_t solid = flats[item.flat & ~FLAT];
      for (uint32_t at = item.first; at < item.first + item.count; ++at)
        raster_segment(segments[(size_t)at * 2], segments[(size_t)at * 2 + 1], item.width, cut,
                       [&](size_t pixel, int, int, int mask, float z, const float* zoff) { apply(pixel, mask, z, zoff, rgba, solid); });
      return;
    }
    if (item.kind == CAP) return;
    for (uint32_t at = item.first; at < item.first + item.count; ++at) {
      const Triangle& tri = triangles[at];
      raster_triangle(tri, item.offset_factor, item.offset_units, cut, [&](size_t pixel, int px, int py, int mask, float z, const float* zoff) {
        // Lit only where a sample passes the depth.
        const float* d = &depth[pixel * samples];
        bool any = false;
        for (int k = 0; k < samples; ++k)
          if ((mask >> k & 1) && z + zoff[k] <= d[k]) any = true;
        if (!any) return;
        float rgba[4];
        shade(tri, px, py, rgba);
        apply(pixel, mask, z, zoff, rgba, blend ? 0 : stored(rgba));
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
  renderer.read(scene, blob, size);
  RENDER_SAY("read", started);
  RENDER_CLOCK(placing);
  renderer.place_all();
  RENDER_SAY("place", placing);
  renderer.background_stored = tone().pack(clamp01(renderer.background[0]), clamp01(renderer.background[1]),
                                           clamp01(renderer.background[2]));
  renderer.draw();
  std::string format = text(scene.get("format"), "rgba");
  RENDER_CLOCK(writing);
  std::string out;
  if (format == "png") {
    out = png(renderer.picture, renderer.width, renderer.height);
  } else if (format == "rgba") {
    out.assign((const char*)renderer.picture.data(), renderer.picture.size() * 4);
  } else {
    throw std::invalid_argument("the scene asks for a picture as " + format + ": rgba or png");
  }
  RENDER_SAY("write", writing);
  RENDER_SAY("all", started);
  return out;
}

}  // namespace vc
