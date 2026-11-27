// exports.hpp: what the mesh exports share (cad's export/mesh.py): each part's tessellation at the engine's one
// tolerance, meshed once per part and read as arrays, and a part's triangles grouped by look.
#pragma once

#include <array>
#include <cstdint>
#include <cstring>
#include <optional>
#include <string>
#include <utility>
#include <vector>

#include "core.hpp"

namespace vc {

// mesh.DEFAULT_COLOR: a part with no colour of its own.
constexpr std::array<double, 4> DEFAULT_COLOR = {0.8, 0.8, 0.8, 1.0};

// A part's XBM2 buffer read as its arrays (mesh_format.Mesh.from_bytes), pointing into the buffer.
struct MeshArrays {
  const float* positions = nullptr;  // nodes x 3
  const float* normals = nullptr;    // nodes x 3
  const uint32_t* indices = nullptr;
  const uint32_t* faces = nullptr;   // faces x 3: ordinal, first index, index count
  uint32_t nodes = 0, nindices = 0, nfaces = 0;
  uint32_t triangles() const { return nindices / 3; }
};

inline MeshArrays mesh_arrays(const std::string& data) {
  MeshArrays m;
  if (data.size() < 80 || data.compare(0, 4, "XBM2") != 0) throw std::runtime_error("not a mesh buffer");
  uint32_t header[20];
  std::memcpy(header, data.data(), 80);
  m.nodes = header[2];
  m.nindices = header[3];
  m.nfaces = header[4];
  const char* base = data.data();
  m.positions = reinterpret_cast<const float*>(base + header[8]);
  m.normals = reinterpret_cast<const float*>(base + header[9]);
  m.indices = reinterpret_cast<const uint32_t*>(base + header[10]);
  m.faces = reinterpret_cast<const uint32_t*>(base + header[11]);
  return m;
}

// A part's mesh at the engine's tolerance, made once and kept on the part (what vc_mesh answers too).
const std::string& part_mesh(Part& part);

// mesh.look_of: a look, the base colour and the part's or face's material (none for a colour alone).
struct Look {
  std::array<double, 4> rgba;
  std::optional<Value> material;
  bool operator==(const Look& o) const {
    return rgba == o.rgba && material.has_value() == o.material.has_value() && (!material || *material == *o.material);
  }
};

// mesh.groups: a part's triangles by look -- its painted faces' colours and materials, its own (or `color`, a
// placement's own colour) for the rest -- in the order their looks first appear; each the indices it draws.
std::vector<std::pair<Look, std::vector<uint32_t>>> look_groups(const MeshArrays& mesh, const Part& part,
                                                               const std::optional<Rgba>& color,
                                                               bool painted = true);

// The document's placements (View.placements): each instance's prototype, its 4x4 column-major matrix, its own
// colour where it has one.
inline const std::vector<Instance>& placements(const Document& doc) { return doc.instances; }

}  // namespace vc
