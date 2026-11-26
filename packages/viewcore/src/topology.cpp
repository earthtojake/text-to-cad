// topology.cpp: a part's faces, edges and vertices and what the kernel measures of each (mesh.Topology), how a pick
// grows (Topology.groups), the part as a whole (mesh.measured), the checker's verdict (mesh.check), edge classes
// (mesh.edge_class) and boxes (kernel/bounds.py).
#include <algorithm>
#include <cmath>
#include <map>
#include <set>
#include <stdexcept>

#include <BRepAdaptor_Curve.hxx>
#include <BRepAdaptor_Surface.hxx>
#include <BRepBndLib.hxx>
#include <BRepBuilderAPI_Copy.hxx>
#include <BRepBuilderAPI_MakeFace.hxx>
#include <BRepCheck_Analyzer.hxx>
#include <BRepCheck_Face.hxx>
#include <BRepCheck_Result.hxx>
#include <BRepCheck_Shell.hxx>
#include <BRepCheck_Status.hxx>
#include <BRepCheck_Wire.hxx>
#include <BRepExtrema_DistShapeShape.hxx>
#include <BRepGProp.hxx>
#include <BRepLib.hxx>
#include <BRep_Builder.hxx>
#include <BRep_Tool.hxx>
#include <Bnd_Box.hxx>
#include <GProp_GProps.hxx>
#include <Precision.hxx>
#include <Standard_Failure.hxx>
#include <TopExp.hxx>
#include <TopExp_Explorer.hxx>
#include <TopoDS.hxx>
#include <TopoDS_Compound.hxx>
#include <gp_Circ.hxx>
#include <gp_Cylinder.hxx>
#include <gp_Pln.hxx>
#include <gp_Sphere.hxx>
#include <gp_Torus.hxx>

#include "core.hpp"
#include "profile.hpp"

