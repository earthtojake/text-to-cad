// glb.hpp: the GLB writer's parts (glb.cpp: the file, its meshes and materials; glb_motion.cpp: its tree, its
// motions and animations), and the arithmetic they mirror numpy's in: numpy's small matrix products (matmul of 4x4s,
// a row times a 3x3, a 1-D dot, linalg.norm of a 1-D vector) sum as a chain of fused multiply-adds in index order;
// its reductions along an axis (np.sum(..., axis), linalg.norm(..., axis)) are plain sums in index order.
#pragma once

#include <array>
#include <cmath>
#include <map>
#include <optional>
#include <string>
#include <vector>

#include "exports.hpp"

namespace vc {
namespace glb {

// --- a JSON document built in order (Value), written as json.dumps(separators=(",", ":")), ensure_ascii ----------
void dumps(std::string& out, const Value& v);
Value real(double x);
Value integer(long long n);
Value string(const std::string& s);
Value boolean(bool b);
Value object();
Value list();
Value reals(const double* x, size_t n);
Value* at(Value& object_, const std::string& key);
Value& put(Value& object_, const std::string& key, Value value);
Value& setdefault(Value& object_, const std::string& key, Value value);
bool pop(Value& object_, const std::string& key, Value* out);
bool truthy(const Value* v);

// --- numpy's arithmetic -----------------------------------------------------------------------------------------

using Mat4 = std::array<double, 16>;  // row-major: m[row * 4 + column]

inline Mat4 eye() { return {1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1}; }

// A column-major 16 (an instance's or a structure's matrix) as a row-major 4x4 (np.array(m).reshape(4, 4).T).
inline Mat4 from_column(const double* m) {
  Mat4 found;
  for (int r = 0; r < 4; ++r)
    for (int c = 0; c < 4; ++c) found[r * 4 + c] = m[c * 4 + r];
  return found;
}

// a @ b, numpy's 4x4 product.
inline Mat4 matmul(const Mat4& a, const Mat4& b) {
  Mat4 found;
  for (int i = 0; i < 4; ++i)
    for (int j = 0; j < 4; ++j) {
      double s = a[i * 4] * b[j];
      for (int k = 1; k < 4; ++k) s = std::fma(a[i * 4 + k], b[k * 4 + j], s);
      found[i * 4 + j] = s;
    }
  return found;
}

// np.linalg.inv of a 4x4 (glb_motion.cpp: LAPACK's dgesv as numpy's OpenBLAS solves A X = I).
Mat4 inverse(const Mat4& m);

// --- the GLB's tree ---------------------------------------------------------------------------------------------

// motion.Target: a node of the GLB's tree a clip may key.
struct Target {
  int node = 0;
  int parent = -1;  // -1: the root holds it
  std::vector<int> members;
  int instance = -1;  // -1: a sub-assembly
  Mat4 matrix, within;
  std::string name;
};

struct Tree {
  std::vector<Value> nodes;
  std::vector<Target> targets;
};

// glb._tree: the document's tree as glTF nodes (the root first, every node before those under it), and each node but
// the root as a Target. `drawn`: each placement the file draws (instance -> its mesh).
Tree build_tree(const Document& doc, const std::map<int, int>& drawn);

// The GLB's buffer and its views and accessors (glb.rendered's add).
struct Buffers {
  std::string blob;
  std::vector<Value> views;
  std::vector<Value> accessors;

  // `data` the array's bytes, `rows` its first dimension; `target` 0 for none; min/max for a VEC3 with a target.
  inline int add(const std::string& data, size_t rows, int target, const char* kind, int component,
          const float* vec3 = nullptr) {
    while (blob.size() % 4) blob += '\0';
    Value view = object();
    view.keys.emplace_back("buffer", integer(0));
    view.keys.emplace_back("byteOffset", integer((long long)blob.size()));
    view.keys.emplace_back("byteLength", integer((long long)data.size()));
    if (target) view.keys.emplace_back("target", integer(target));
    views.push_back(view);
    blob += data;
    Value accessor = object();
    accessor.keys.emplace_back("bufferView", integer((long long)views.size() - 1));
    accessor.keys.emplace_back("componentType", integer(component));
    accessor.keys.emplace_back("count", integer((long long)rows));
    accessor.keys.emplace_back("type", string(kind));
    if (std::string(kind) == "VEC3" && target) {
      double low[3] = {0, 0, 0}, high[3] = {0, 0, 0};
      if (rows) {
        for (int c = 0; c < 3; ++c) low[c] = high[c] = vec3[c];
        for (size_t r = 1; r < rows; ++r)
          for (int c = 0; c < 3; ++c) {
            float x = vec3[3 * r + c];
            if (x < low[c]) low[c] = x;
            if (x > high[c]) high[c] = x;
          }
      }
      if (rows) {
        accessor.keys.emplace_back("min", reals(low, 3));
        accessor.keys.emplace_back("max", reals(high, 3));
      } else {
        Value zero = list();
        for (int c = 0; c < 3; ++c) zero.items.push_back(integer(0));
        accessor.keys.emplace_back("min", zero);
        accessor.keys.emplace_back("max", zero);
      }
    }
    accessors.push_back(accessor);
    return (int)accessors.size() - 1;
  }
};


// glb._animations: every configuration sequence baked into an animation, then every animation() the document
// records; the nodes they move given translation and rotation in place of their matrices.
std::vector<Value> bake_animations(const Document& doc, const std::map<int, MeshArrays>& held,
                                   const std::vector<int>& shown, Tree& tree, Buffers& buffers);

}  // namespace glb
}  // namespace vc
