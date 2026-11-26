// core.hpp: the view core's insides, shared by its parts. Each part mirrors one of cad's Python modules:
//   document.cpp  document.py (Loaded: prototypes, instances, names, colours, keys) and mesh.shape_bytes
//   mesh.cpp      mesh.py's mesh_shape, _extract, _assemble and mesh_format.Mesh.to_bytes (XBM2)
//   topology.cpp  mesh.py's Topology, measured, check, edge_class; kernel/bounds.py
#pragma once

#include <array>
#include <map>
#include <memory>
#include <optional>
#include <string>
#include <vector>

#include <NCollection_IndexedDataMap.hxx>
#include <NCollection_IndexedMap.hxx>
#include <NCollection_List.hxx>
#include <TopTools_ShapeMapHasher.hxx>
#include <TopoDS_Edge.hxx>
#include <TopoDS_Face.hxx>
#include <TopoDS_Shape.hxx>

#include "json.hpp"

namespace vc {

using ShapeMap = NCollection_IndexedMap<TopoDS_Shape, TopTools_ShapeMapHasher>;
using AncestorMap =
    NCollection_IndexedDataMap<TopoDS_Shape, NCollection_List<TopoDS_Shape>, TopTools_ShapeMapHasher>;
using Rgba = std::array<double, 4>;

// mesh_format: edge classes and the tessellation.
enum { FEATURE = 1, TANGENT = 2, SEAM = 3, BOUNDARY = 5, NONMANIFOLD = 6 };
constexpr double DEVIATION = 0.25;
const double ANGULAR = 28.5 * (3.141592653589793 / 180.0);  // math.radians(28.5), as Python computes it

// --- shapes and their bytes (document.cpp)
std::string write_shape(const TopoDS_Shape& shape);           // mesh._write
std::string shape_bytes(const TopoDS_Shape& shape);           // mesh.shape_bytes(shape, read=True)
TopoDS_Shape read_shape(const std::string& data);             // mesh.read_shape

// --- the B-rep's facts (topology.cpp)
std::vector<TopoDS_Face> unique_faces(const NCollection_List<TopoDS_Shape>& owners);
int edge_class(const TopoDS_Edge& edge, const std::vector<TopoDS_Face>& faces);
std::string check(const TopoDS_Face& face);

struct Topology {
  TopoDS_Shape shape;
  ShapeMap faces, edges, vertices;
  bool encoded = false;  // edge(): regularity encoded and ancestors mapped, once
  AncestorMap ancestors;

  explicit Topology(const std::string& data);
  void face(Json& out, int ordinal);
  void edge(Json& out, int ordinal);
  void vertex(Json& out, int ordinal);
  void groups(Json& out);
  void elements(Json& out);
};

void measured(Json& out, const std::string& data);

// --- the mesh (mesh.cpp)
std::string mesh_bytes(const std::string& data);  // mesh.mesh_shape(data, parallel=False).to_bytes()

// --- the document (document.cpp)
struct Part {
  int index = 0;
  TopoDS_Shape shape;  // at the identity
  std::string name;
  std::optional<Rgba> color;
  std::string key;
  std::map<int, std::string> face_names, edge_names, vertex_names;
  std::map<int, Rgba> face_colors;
  std::string bytes;  // shape_bytes(shape), made once on open (the key is its digest)
  std::unique_ptr<Topology> topology;  // made on the first pick
};

struct Instance {
  int prototype = 0;
  std::string path;
  double matrix[16];
  std::optional<Rgba> color;
};

struct Document {
  std::vector<std::unique_ptr<Part>> parts;
  std::vector<Instance> instances;
};

std::unique_ptr<Document> open_xbf(const uint8_t* data, size_t size);
std::string structure(const Document& doc);

}  // namespace vc