namespace vc {

namespace {

const char* SURFACE_KINDS[] = {"plane", "cylinder", "cone", "sphere", "torus", "beziersurface", "bsplinesurface",
                               "surfaceofrevolution", "surfaceofextrusion", "offsetsurface", "othersurface"};
const char* CURVE_KINDS[] = {"line", "circle", "ellipse", "hyperbola", "parabola", "beziercurve", "bsplinecurve",
                             "offsetcurve", "othercurve"};
const char* STATUS_NAMES[] = {
    "NoError", "InvalidPointOnCurve", "InvalidPointOnCurveOnSurface", "InvalidPointOnSurface", "No3DCurve",
    "Multiple3DCurve", "Invalid3DCurve", "NoCurveOnSurface", "InvalidCurveOnSurface", "InvalidCurveOnClosedSurface",
    "InvalidSameRangeFlag", "InvalidSameParameterFlag", "InvalidDegeneratedFlag", "FreeEdge", "InvalidMultiConnexity",
    "InvalidRange", "EmptyWire", "RedundantEdge", "SelfIntersectingWire", "NoSurface", "InvalidWire", "RedundantWire",
    "IntersectingWires", "InvalidImbricationOfWires", "EmptyShell", "RedundantFace", "InvalidImbricationOfShells",
    "UnorientableShape", "NotClosed", "NotConnected", "SubshapeNotInShape", "BadOrientation",
    "BadOrientationOfSubshape", "InvalidPolygonOnTriangulation", "InvalidToleranceValue", "EnclosedRegion",
    "CheckFail"};

std::string class_name(int kind) {
  switch (kind) {
    case FEATURE: return "feature";
    case TANGENT: return "tangent";
    case SEAM: return "seam";
    case BOUNDARY: return "boundary";
    case NONMANIFOLD: return "non-manifold";
    default: return "degenerate";
  }
}

void put_point(Json& out, const gp_Pnt& p) { out.point(p.X(), p.Y(), p.Z()); }

void put_box(Json& out, const Bnd_Box& box) {
  if (box.IsVoid()) {
    out.null();
    return;
  }
  gp_Pnt low = box.CornerMin(), high = box.CornerMax();
  out.open().key("min");
  put_point(out, low);
  out.key("max");
  put_point(out, high);
  out.close();
}

// kernel/bounds._support_box: a free-form shape's box from its distances to six exterior planes.
#if !defined(VC_PLAIN_BOX) && !defined(VC_OPTIMAL_BOX)
Bnd_Box support_box(const TopoDS_Shape& shape) {
  VC_SCOPE(box_support_setup);
  Bnd_Box box;
  BRepBndLib::Add(shape, box, false);
  if (box.IsVoid()) return box;
  gp_Pnt low = box.CornerMin(), high = box.CornerMax();
  double limits[6] = {low.X(), low.Y(), low.Z(), high.X(), high.Y(), high.Z()};
  for (double v : limits)
    if (!std::isfinite(v)) throw std::runtime_error("cannot measure a non-finite shape's bounds");
  TopoDS_Shape copied = BRepBuilderAPI_Copy(shape, false, false).Shape();
  TopoDS_Compound boundary;
  BRep_Builder builder;
  builder.MakeCompound(boundary);
  const TopAbs_ShapeEnum kinds[3][2] = {
      {TopAbs_FACE, TopAbs_SHAPE}, {TopAbs_EDGE, TopAbs_FACE}, {TopAbs_VERTEX, TopAbs_EDGE}};
  for (const auto& kind : kinds)
    for (TopExp_Explorer elements(copied, kind[0], kind[1]); elements.More(); elements.Next())
      builder.Add(boundary, elements.Current());
  double center[3], spread = 0;
  for (int axis = 0; axis < 3; ++axis) {
    center[axis] = (limits[axis] + limits[axis + 3]) / 2;
    spread = std::max(spread, limits[axis + 3] - limits[axis]);
  }
  const double reach = std::max(spread, 1.0) * 2;
  double measured[6] = {0, 0, 0, 0, 0, 0};
  for (int axis = 0; axis < 3; ++axis) {
    double direction[3] = {0, 0, 0};
    direction[axis] = 1.0;
    for (int side : {-1, 1}) {
      const int offset = side < 0 ? 0 : 3;
      double origin[3] = {center[0], center[1], center[2]};
      origin[axis] += side * reach;
      gp_Pln plane(gp_Pnt(origin[0], origin[1], origin[2]), gp_Dir(direction[0], direction[1], direction[2]));
      TopoDS_Face face = BRepBuilderAPI_MakeFace(plane, -reach, reach, -reach, reach).Face();
      double value = 0;
      VC_TIMED(box_support_distance, {
        BRepExtrema_DistShapeShape distance(boundary, face, Precision::Confusion());
        if (!distance.IsDone() || distance.InnerSolution() || !std::isfinite(distance.Value()))
          throw std::runtime_error("the kernel could not measure a shape's support plane distance");
        value = distance.Value();
      });
      measured[axis + offset] = origin[axis] - side * value;
    }
  }
  Bnd_Box result;
  result.Update(measured[0], measured[1], measured[2], measured[3], measured[4], measured[5]);
  return result;
}
#endif

// kernel/bounds.optimal_box. Variants: VC_PLAIN_BOX, the kernel's plain box (BRepBndLib::Add, no triangulation: a
// face's tolerance and its surface's control points or analytic bounds); VC_OPTIMAL_BOX, AddOptimal for every shape,
// free-form ones too (no support planes: OCCT #1604 can miss a spline's extremum).
Bnd_Box optimal_box(const TopoDS_Shape& shape) {
  Bnd_Box box;
#if defined(VC_PLAIN_BOX)
  VC_TIMED(box_plain, BRepBndLib::Add(shape, box, false); box.SetGap(0.0));
  return box;
#else
#if !defined(VC_OPTIMAL_BOX)
  bool analytic = true, torus = false;
  VC_TIMED(box_scan, {
    for (TopExp_Explorer faces(shape, TopAbs_FACE); faces.More() && analytic; faces.Next()) {
      GeomAbs_SurfaceType type = BRepAdaptor_Surface(TopoDS::Face(faces.Current()), false).GetType();
      analytic = type == GeomAbs_Plane || type == GeomAbs_Cylinder || type == GeomAbs_Cone ||
                 type == GeomAbs_Sphere || type == GeomAbs_Torus;
      torus = torus || type == GeomAbs_Torus;
    }
  });
  (void)torus;
  if (!analytic) return support_box(shape);
#else
  const bool torus = false;
  (void)torus;
#endif
  VC_TIMED_AS(torus ? box_analytic_torus : box_analytic, BRepBndLib::AddOptimal(shape, box, false, false));
  return box;
#endif
}

// kernel/checks.probed_statuses: what the per-type checkers name of one entity.
std::vector<BRepCheck_Status> probed(const TopoDS_Shape& entity, const TopoDS_Face* face) {
  std::vector<BRepCheck_Status> statuses;
  switch (entity.ShapeType()) {
    case TopAbs_SHELL: {
      occ::handle<BRepCheck_Shell> checker = new BRepCheck_Shell(TopoDS::Shell(entity));
      statuses.push_back(checker->Closed(false));
      statuses.push_back(checker->Orientation(false));
      if (checker->IsUnorientable()) statuses.push_back(BRepCheck_UnorientableShape);
      break;
    }
    case TopAbs_FACE: {
      occ::handle<BRepCheck_Face> checker = new BRepCheck_Face(TopoDS::Face(entity));
      statuses.push_back(checker->IntersectWires(false));
      statuses.push_back(checker->ClassifyWires(false));
      statuses.push_back(checker->OrientationOfWires(false));
      if (checker->IsUnorientable()) statuses.push_back(BRepCheck_UnorientableShape);
      break;
    }
    case TopAbs_WIRE: {
      occ::handle<BRepCheck_Wire> checker = new BRepCheck_Wire(TopoDS::Wire(entity));
      if (face) {
        TopoDS_Edge e1, e2;
        statuses.push_back(checker->SelfIntersect(*face, e1, e2, false));
      }
      statuses.push_back(checker->Closed(false));
      break;
    }
    default:
      break;
  }
  std::vector<BRepCheck_Status> found;
  for (BRepCheck_Status s : statuses)
    if (s != BRepCheck_NoError) found.push_back(s);
  return found;
}

void add_unique(std::vector<std::string>& list, const std::string& text) {
  if (std::find(list.begin(), list.end(), text) == list.end()) list.push_back(text);
}

// mesh._unit
bool unit(double x, double y, double z, double out[3]) {
  double size = std::sqrt(0.0 + x * x + y * y + z * z);
  if (size < 1e-12) return false;
  out[0] = x / size;
  out[1] = y / size;
  out[2] = z / size;
  return true;
}

int root(std::map<int, int>& table, int item) {
  while (table[item] != item) {
    table[item] = table[table[item]];
    item = table[item];
  }
  return item;
}

void named(Json& out, std::map<int, int>& table) {
  std::map<int, int> smallest;
  for (auto& [item, _] : table) {
    int top = root(table, item);
    auto found = smallest.find(top);
    smallest[top] = found == smallest.end() ? item : std::min(found->second, item);
  }
  out.open();
  for (auto& [item, _] : table) out.key(item).integer(smallest[root(table, item)]);
  out.close();
}

}  // namespace

std::vector<TopoDS_Face> unique_faces(const NCollection_List<TopoDS_Shape>& owners) {
  std::vector<TopoDS_Shape> found;
  for (NCollection_List<TopoDS_Shape>::Iterator it(owners); it.More(); it.Next()) {
    bool seen = false;
    for (const TopoDS_Shape& held : found) seen = seen || it.Value().IsSame(held);
    if (!seen) found.push_back(it.Value());
  }
  std::vector<TopoDS_Face> faces;
  for (const TopoDS_Shape& face : found) faces.push_back(TopoDS::Face(face));
  return faces;
}

int edge_class(const TopoDS_Edge& edge, const std::vector<TopoDS_Face>& faces) {
  for (const TopoDS_Face& face : faces)
    if (BRep_Tool::IsClosed(edge, face)) return SEAM;
  if (faces.size() == 1) return BOUNDARY;
  if (faces.size() > 2) return NONMANIFOLD;
  if (faces.size() == 2 && (int)BRep_Tool::Continuity(edge, faces[0], faces[1]) >= (int)GeomAbs_G1) return TANGENT;
  return FEATURE;
}

std::string check(const TopoDS_Face& face) {
  std::optional<BRepCheck_Analyzer> held;
  bool valid = false;
  VC_TIMED(check_analyzer, held.emplace(face); valid = held->IsValid());
  if (valid) return "valid";
  VC_SCOPE(check_probed);
  BRepCheck_Analyzer& analyzer = *held;
  // OCP cannot read a result's status list, so cad names the faults the scalar checkers find (kernel/checks.py).
  std::vector<std::string> found;
  const std::pair<TopAbs_ShapeEnum, const char*> kinds[2] = {{TopAbs_WIRE, "wire"}, {TopAbs_EDGE, "edge"}};
  for (const auto& [kind, label] : kinds) {
    int at = 0;
    for (TopExp_Explorer explorer(face, kind); explorer.More(); explorer.Next()) {
      ++at;
      if (analyzer.Result(explorer.Current()).IsNull()) continue;
      std::vector<std::string> statuses;
      for (BRepCheck_Status s : probed(explorer.Current(), &face)) add_unique(statuses, STATUS_NAMES[s]);
      for (const std::string& text : statuses) found.push_back(std::string(label) + " " + std::to_string(at) + ": " + text);
    }
  }
  if (!analyzer.Result(face).IsNull()) {
    std::vector<std::string> statuses;
    for (BRepCheck_Status s : probed(face, nullptr)) add_unique(statuses, STATUS_NAMES[s]);
    for (const std::string& text : statuses) found.push_back("face: " + text);
  }
  if (found.empty()) return "invalid (kernel diagnostic unavailable)";
  std::vector<std::string> shown;
  for (const std::string& text : found) add_unique(shown, text);
  std::string out;
  for (size_t i = 0; i < shown.size() && i < 6; ++i) out += (i ? "; " : "") + shown[i];
  if (shown.size() > 6) out += "; and " + std::to_string(shown.size() - 6) + " more";
  return out;
}

Topology::Topology(const std::string& data) {
  VC_TIMED(read, shape = read_shape(data));
  VC_TIMED(maps, {
    TopExp::MapShapes(shape, TopAbs_FACE, faces);
    TopExp::MapShapes(shape, TopAbs_EDGE, edges);
    TopExp::MapShapes(shape, TopAbs_VERTEX, vertices);
  });
}

// The regularity encoded on the part and its edges' faces mapped, once (edge(), and groups() under VC_SHARED_PART).
void Topology::encode() {
  if (encoded) return;
  VC_TIMED(edge_encode, BRepLib::EncodeRegularity(shape, 1e-3));  // as the mesher classes edges
  VC_TIMED(edge_ancestors, TopExp::MapShapesAndAncestors(shape, TopAbs_EDGE, TopAbs_FACE, ancestors));
  encoded = true;
}

const ShapeMap& Topology::solid_map() {
  if (!solids_mapped) {
    VC_TIMED(maps, TopExp::MapShapes(shape, TopAbs_SOLID, solids));
    solids_mapped = true;
  }
  return solids;
}

static void in_range(const char* kind, int ordinal, int extent) {
  if (ordinal < 1 || ordinal > extent)
    throw std::out_of_range(std::string("the part has no ") + kind + " " + std::to_string(ordinal) + " (it has " +
                            std::to_string(extent) + ")");
}

void Topology::face(Json& out, int ordinal, bool checked) {
  in_range("face", ordinal, faces.Extent());
  const TopoDS_Face face = TopoDS::Face(faces.FindKey(ordinal));
  std::optional<BRepAdaptor_Surface> surface;
  GeomAbs_SurfaceType type;
  VC_TIMED(face_adaptor, surface.emplace(face, false); type = surface->GetType());
  GProp_GProps props;
#if defined(VC_GPROP_EPS)  // the adaptive integration, to this relative error, in place of the fixed Gauss points
  VC_TIMED_AS(type <= GeomAbs_Torus ? face_gprop : face_gprop_freeform,
              BRepGProp::SurfaceProperties(face, props, VC_GPROP_EPS));
#else
  VC_TIMED_AS(type <= GeomAbs_Torus ? face_gprop : face_gprop_freeform, BRepGProp::SurfaceProperties(face, props));
#endif
#if !defined(VC_NO_FACE_BOX)
  const Bnd_Box& box = face_box(ordinal);
#endif
  out.open().key("kind").str("face").key("ordinal").integer(ordinal).key("area").num(props.Mass());
  out.key("centroid");
  put_point(out, props.CentreOfMass());
  out.key("surface").str(SURFACE_KINDS[type]);
#if !defined(VC_NO_FACE_BOX)
  out.key("box");
  put_box(out, box);
#endif
#if !defined(VC_NO_CHECK)
  if (checked) out.key("check").str(check(face));
#endif
  VC_TIMED(face_adaptor, {
    if (type == GeomAbs_Cylinder) {
      out.key("radius").num(surface->Cylinder().Radius());
    } else if (type == GeomAbs_Sphere) {
      out.key("radius").num(surface->Sphere().Radius());
    } else if (type == GeomAbs_Torus) {
      gp_Torus torus = surface->Torus();
      out.key("majorRadius").num(torus.MajorRadius()).key("minorRadius").num(torus.MinorRadius());
    }
  });
  out.close();
}

void Topology::edge(Json& out, int ordinal) {
  in_range("edge", ordinal, edges.Extent());
  const TopoDS_Edge edge = TopoDS::Edge(edges.FindKey(ordinal));
  encode();
  const bool degenerate = BRep_Tool::Degenerated(edge);
  std::vector<TopoDS_Face> owners;
  VC_TIMED(edge_owners, {
    int at = ancestors.FindIndex(edge);
    if (at) owners = unique_faces(ancestors.FindFromIndex(at));
  });
  int kind = 0;
  VC_TIMED(edge_class, kind = degenerate ? 0 : (owners.empty() ? BOUNDARY : edge_class(edge, owners)));
  GProp_GProps props;
  VC_TIMED(edge_gprop, BRepGProp::LinearProperties(edge, props));
  TopoDS_Vertex ends[2];
  VC_TIMED(edge_ends, ends[0] = TopExp::FirstVertex(edge, true); ends[1] = TopExp::LastVertex(edge, true));
  std::optional<BRepAdaptor_Curve> curve;
  std::string curve_kind;
  VC_TIMED(edge_curve, {
    if (!degenerate) curve.emplace(edge);
    curve_kind = degenerate ? "degenerate" : CURVE_KINDS[curve->GetType()];
  });
  out.open().key("kind").str("edge").key("ordinal").integer(ordinal).key("length").num(props.Mass());
  out.key("curve").str(curve_kind).key("class").str(class_name(kind)).key("classCode").integer(kind);
  out.key("faces").open_list();
  VC_TIMED(edge_owners, for (const TopoDS_Face& face : owners) out.integer(faces.FindIndex(face)));
  out.close_list().key("endpoints").open_list();
  VC_TIMED(edge_ends, {
    for (const TopoDS_Vertex& v : ends)
      if (!v.IsNull()) put_point(out, BRep_Tool::Pnt(v));
    out.close_list().key("vertices").open_list();
    for (const TopoDS_Vertex& v : ends)
      if (!v.IsNull()) out.integer(vertices.FindIndex(v));
  });
  out.close_list();
  if (curve_kind == "circle") {
    VC_TIMED(edge_curve, {
      out.key("radius").num(curve->Circle().Radius());
      out.key("sweepRadians").num(std::abs(curve->LastParameter() - curve->FirstParameter()));
    });
  }
  out.close();
}

void Topology::vertex(Json& out, int ordinal) {
  in_range("vertex", ordinal, vertices.Extent());
  VC_SCOPE(vertex);
  const TopoDS_Vertex vertex = TopoDS::Vertex(vertices.FindKey(ordinal));
  out.open().key("kind").str("vertex").key("ordinal").integer(ordinal).key("position");
  put_point(out, BRep_Tool::Pnt(vertex));
  out.key("tolerance").num(BRep_Tool::Tolerance(vertex)).close();
}

void Topology::groups(Json& out) {
  static const double CHAIN_ALIGNMENT_COS = -std::cos(3.0 * (3.141592653589793 / 180.0));
  VC_SCOPE(groups_chains);
#if defined(VC_SHARED_PART)
  encode();  // the edges' facts encoded and mapped it already: once is enough
  const AncestorMap& owners_of = ancestors;
#else
  VC_TIMED(groups_encode, BRepLib::EncodeRegularity(shape, 1e-3));
  AncestorMap owners_of;
  VC_TIMED(groups_ancestors, TopExp::MapShapesAndAncestors(shape, TopAbs_EDGE, TopAbs_FACE, owners_of));
#endif
  // Each face's solid (the first that holds it): neither grouping crosses solids.
  std::map<int, int> solid_of;
  VC_TIMED(groups_solids, {
    const ShapeMap& solids = solid_map();
    for (int at = 1; at <= solids.Extent(); ++at) {
      ShapeMap held;
      TopExp::MapShapes(solids.FindKey(at), TopAbs_FACE, held);
      for (int i = 1; i <= held.Extent(); ++i) solid_of.emplace(faces.FindIndex(held.FindKey(i)), at);
    }
  });
  auto solid = [&](int face) -> std::optional<int> {
    auto found = solid_of.find(face);
    return found == solid_of.end() ? std::nullopt : std::optional<int>(found->second);
  };
  std::map<int, int> parent;
  for (int ordinal = 1; ordinal <= faces.Extent(); ++ordinal) parent[ordinal] = ordinal;

  std::map<int, std::set<int>> edge_faces;
  std::vector<int> tangent_order;  // the edges with tangents, in ordinal order
  std::map<int, std::array<std::array<double, 3>, 2>> tangents;
  std::map<int, std::array<int, 2>> ends;
  {
  VC_SCOPE(groups_edges);
  for (int ordinal = 1; ordinal <= edges.Extent(); ++ordinal) {
    const TopoDS_Edge edge = TopoDS::Edge(edges.FindKey(ordinal));
    int at = owners_of.FindIndex(edge);
    std::vector<TopoDS_Face> owners;
    if (at) owners = unique_faces(owners_of.FindFromIndex(at));
    std::set<int>& mine = edge_faces[ordinal];
    for (const TopoDS_Face& face : owners) mine.insert(faces.FindIndex(face));
    if (BRep_Tool::Degenerated(edge)) continue;
    if (owners.size() == 2 && edge_class(edge, owners) == TANGENT) {
      int one = *mine.begin(), two = *mine.rbegin();
      if (solid(one) == solid(two)) parent[root(parent, one)] = root(parent, two);
    }
    TopoDS_Vertex first = TopExp::FirstVertex(edge, false), last = TopExp::LastVertex(edge, false);
    if (first.IsNull() || last.IsNull()) continue;
    ends[ordinal] = {vertices.FindIndex(first), vertices.FindIndex(last)};
    if (ends[ordinal][0] == ends[ordinal][1]) continue;
    double into_first[3], into_last[3];
    bool ok_first, ok_last;
    try {
      BRepAdaptor_Curve curve(edge);
      gp_Pnt point;
      gp_Vec vector;
      curve.D1(curve.FirstParameter(), point, vector);
      ok_first = unit(vector.X(), vector.Y(), vector.Z(), into_first);
      curve.D1(curve.LastParameter(), point, vector);
      ok_last = unit(-vector.X(), -vector.Y(), -vector.Z(), into_last);
    } catch (const Standard_Failure&) {
      continue;  // an edge with no tangent is in no chain
    } catch (const std::exception&) {
      continue;
    }
    if (ok_first && ok_last) {
      tangents[ordinal] = {{{into_first[0], into_first[1], into_first[2]}, {into_last[0], into_last[1], into_last[2]}}};
      tangent_order.push_back(ordinal);
    }
  }
  }

  std::map<int, std::vector<std::pair<int, int>>> at_vertex;
  for (int ordinal : tangent_order)
    for (int end = 0; end < 2; ++end) at_vertex[ends[ordinal][end]].push_back({ordinal, end});
  std::map<int, int> solid_of_edge;
  for (auto& [ordinal, owners] : edge_faces) {
    int least = 0;
    bool any = false;
    for (int face : owners) {
      auto s = solid(face);
      int value = s ? *s : 0;
      least = any ? std::min(least, value) : value;
      any = true;
    }
    solid_of_edge[ordinal] = least;
  }
  auto shares_face = [&](int a, int b) {
    for (int face : edge_faces[a])
      if (edge_faces[b].count(face)) return true;
    return false;
  };
  std::map<std::pair<int, int>, std::pair<int, int>> choice;
  for (auto& [vertex, here] : at_vertex) {
    for (auto [ordinal, end] : here) {
      std::vector<std::pair<int, int>> candidates;
      for (auto [other, other_end] : here)
        if (other != ordinal && solid_of_edge[other] == solid_of_edge[ordinal] && shares_face(other, ordinal))
          candidates.push_back({other, other_end});
      if (candidates.size() > 1) {
        const auto& direction = tangents[ordinal][end];
        std::vector<std::pair<int, int>> aligned;
        for (auto [other, other_end] : candidates) {
          const auto& t = tangents[other][other_end];
          double dot = 0.0 + direction[0] * t[0] + direction[1] * t[1] + direction[2] * t[2];
          if (dot < CHAIN_ALIGNMENT_COS) aligned.push_back({other, other_end});
        }
        candidates = aligned;
      }
      if (candidates.size() == 1) choice[{ordinal, end}] = candidates[0];
    }
  }
  std::map<int, int> chains;
  for (int ordinal : tangent_order) chains[ordinal] = ordinal;
  for (auto& [here, there] : choice) {
    auto back = choice.find(there);
    if (back != choice.end() && back->second == here) chains[root(chains, here.first)] = root(chains, there.first);
  }
  out.open().key("faces");
  named(out, parent);
  out.key("edges");
  named(out, chains);
  out.close();
}

void Topology::elements(Json& out, const std::set<int>& unmeshed) {
  out.open().key("faces").open();
  for (int ordinal = 1; ordinal <= faces.Extent(); ++ordinal) {
#if defined(VC_CHECK_UNMESHED)
    face(out.key(ordinal), ordinal, unmeshed.count(ordinal) > 0);
#else
    face(out.key(ordinal), ordinal);
#endif
  }
  out.close().key("edges").open();
  for (int ordinal = 1; ordinal <= edges.Extent(); ++ordinal) edge(out.key(ordinal), ordinal);
  out.close().key("vertices").open();
  for (int ordinal = 1; ordinal <= vertices.Extent(); ++ordinal) vertex(out.key(ordinal), ordinal);
  out.close().key("groups");
  groups(out);
  out.close();
}

// A face's box, once per topology (the part's box is their union under VC_UNION_BOX).
const Bnd_Box& Topology::face_box(int ordinal) {
  if (face_boxes.empty()) face_boxes.resize(faces.Extent() + 1);
  std::optional<Bnd_Box>& held = face_boxes[ordinal];
  if (!held) held = optimal_box(faces.FindKey(ordinal));
  return *held;
}

#if defined(VC_UNION_BOX)
// VC_UNION_BOX: the part's box as the union of its faces' (kept from its elements when they share the topology), and
// of its edges outside faces and vertices outside edges.
static Bnd_Box union_box(Topology& topology) {
  Bnd_Box box;
  for (int ordinal = 1; ordinal <= topology.faces.Extent(); ++ordinal) box.Add(topology.face_box(ordinal));
  for (TopExp_Explorer free(topology.shape, TopAbs_EDGE, TopAbs_FACE); free.More(); free.Next())
    box.Add(optimal_box(free.Current()));
  for (TopExp_Explorer free(topology.shape, TopAbs_VERTEX, TopAbs_EDGE); free.More(); free.Next())
    box.Add(optimal_box(free.Current()));
  return box;
}
#endif

void measured(Json& out, const std::string& data, Topology* shared) {
  std::optional<Topology> own;
  if (!shared) {
#if defined(VC_UNION_BOX)
    own.emplace(data);
    shared = &*own;
#endif
  }
  TopoDS_Shape shape;
  ShapeMap own_solids;
  const ShapeMap* solids = &own_solids;
  if (shared) {
    shape = shared->shape;
    solids = &shared->solid_map();
  } else {
    VC_TIMED(read, shape = read_shape(data));
    VC_TIMED(measure_solids, TopExp::MapShapes(shape, TopAbs_SOLID, own_solids));
  }
  double total = 0.0;
  int inverted = 0;
  VC_TIMED(measure_volume, {
    for (int at = 1; at <= solids->Extent(); ++at) {
      GProp_GProps props;
#if defined(VC_GPROP_EPS)
      BRepGProp::VolumeProperties(solids->FindKey(at), props, VC_GPROP_EPS);
#else
      BRepGProp::VolumeProperties(solids->FindKey(at), props);
#endif
      total += std::abs(props.Mass());
      inverted += props.Mass() < -1e-9;  // inside out; nearer zero, degenerate
    }
  });
#if defined(VC_UNION_BOX)
  Bnd_Box box = union_box(*shared);
#else
  Bnd_Box box = optimal_box(shape);
#endif
  out.open().key("volume").num(total).key("solids").integer(solids->Extent()).key("inverted").integer(inverted);
  out.key("box");
  put_box(out, box);
  out.close();
}

}  // namespace vc
