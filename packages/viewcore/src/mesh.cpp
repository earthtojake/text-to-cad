// mesh.cpp: a part meshed by cad's rule into the XBM2 buffer: mesh.deflection, mesh_shape, _extract, _assemble
// and mesh_format.Mesh.to_bytes. The arrays are those _assemble makes, in its order and with its arithmetic, read
// from the triangulations directly (Python reads them from a BinTools dump only to avoid a loop per node).
#include <algorithm>
#include <cmath>
#include <cstring>
#include <map>
#include <tuple>

#include <BRepBndLib.hxx>
#include <BRepLib.hxx>
#include <BRepLib_ToolTriangulatedShape.hxx>
#include <BRepMesh_IncrementalMesh.hxx>
#include <BRep_Tool.hxx>
#include <Bnd_Box.hxx>
#include <IMeshTools_Parameters.hxx>
#include <Poly_PolygonOnTriangulation.hxx>
#include <Poly_Triangulation.hxx>
#include <TopExp.hxx>
#include <TopLoc_Location.hxx>
#include <TopoDS.hxx>
#include <TopoDS_TShape.hxx>
#include <gp_Trsf.hxx>

#include "core.hpp"
#include "profile.hpp"

namespace vc {

namespace {

struct Transform {
  bool identity = true;
  double m[3][4];
};

Transform transform_of(const TopLoc_Location& location) {
  Transform t;
  if (location.IsIdentity()) return t;
  t.identity = false;
  const gp_Trsf trsf = location.Transformation();
  for (int r = 0; r < 3; ++r)
    for (int c = 0; c < 4; ++c) t.m[r][c] = trsf.Value(r + 1, c + 1);
  return t;
}

// numpy's `points @ T[:, :3].T + T[:, 3]` for one point; `normals @ T[:, :3].T` with translate false. The sum starts
// at +0, as the matrix product's does: a normal's zero keeps the sign numpy gives it.
inline void apply(const Transform& t, const double in[3], double out[3], bool translate) {
  for (int r = 0; r < 3; ++r) {
    double v = 0.0 + in[0] * t.m[r][0] + in[1] * t.m[r][1] + in[2] * t.m[r][2];
    out[r] = translate ? v + t.m[r][3] : v;
  }
}

struct FaceRow {
  int ordinal;
  int triangulation;  // index among the distinct triangulations, -1 for none
  Transform transform;
  bool reversed;
};

struct EdgeRow {
  int ordinal, kind, polygon;  // polygon: index among the distinct polygons, -1 for none
  Transform transform;
};

struct Polygon {
  occ::handle<Poly_PolygonOnTriangulation> polygon;
  int triangulation;
};

void put_u32(std::string& out, uint32_t v) { out.append(reinterpret_cast<const char*>(&v), 4); }
void put_f32(std::string& out, float v) { out.append(reinterpret_cast<const char*>(&v), 4); }

}  // namespace

// mesh.deflection
double deflection(const TopoDS_Shape& shape) {
  Bnd_Box box;
  BRepBndLib::Add(shape, box, false);
  if (box.IsVoid()) return 0.1;
  box.SetGap(0.0);
  gp_Pnt low = box.CornerMin(), high = box.CornerMax();
  double value = ((high.X() - low.X()) + (high.Y() - low.Y()) + (high.Z() - low.Z())) / 300.0 * DEVIATION;
  return std::max(value, 1e-4);
}

std::string mesh_bytes(const std::string& data) {
  TopoDS_Shape shape;
  VC_TIMED(read, shape = read_shape(data));
  double linear = 0;
  VC_TIMED(mesh_deflection, linear = deflection(shape));
  const double angular = ANGULAR;
  IMeshTools_Parameters parameters;
  parameters.Deflection = linear;
  parameters.Angle = angular;
  parameters.Relative = false;
  parameters.InParallel = false;
  parameters.EnableControlSurfaceDeflectionAllSurfaces = true;
  parameters.ForceFaceDeflection = false;
  VC_TIMED(mesh_brepmesh, BRepMesh_IncrementalMesh mesher(shape, parameters));
  VC_PHASES();
  VC_PHASE(mesh_extract);

  // _extract: the faces' triangulations, each distinct one once.
  ShapeMap faces;
  TopExp::MapShapes(shape, TopAbs_FACE, faces);
  std::vector<occ::handle<Poly_Triangulation>> held;
  std::map<const TopoDS_TShape*, int> by_face;
  std::vector<FaceRow> face_rows;
  for (int ordinal = 1; ordinal <= faces.Extent(); ++ordinal) {
    const TopoDS_Face face = TopoDS::Face(faces.FindKey(ordinal));
    TopLoc_Location location;
    const occ::handle<Poly_Triangulation>& triangulation = BRep_Tool::Triangulation(face, location);
    if (triangulation.IsNull() || triangulation->NbTriangles() == 0) {
      face_rows.push_back({ordinal, -1, Transform(), false});
      continue;
    }
    const TopoDS_TShape* tshape = face.TShape().get();
    auto found = by_face.find(tshape);
    int index;
    if (found == by_face.end()) {
      BRepLib_ToolTriangulatedShape::ComputeNormals(face, triangulation);
      index = (int)held.size();
      held.push_back(triangulation);
      by_face[tshape] = index;
    } else {
      index = found->second;
    }
    face_rows.push_back({ordinal, index, transform_of(location), face.Orientation() == TopAbs_REVERSED});
  }

  BRepLib::EncodeRegularity(shape, 1e-3);
  ShapeMap edges;
  TopExp::MapShapes(shape, TopAbs_EDGE, edges);
  AncestorMap ancestors;
  TopExp::MapShapesAndAncestors(shape, TopAbs_EDGE, TopAbs_FACE, ancestors);
  std::map<std::tuple<const TopoDS_TShape*, size_t, int>, int> polygon_keys;
  std::vector<Polygon> polygons;
  std::vector<EdgeRow> edge_rows;
  for (int ordinal = 1; ordinal <= edges.Extent(); ++ordinal) {
    const TopoDS_Edge edge = TopoDS::Edge(edges.FindKey(ordinal));
    if (BRep_Tool::Degenerated(edge)) continue;
    int at = ancestors.FindIndex(edge);
    std::vector<TopoDS_Face> owners;
    if (at) owners = unique_faces(ancestors.FindFromIndex(at));
    int kind = owners.empty() ? BOUNDARY : edge_class(edge, owners);
    occ::handle<Poly_PolygonOnTriangulation> polygon;
    int face_index = -1;
    TopLoc_Location location;
    for (const TopoDS_Face& face : owners) {
      TopLoc_Location here;
      const occ::handle<Poly_Triangulation>& triangulation = BRep_Tool::Triangulation(face, here);
      if (triangulation.IsNull()) continue;
      auto found = by_face.find(face.TShape().get());
      if (found == by_face.end()) continue;
      const occ::handle<Poly_PolygonOnTriangulation>& on = BRep_Tool::PolygonOnTriangulation(edge, triangulation, here);
      if (!on.IsNull()) {
        polygon = on;
        face_index = found->second;
        location = here;
        break;
      }
    }
    if (polygon.IsNull()) {
      edge_rows.push_back({ordinal, kind, -1, Transform()});
      continue;
    }
    // An extrusion's far cap shares its edges' TShapes with the near cap's, moved: the edge's location keys too.
    auto key = std::make_tuple(edge.TShape().get(), edge.Location().HashCode(), face_index);
    auto found = polygon_keys.find(key);
    int index;
    if (found == polygon_keys.end()) {
      index = polygon_keys[key] = (int)polygons.size();
      polygons.push_back({polygon, face_index});
    } else {
      index = found->second;
    }
    edge_rows.push_back({ordinal, kind, index, transform_of(location)});
  }

  ShapeMap vertex_map;
  TopExp::MapShapes(shape, TopAbs_VERTEX, vertex_map);

  VC_PHASE(mesh_assemble);
  // _assemble: the meshed faces' nodes, joined, transformed, in float64.
  std::vector<double> positions, normals;  // 3 per node
  std::vector<int64_t> corners;            // 3 per triangle, into the joined nodes
  std::vector<size_t> face_node_start, face_node_count, face_tri_start, face_tri_count;
  std::vector<bool> face_stored;
  std::vector<uint32_t> face_count(face_rows.size(), 0);
  for (size_t row = 0; row < face_rows.size(); ++row) {
    const FaceRow& face = face_rows[row];
    if (face.triangulation < 0) continue;
    const occ::handle<Poly_Triangulation>& t = held[face.triangulation];
    const int nodes = t->NbNodes(), triangles = t->NbTriangles();
    const bool has = t->HasNormals();
    const size_t base = positions.size() / 3;
    face_node_start.push_back(base);
    face_node_count.push_back(nodes);
    face_tri_start.push_back(corners.size() / 3);
    face_tri_count.push_back(triangles);
    face_stored.push_back(has);
    for (int i = 1; i <= nodes; ++i) {
      gp_Pnt p = t->Node(i);
      double in[3] = {p.X(), p.Y(), p.Z()}, n[3] = {0, 0, 0};
      if (has) {
        NCollection_Vec3<float> v;
        t->Normal(i, v);
        n[0] = v.x(); n[1] = v.y(); n[2] = v.z();
      }
      if (!face.transform.identity) {
        double out[3], nout[3];
        apply(face.transform, in, out, true);
        apply(face.transform, n, nout, false);
        std::memcpy(in, out, sizeof in);
        std::memcpy(n, nout, sizeof n);
      }
      positions.insert(positions.end(), in, in + 3);
      normals.insert(normals.end(), n, n + 3);
    }
    for (int i = 1; i <= triangles; ++i) {
      int a, b, c;
      t->Triangle(i).Get(a, b, c);
      int64_t A = a - 1 + (int64_t)base, B = b - 1 + (int64_t)base, C = c - 1 + (int64_t)base;
      if (face.reversed) std::swap(B, C);
      corners.push_back(A);
      corners.push_back(B);
      corners.push_back(C);
    }
    face_count[row] = (uint32_t)triangles * 3;
  }
  const size_t ntri = corners.size() / 3, nnodes = positions.size() / 3;
  std::vector<double> geometric(ntri * 3);
  for (size_t k = 0; k < ntri; ++k) {
    const double* a = &positions[corners[3 * k] * 3];
    const double* b = &positions[corners[3 * k + 1] * 3];
    const double* c = &positions[corners[3 * k + 2] * 3];
    double u[3] = {b[0] - a[0], b[1] - a[1], b[2] - a[2]}, v[3] = {c[0] - a[0], c[1] - a[1], c[2] - a[2]};
    geometric[3 * k] = u[1] * v[2] - u[2] * v[1];
    geometric[3 * k + 1] = u[2] * v[0] - u[0] * v[2];
    geometric[3 * k + 2] = u[0] * v[1] - u[1] * v[0];
  }
  // A triangulation is shared by both orientations of its face: its normals point whichever way the first one to
  // compute them faced; a face whose stored normals face away from its triangles has them turned.
  std::vector<bool> flip(face_stored.size(), false);
  bool all_stored = true;
  for (size_t f = 0; f < face_stored.size(); ++f) {
    all_stored = all_stored && face_stored[f];
    double facing = 0;
    for (size_t k = face_tri_start[f]; k < face_tri_start[f] + face_tri_count[f]; ++k) {
      const double* n = &normals[corners[3 * k] * 3];
      const double* g = &geometric[3 * k];
      facing += g[0] * n[0] + g[1] * n[1] + g[2] * n[2];
    }
    flip[f] = face_stored[f] && facing < 0;
  }
  for (size_t f = 0; f < face_stored.size(); ++f) {
    if (!flip[f]) continue;
    for (size_t i = face_node_start[f]; i < face_node_start[f] + face_node_count[f]; ++i)
      for (int c = 0; c < 3; ++c) normals[3 * i + c] *= -1;
  }
  if (!all_stored) {
    // Faces without stored normals: each node's, the area-weighted sum of its triangles' (np.add.at, by column).
    std::vector<bool> mine(ntri, false), computed(nnodes, false);
    for (size_t f = 0; f < face_stored.size(); ++f) {
      if (face_stored[f]) continue;
      for (size_t k = face_tri_start[f]; k < face_tri_start[f] + face_tri_count[f]; ++k) mine[k] = true;
      for (size_t i = face_node_start[f]; i < face_node_start[f] + face_node_count[f]; ++i) computed[i] = true;
    }
    std::vector<double> summed(nnodes * 3, 0.0);
    for (int column = 0; column < 3; ++column)
      for (size_t k = 0; k < ntri; ++k)
        if (mine[k])
          for (int c = 0; c < 3; ++c) summed[corners[3 * k + column] * 3 + c] += geometric[3 * k + c];
    for (size_t i = 0; i < nnodes; ++i) {
      if (!computed[i]) continue;
      const double* s = &summed[3 * i];
      double length = std::sqrt(s[0] * s[0] + s[1] * s[1] + s[2] * s[2]);
      double d = length > 0 ? length : 1;
      for (int c = 0; c < 3; ++c) normals[3 * i + c] = s[c] / d;
    }
  }

  // The edges' polylines, from the triangulation each polygon is on, at the edge's face's placement.
  std::vector<float> lines;
  std::vector<uint32_t> edge_table;
  uint32_t point_base = 0;
  for (const EdgeRow& row : edge_rows) {
    if (row.polygon < 0) {
      edge_table.insert(edge_table.end(), {(uint32_t)row.ordinal, point_base, 0u, (uint32_t)row.kind});
      continue;
    }
    const Polygon& p = polygons[row.polygon];
    const occ::handle<Poly_Triangulation>& t = held[p.triangulation];
    const int n = p.polygon->NbNodes();
    for (int i = 1; i <= n; ++i) {
      gp_Pnt point = t->Node(p.polygon->Node(i));
      double in[3] = {point.X(), point.Y(), point.Z()}, out[3];
      if (!row.transform.identity) {
        apply(row.transform, in, out, true);
        std::memcpy(in, out, sizeof in);
      }
      for (double v : in) lines.push_back((float)v);
    }
    edge_table.insert(edge_table.end(), {(uint32_t)row.ordinal, point_base, (uint32_t)n, (uint32_t)row.kind});
    point_base += n;
  }

  // mesh_format.Mesh.to_bytes: the 80-byte header, then the seven arrays.
  const uint32_t nfaces = (uint32_t)face_rows.size(), nedges = (uint32_t)edge_rows.size();
  const uint32_t npoints = (uint32_t)(lines.size() / 3), nvertices = (uint32_t)vertex_map.Extent();
  const uint32_t sizes[7] = {(uint32_t)nnodes * 12, (uint32_t)nnodes * 12, (uint32_t)ntri * 12, nfaces * 12,
                             nedges * 16, npoints * 12, nvertices * 16};
  std::string out;
  out.reserve(80 + sizes[0] + sizes[1] + sizes[2] + sizes[3] + sizes[4] + sizes[5] + sizes[6]);
  out.append("XBM2", 4);
  put_u32(out, 2);
  for (uint32_t v : {(uint32_t)nnodes, (uint32_t)ntri * 3, nfaces, nedges, npoints, nvertices}) put_u32(out, v);
  uint32_t at = 80;
  for (uint32_t s : sizes) {
    put_u32(out, at);
    at += s;
  }
  put_f32(out, (float)linear);
  put_f32(out, (float)angular);
  for (int i = 0; i < 3; ++i) put_u32(out, 0);
  for (double v : positions) put_f32(out, (float)v);
  for (double v : normals) put_f32(out, (float)v);
  for (int64_t c : corners) put_u32(out, (uint32_t)c);
  uint32_t first = 0;
  for (size_t row = 0; row < face_rows.size(); ++row) {
    put_u32(out, (uint32_t)face_rows[row].ordinal);
    put_u32(out, first);
    put_u32(out, face_count[row]);
    first += face_count[row];
  }
  for (uint32_t v : edge_table) put_u32(out, v);
  for (float v : lines) put_f32(out, v);
  for (int ordinal = 1; ordinal <= vertex_map.Extent(); ++ordinal) {
    gp_Pnt p = BRep_Tool::Pnt(TopoDS::Vertex(vertex_map.FindKey(ordinal)));
    put_f32(out, (float)ordinal);
    put_f32(out, (float)p.X());
    put_f32(out, (float)p.Y());
    put_f32(out, (float)p.Z());
  }
  return out;
}

}  // namespace vc
