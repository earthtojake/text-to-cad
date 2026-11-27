// core.hpp: the view core's insides, shared by its parts. Each part mirrors one of cad's Python modules:
//   document.cpp  document.py (Loaded: prototypes, instances, names, colours, keys) and mesh.shape_bytes
//   mesh.cpp      mesh.py's mesh_shape, _extract, _assemble and mesh_format.Mesh.to_bytes (XBM2)
//   topology.cpp  mesh.py's Topology, measured, check, edge_class; kernel/bounds.py
#pragma once

#include <array>
#include <map>
#include <memory>
#include <optional>
#include <set>
#include <string>
#include <vector>

#include <NCollection_IndexedDataMap.hxx>
#include <NCollection_IndexedMap.hxx>
#include <NCollection_List.hxx>
#include <Bnd_Box.hxx>
#include <TopTools_ShapeMapHasher.hxx>
#include <TopoDS_Edge.hxx>
#include <TopoDS_Face.hxx>
#include <TopoDS_Shape.hxx>
#include <TDF_Label.hxx>
#include <TCollection_ExtendedString.hxx>

#include "json.hpp"
#include "value.hpp"

// The facts' rules, version 2 (cad's mesh.FACTS_VERSION): a part's shape read once for all its facts, its box the union
// of its faces' boxes, areas, centroids and volumes integrated adaptively to VC_GPROP_EPS, and a face's checker
// verdict in the whole table only for a face its mesh left without triangles. -DVC_FACTS_V1 measures version 1's rules
// (each answer its own read, the part's own optimal box, fixed Gauss points, every face checked).
#ifndef VC_FACTS_V1
#define VC_SHARED_PART
#define VC_UNION_BOX
#ifndef VC_GPROP_EPS
#define VC_GPROP_EPS 1e-3
#endif
#define VC_CHECK_UNMESHED
#endif

namespace vc {

using ShapeMap = NCollection_IndexedMap<TopoDS_Shape, TopTools_ShapeMapHasher>;
using AncestorMap =
    NCollection_IndexedDataMap<TopoDS_Shape, NCollection_List<TopoDS_Shape>, TopTools_ShapeMapHasher>;
using Rgba = std::array<double, 4>;

// mesh_format: edge classes and the tessellation.
enum { FEATURE = 1, TANGENT = 2, SEAM = 3, BOUNDARY = 5, NONMANIFOLD = 6 };
constexpr double DEVIATION = 0.25;
const double ANGULAR = 28.5 * (3.141592653589793 / 180.0);  // math.radians(28.5), as Python computes it
// mesh_format.TESSELLATION: what a structure names and every part's buffer is made at.
constexpr const char* TESSELLATION = "0.25-28.5";

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
  bool solids_mapped = false;
  ShapeMap solids;
  std::vector<std::optional<Bnd_Box>> face_boxes;  // by ordinal, as face() made them

  explicit Topology(const std::string& data);
  void encode();
  const ShapeMap& solid_map();
  const Bnd_Box& face_box(int ordinal);
  void face(Json& out, int ordinal, bool checked = true);  // a pick's face says its checker's verdict
  void edge(Json& out, int ordinal);
  void vertex(Json& out, int ordinal);
  void groups(Json& out);
  // The whole table; under VC_CHECK_UNMESHED a face says its verdict only if its mesh left it without triangles.
  void elements(Json& out, const std::set<int>& unmeshed);
};

// mesh.measured; `shared` (VC_SHARED_PART) is the part's topology, read once for its facts too.
void measured(Json& out, const std::string& data, Topology* shared = nullptr);

// --- the mesh (mesh.cpp)
// mesh.mesh_shape(data, parallel=False).to_bytes(); `unmeshed`, the faces it left without triangles.
std::string mesh_bytes(const std::string& data, std::set<int>* unmeshed = nullptr);

// --- the document (document.cpp)
struct Part {
  int index = 0;
  // document._label_material: the material cad wrote on the part's label (its bd_materials record, as
  // material_json writes it), and its faces' where theirs differ; frames and the rest of its declarations.
  std::optional<Value> material;
  std::map<int, Value> face_materials;
  std::vector<std::pair<std::string, std::vector<double>>> frames;  // by name, sorted
  std::vector<std::pair<std::string, Value>> declared;              // document.DECLARED, in that order
  TopoDS_Shape shape;  // at the identity
  std::string name;
  std::optional<Rgba> color;
  std::string key;
  std::map<int, std::string> face_names, edge_names, vertex_names;
  std::map<int, Rgba> face_colors;
  std::string bytes;  // shape_bytes(shape), made once on open (the key is its digest)
  std::unique_ptr<Topology> topology;  // made on the first pick (or whole-part answer)
  std::set<int> unmeshed;              // the faces its mesh left without triangles, once meshed
};

struct Instance {
  int prototype = 0;
  std::string path;
  double matrix[16];
  std::optional<Rgba> color;
};

// An occurrence: component indices from the root (document.Loaded.instance_paths, worlds' keys).
using Occurrence = std::vector<int>;

struct Document {
  std::string name;  // the tree root's name (one root), else the name the host gave (the file's stem)
  Value tree;
  std::vector<std::unique_ptr<Part>> parts;
  std::vector<Instance> instances;
  std::optional<std::string> kinematics;  // mechanism.block's JSON, where the document has a mechanism
  std::vector<std::pair<std::string, double>> animations;  // document._animations_listed: name, duration
  Value parameters;                                         // parameters.recorded: a list
  std::optional<Value> closure;                             // the build closure the file holds, if any
};

// `stem` names the document where its file does not (Python's path.stem): an unnamed root, several roots.
std::unique_ptr<Document> open_xbf(const uint8_t* data, size_t size, const std::string& stem);

// mechanism.cpp: mechanism.read then mechanism.block, as JSON; none where the document holds no mechanism.
std::optional<std::string> kinematics(const TDF_Label& main, const std::map<std::string, Occurrence>& occurrences,
                                      const std::vector<Occurrence>& instance_paths,
                                      const std::map<Occurrence, std::array<double, 16>>& worlds);
std::string utf8(const TCollection_ExtendedString& text);
std::string structure(const Document& doc);

}  // namespace vc
