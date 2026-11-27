// document.cpp: an .xbf read as document.Loaded reads it (its prototypes, instances, names, colours and keys),
// and a part's canonical shape bytes (mesh.shape_bytes, mesh.read_shape).
#include <algorithm>
#include <set>
#include <sstream>
#include <stdexcept>

#include <BinTools.hxx>
#include <BinXCAFDrivers.hxx>
#include <BinXCAFDrivers_DocumentRetrievalDriver.hxx>
#include <Message_ProgressRange.hxx>
#include <PCDM_ReadWriter.hxx>
#include <Quantity_ColorRGBA.hxx>
#include <Standard_GUID.hxx>
#include <Storage_Data.hxx>
#include <TCollection_AsciiString.hxx>
#include <TCollection_ExtendedString.hxx>
#include <TDF_Label.hxx>
#include <TDF_Tool.hxx>
#include <TDataStd_AsciiString.hxx>
#include <TDataStd_Name.hxx>
#include <TDataStd_NamedData.hxx>
#include <TDataStd_TreeNode.hxx>
#include <XCAFDoc.hxx>
#include <XCAFDoc_Material.hxx>
#include <TDocStd_Document.hxx>
#include <TopAbs_ShapeEnum.hxx>
#include <TopExp.hxx>
#include <TopLoc_Location.hxx>
#include <TopoDS_TShape.hxx>
#include <XCAFApp_Application.hxx>
#include <XCAFDoc_ColorTool.hxx>
#include <XCAFDoc_DocumentTool.hxx>
#include <XCAFDoc_ShapeTool.hxx>
#include <gp_Trsf.hxx>

#include "blake2b.hpp"
#include "core.hpp"
#include "json.hpp"

namespace vc {

// --- shape bytes ------------------------------------------------------------------------------

std::string write_shape(const TopoDS_Shape& shape) {
  std::ostringstream stream(std::ios::out | std::ios::binary);
  BinTools::Write(shape.Located(TopLoc_Location()), stream, false, false, BinTools_FormatVersion_VERSION_4);
  return stream.str();
}

std::string shape_bytes(const TopoDS_Shape& shape) {
  // mesh._settled: every sub-shape's bookkeeping flags at (Free, Modified, Checked, Locked) = (1, 1, 0, 0) while
  // written, set back after.
  ShapeMap mapped;
  TopExp::MapShapes(shape, mapped);
  struct Held { occ::handle<TopoDS_TShape> tshape; bool free, modified, checked, locked; };
  std::vector<Held> changed;
  for (int at = 1; at <= mapped.Extent(); ++at) {
    const occ::handle<TopoDS_TShape>& t = mapped.FindKey(at).TShape();
    Held held{t, t->Free(), t->Modified(), t->Checked(), t->Locked()};
    if (!(held.free && held.modified && !held.checked && !held.locked)) {
      changed.push_back(held);
      t->Free(true);
      t->Modified(true);
      t->Checked(false);
      t->Locked(false);
    }
  }
  auto restore = [&]() {
    for (const Held& held : changed) {
      held.tshape->Free(held.free);
      held.tshape->Modified(held.modified);
      held.tshape->Checked(held.checked);
      held.tshape->Locked(held.locked);
    }
  };
  try {
    std::string data = write_shape(shape);
    restore();
    return data;
  } catch (...) {
    restore();
    throw;
  }
}

TopoDS_Shape read_shape(const std::string& data) {
  std::istringstream stream(data, std::ios::in | std::ios::binary);
  TopoDS_Shape shape;
  BinTools::Read(shape, stream);
  return shape;
}

// --- labels -----------------------------------------------------------------------------------

std::string utf8(const TCollection_ExtendedString& text) {
  std::string out;
  const char16_t* s = text.ToExtString();
  for (int i = 0; i < text.Length(); ++i) {
    uint32_t c = s[i];
    if (c >= 0xD800 && c < 0xDC00 && i + 1 < text.Length() && s[i + 1] >= 0xDC00 && s[i + 1] < 0xE000) {
      c = 0x10000 + ((c - 0xD800) << 10) + (s[i + 1] - 0xDC00);
      ++i;
    }
    if (c < 0x80) {
      out += (char)c;
    } else if (c < 0x800) {
      out += (char)(0xC0 | (c >> 6));
      out += (char)(0x80 | (c & 63));
    } else if (c < 0x10000) {
      out += (char)(0xE0 | (c >> 12));
      out += (char)(0x80 | ((c >> 6) & 63));
      out += (char)(0x80 | (c & 63));
    } else {
      out += (char)(0xF0 | (c >> 18));
      out += (char)(0x80 | ((c >> 12) & 63));
      out += (char)(0x80 | ((c >> 6) & 63));
      out += (char)(0x80 | (c & 63));
    }
  }
  return out;
}

namespace {

const char* KEY_GUID = "c8f2d4a6-1b3e-4f5a-9c7d-2e8b6a4f0d13";
const char* CLOSURE_GUID = "2f6c9d1e-8a43-4b7e-b5d0-7e1a3c9f4b62";
const char* ANIMATIONS_GUID = "196117b9-7763-467d-8c37-7f838602e8a5";
const char* DECLARATIONS_GUID = "8d3b6f2a-4c71-4e9b-a5d8-1f0c7e2b9a64";
const char* PARAMETERS_GUID = "5b0e7c93-2f4d-4a68-9d31-c6a8e04f7b25";
// document.DECLARED: what a part declares beside its frames, in the structure's order.
const char* DECLARED[] = {"body", "drives", "mass", "pointMasses", "free", "link"};
// parameters._RECORDED: what a recorded parameter says.
const char* RECORDED[] = {"name", "value", "kind", "min", "max", "step", "unit"};
const int MAX_OCCURRENCES = 250000;
const int MAX_ASSEMBLY_DEPTH = 64;

std::string entry_of(const TDF_Label& label) {
  TCollection_AsciiString text;
  TDF_Tool::Entry(label, text);
  return text.ToCString();
}

std::string label_name(const TDF_Label& label) {
  occ::handle<TDataStd_Name> found;
  if (label.FindAttribute(TDataStd_Name::GetID(), found)) return utf8(found->Get());
  return "";
}

std::optional<std::string> label_text(const TDF_Label& label, const char* guid) {
  occ::handle<TDataStd_AsciiString> found;
  if (label.FindAttribute(Standard_GUID(guid), found)) return std::string(found->Get().ToCString());
  return std::nullopt;
}

// document._label_color: linear RGBA, surface colour first, each channel rounded to 6 places.
std::optional<Rgba> label_color(const TDF_Label& label) {
  Quantity_ColorRGBA rgba;
  for (XCAFDoc_ColorType kind : {XCAFDoc_ColorSurf, XCAFDoc_ColorGen}) {
    if (XCAFDoc_ColorTool::GetColor(label, kind, rgba)) {
      const Quantity_Color& rgb = rgba.GetRGB();
      return Rgba{round6(rgb.Red()), round6(rgb.Green()), round6(rgb.Blue()), round6(rgba.Alpha())};
    }
  }
  return std::nullopt;
}

// document._held_colors: faces coloured through the solids or shells that hold them.
std::optional<Rgba> held_colors(const ShapeMap& faces, const std::vector<std::pair<TopoDS_Shape, Rgba>>& holding,
                                std::optional<Rgba> color, std::map<int, Rgba>& face_colors) {
  struct Held { ShapeMap inner; int kind; Rgba rgba; };
  std::vector<Held> held;
  for (const auto& [shape, rgba] : holding) {
    Held h;
    TopExp::MapShapes(shape, TopAbs_FACE, h.inner);
    h.kind = (int)shape.ShapeType();
    h.rgba = rgba;
    held.push_back(std::move(h));
  }
  std::vector<size_t> order(held.size());
  for (size_t i = 0; i < order.size(); ++i) order[i] = i;
  std::stable_sort(order.begin(), order.end(), [&](size_t a, size_t b) {
    int ea = -held[a].inner.Extent(), eb = -held[b].inner.Extent();
    return ea != eb ? ea < eb : held[a].kind < held[b].kind;
  });
  std::vector<std::pair<int, Rgba>> given;  // insertion order, as a dict keeps it
  std::map<int, size_t> where;
  for (size_t i : order) {
    for (int at = 1; at <= held[i].inner.Extent(); ++at) {
      int ordinal = faces.FindIndex(held[i].inner.FindKey(at));
      if (!ordinal) continue;
      auto found = where.find(ordinal);
      if (found == where.end()) {
        where[ordinal] = given.size();
        given.emplace_back(ordinal, held[i].rgba);
      } else {
        given[found->second].second = held[i].rgba;
      }
    }
  }
  if ((int)given.size() == faces.Extent() && !given.empty()) {
    bool one = true;
    for (const auto& g : given) one = one && g.second == given[0].second;
    if (one) return given[0].second;
  }
  for (const auto& [ordinal, rgba] : given) {
    if (!face_colors.count(ordinal) && (!color || rgba != *color)) face_colors[ordinal] = rgba;
  }
  return color;
}

// document._label_material, for a document cad wrote: the material its label refers to (XCAF's material reference
// tree node), as the bd_materials record cad keeps beside XCAF's subset on the material's label (_write_extra), read
// back as material_json writes it (that record is material_key: material_json's own JSON). A material with no such
// record (a file cad did not write) is not read: none.
std::optional<Value> label_material(const TDF_Label& label) {
  occ::handle<TDataStd_TreeNode> node;
  if (!label.FindAttribute(XCAFDoc::MaterialRefGUID(), node) || !node->HasFather()) return std::nullopt;
  TDF_Label held = node->Father()->Label();
  occ::handle<XCAFDoc_Material> physical;
  if (!held.FindAttribute(XCAFDoc_Material::GetID(), physical)) return std::nullopt;
  occ::handle<TDataStd_NamedData> data;
  TCollection_ExtendedString key("bd_materials");
  if (!held.FindAttribute(TDataStd_NamedData::GetID(), data)) return std::nullopt;
  data->LoadDeferredData();
  if (!data->HasString(key)) return std::nullopt;
  return Value::parse(utf8(data->GetString(key)));
}

// document._held_materials: faces given a material through the solids or shells that hold them.
std::optional<Value> held_materials(const ShapeMap& faces, const std::vector<std::pair<TopoDS_Shape, Value>>& holding,
                                    std::optional<Value> material, std::map<int, Value>& face_materials) {
  struct Held { ShapeMap inner; int kind; const Value* given; };
  std::vector<Held> held;
  for (const auto& [shape, given] : holding) {
    Held h;
    TopExp::MapShapes(shape, TopAbs_FACE, h.inner);
    h.kind = (int)shape.ShapeType();
    h.given = &given;
    held.push_back(std::move(h));
  }
  std::vector<size_t> order(held.size());
  for (size_t i = 0; i < order.size(); ++i) order[i] = i;
  std::stable_sort(order.begin(), order.end(), [&](size_t a, size_t b) {
    int ea = -held[a].inner.Extent(), eb = -held[b].inner.Extent();
    return ea != eb ? ea < eb : held[a].kind < held[b].kind;
  });
  std::vector<std::pair<int, const Value*>> by_face;  // insertion order, as a dict keeps it
  std::map<int, size_t> where;
  for (size_t i : order) {
    for (int at = 1; at <= held[i].inner.Extent(); ++at) {
      int ordinal = faces.FindIndex(held[i].inner.FindKey(at));
      if (!ordinal) continue;
      auto found = where.find(ordinal);
      if (found == where.end()) {
        where[ordinal] = by_face.size();
        by_face.emplace_back(ordinal, held[i].given);
      } else {
        by_face[found->second].second = held[i].given;
      }
    }
  }
  if ((int)by_face.size() == faces.Extent() && !by_face.empty()) {
    bool one = true;
    for (const auto& b : by_face) one = one && *b.second == *by_face[0].second;
    if (one) {
      const Value& appearance = *by_face[0].second;
      if (!material) return appearance;
      // FinishedMaterial(material.material, pbr=appearance.pbr): the part's physics in the held look, no process.
      Value made;
      made.kind = Value::OBJECT;
      for (const char* name : {"type", "material"})
        if (const Value* v = material->get(name)) made.keys.emplace_back(name, *v);
      if (const Value* v = appearance.get("pbr")) made.keys.emplace_back("pbr", *v);
      return made;
    }
  }
  for (const auto& [ordinal, given] : by_face) {
    if (!face_materials.count(ordinal) && (!material || *given != *material)) face_materials[ordinal] = *given;
  }
  return material;
}

// document.declarations_from: a part's frames (16 floats each) and the rest it declares (DECLARED).
void read_declarations(Part& part, const std::optional<std::string>& text) {
  if (!text || text->empty()) return;
  Value value = Value::parse(*text);
  if (const Value* frames = value.get("frames")) {
    for (const auto& [name, values] : frames->keys) {
      std::vector<double> found;
      for (const Value& item : values.items) found.push_back(item.number());
      part.frames.emplace_back(name, found);
    }
    std::sort(part.frames.begin(), part.frames.end(),
              [](const auto& a, const auto& b) { return a.first < b.first; });
  }
  for (const char* name : DECLARED)
    if (const Value* v = value.get(name)) part.declared.emplace_back(name, *v);
}

// document._prototype.
std::unique_ptr<Part> make_part(int index, const TDF_Label& label, const TopoDS_Shape& shape) {
  auto part = std::make_unique<Part>();
  part->index = index;
  part->shape = shape.Located(TopLoc_Location());
  part->bytes = shape_bytes(part->shape);
  part->key = blake2b_hex(part->bytes.data(), part->bytes.size());
  part->color = label_color(label);
  part->material = label_material(label);
  NCollection_Sequence<TDF_Label> subs;
  XCAFDoc_ShapeTool::GetSubShapes(label, subs);
  if (subs.Length()) {
    ShapeMap faces, edges, vertices;
    bool vertices_mapped = false;
    TopExp::MapShapes(shape, TopAbs_FACE, faces);
    TopExp::MapShapes(shape, TopAbs_EDGE, edges);
    std::vector<std::pair<TopoDS_Shape, Rgba>> holding;
    std::vector<std::pair<TopoDS_Shape, Value>> held_material;
    for (int at = 1; at <= subs.Length(); ++at) {
      const TDF_Label& sub = subs.Value(at);
      TopoDS_Shape held = XCAFDoc_ShapeTool::GetShape(sub);
      if (held.IsNull()) continue;
      TopAbs_ShapeEnum kind = held.ShapeType();
      if (kind != TopAbs_FACE && kind != TopAbs_EDGE && kind != TopAbs_VERTEX) {
        if (auto rgba = label_color(sub)) holding.emplace_back(held, *rgba);
        if (auto material = label_material(sub)) held_material.emplace_back(held, *material);
      } else if (kind == TopAbs_FACE) {
        int ordinal = faces.FindIndex(held);
        if (ordinal) {
          std::string name = label_name(sub);
          if (!name.empty()) part->face_names[ordinal] = name;
          if (auto rgba = label_color(sub)) part->face_colors[ordinal] = *rgba;
          if (auto material = label_material(sub)) part->face_materials[ordinal] = *material;
        }
      } else if (kind == TopAbs_EDGE) {
        int ordinal = edges.FindIndex(held);
        std::string name = ordinal ? label_name(sub) : "";
        if (!name.empty()) part->edge_names[ordinal] = name;
      } else {
        if (!vertices_mapped) {
          TopExp::MapShapes(shape, TopAbs_VERTEX, vertices);
          vertices_mapped = true;
        }
        int ordinal = vertices.FindIndex(held);
        std::string name = ordinal ? label_name(sub) : "";
        if (!name.empty()) part->vertex_names[ordinal] = name;
      }
    }
    if (!holding.empty()) part->color = held_colors(faces, holding, part->color, part->face_colors);
    if (!held_material.empty())
      part->material = held_materials(faces, held_material, part->material, part->face_materials);
  }
  std::string name = label_name(label);
  part->name = name.empty() ? "part" + std::to_string(index + 1) : name;
  read_declarations(*part, label_text(label, DECLARATIONS_GUID));
  return part;
}

// document._matrix: 4x4, column-major.
std::array<double, 16> matrix_of(const TopLoc_Location& location) {
  std::array<double, 16> found;
  const gp_Trsf transform = location.Transformation();
  for (int column = 0; column < 4; ++column)
    for (int row = 0; row < 4; ++row)
      found[column * 4 + row] = row < 3 ? transform.Value(row + 1, column + 1) : (column == 3 ? 1.0 : 0.0);
  return found;
}

Value string_value(const std::string& text) {
  Value v;
  v.kind = Value::STRING;
  v.text = text;
  return v;
}

Value integer_value(long long n) {
  Value v;
  v.kind = Value::INT;
  v.text = std::to_string(n);
  return v;
}

class Walker {
 public:
  Document& doc;
  std::map<std::string, int> by_entry;
  std::map<int, std::string> claims;
  int counted = 0;
  // document.Loaded's instance_paths, worlds and occurrences: what its mechanism is read by.
  std::vector<Occurrence> instance_paths;
  std::map<Occurrence, std::array<double, 16>> worlds;
  std::map<std::string, Occurrence> occurrences;

  explicit Walker(Document& d) : doc(d) {}

  // document.Loaded._walk's visit: the tree's node for the label.
  Value visit(const TDF_Label& label, const TopLoc_Location& location, const std::vector<std::string>& path,
              std::optional<Rgba> inherited, const std::string& name, const Occurrence& occurrence,
              const std::vector<std::string>& entries, const std::set<std::string>& ancestors) {
    if (++counted > MAX_OCCURRENCES) throw std::runtime_error("the assembly names too many occurrences");
    if ((int)occurrence.size() > MAX_ASSEMBLY_DEPTH) throw std::runtime_error("the assembly is too deep");
    std::optional<Rgba> color = label_color(label);
    if (!color) color = inherited;
    worlds[occurrence] = matrix_of(location);
    std::string joined;
    for (size_t i = 0; i < entries.size(); ++i) joined += (i ? "/" : "") + entries[i];
    occurrences[joined] = occurrence;
    Value node;
    node.kind = Value::OBJECT;
    node.keys.emplace_back("name", string_value(name));
    if (XCAFDoc_ShapeTool::IsAssembly(label)) {
      std::string own = entry_of(label);
      if (ancestors.count(own)) throw std::runtime_error("an assembly contains itself");
      std::set<std::string> inner = ancestors;
      inner.insert(own);
      Value list;
      list.kind = Value::LIST;
      NCollection_Sequence<TDF_Label> components;
      XCAFDoc_ShapeTool::GetComponents(label, components, false);
      for (int at = 1; at <= components.Length(); ++at) {
        const TDF_Label& component = components.Value(at);
        TDF_Label referred;
        XCAFDoc_ShapeTool::GetReferredShape(component, referred);
        TopLoc_Location placed = location.Multiplied(XCAFDoc_ShapeTool::GetLocation(component));
        std::string child_name = label_name(component);
        if (child_name.empty()) child_name = label_name(referred);
        if (child_name.empty()) child_name = name + "." + std::to_string(at);
        std::optional<Rgba> child_color = label_color(component);
        if (!child_color) child_color = color;
        std::vector<std::string> child_path = path;
        child_path.push_back(child_name);
        Occurrence child = occurrence;
        child.push_back(at - 1);
        std::vector<std::string> child_entries = entries;
        child_entries.push_back(entry_of(component));
        list.items.push_back(visit(referred, placed, child_path, child_color, child_name, child, child_entries, inner));
      }
      node.keys.emplace_back("children", std::move(list));
      return node;
    }
    TopoDS_Shape shape = XCAFDoc_ShapeTool::GetShape(label);
    std::string entry = entry_of(label);
    auto found = by_entry.find(entry);
    int index;
    if (found == by_entry.end()) {
      index = by_entry[entry] = (int)doc.parts.size();
      doc.parts.push_back(make_part(index, label, shape));
      if (auto claim = label_text(label, KEY_GUID)) claims[index] = *claim;
    } else {
      index = found->second;
    }
    TopLoc_Location placed = location.Multiplied(shape.Location());
    Instance instance;
    instance.prototype = index;
    for (size_t i = 0; i < path.size(); ++i) instance.path += (i ? "/" : "") + path[i];
    std::array<double, 16> matrix = matrix_of(placed);
    std::copy(matrix.begin(), matrix.end(), instance.matrix);
    const Part& prototype = *doc.parts[index];
    if (color != prototype.color) instance.color = color;
    doc.instances.push_back(instance);
    instance_paths.push_back(occurrence);
    node.keys.emplace_back("prototype", integer_value(index));
    node.keys.emplace_back("instance", integer_value((long long)doc.instances.size() - 1));
    return node;
  }

  // document._checked_keys: a part keeps the key its file names only where every part naming it makes it again.
  void checked_keys() {
    std::map<std::string, std::vector<Part*>> named;
    for (auto& part : doc.parts) {
      auto claim = claims.find(part->index);
      if (claim != claims.end() && !claim->second.empty()) named[claim->second].push_back(part.get());
    }
    for (auto& [claim, group] : named) {
      std::string key = claim;
      bool held = true;
      for (Part* part : group) held = held && part->key == claim;
      if (!held) {
        std::vector<std::string> keys;
        for (Part* part : group) keys.push_back(part->key);
        std::sort(keys.begin(), keys.end());
        std::string made = std::string("named") + '\0' + claim;
        for (const std::string& k : keys) made += '\0' + k;
        key = blake2b_hex(made.data(), made.size());
      }
      for (Part* part : group) part->key = key;
    }
  }
};

occ::handle<TDocStd_Application> application() {
  static occ::handle<XCAFApp_Application> app;
  if (app.IsNull()) {
    app = XCAFApp_Application::GetApplication();
    BinXCAFDrivers::DefineFormat(app);
  }
  return app;
}

}  // namespace

std::unique_ptr<Document> open_xbf(const uint8_t* data, size_t size, const std::string& given_stem) {
  occ::handle<TDocStd_Application> app = application();
  occ::handle<TDocStd_Document> xdoc = new TDocStd_Document(TCollection_ExtendedString("BinXCAF"));
  {
    std::istringstream stream(std::string(reinterpret_cast<const char*>(data), size),
                              std::ios::in | std::ios::binary);
    occ::handle<Storage_Data> header;
    PCDM_ReadWriter::FileFormat(stream, header);
    occ::handle<BinXCAFDrivers_DocumentRetrievalDriver> driver = new BinXCAFDrivers_DocumentRetrievalDriver();
    driver->Read(stream, header, xdoc, app, occ::handle<PCDM_ReaderFilter>(), Message_ProgressRange());
    static const char* names[] = {
        "OK", "NoDriver", "UnknownFileDriver", "OpenError", "NoVersion", "NoSchema", "NoDocument",
        "ExtensionFailure", "WrongStreamMode", "FormatFailure", "TypeFailure", "TypeNotFoundInSchema",
        "UnrecognizedFileFormat", "MakeFailure", "PermissionDenied", "DriverFailure", "AlreadyRetrievedAndModified",
        "AlreadyRetrieved", "UnknownDocument", "WrongResource", "ReaderException", "NoModel", "UserBreak"};
    const int status = (int)driver->GetStatus();
    if (status != PCDM_RS_OK)
      throw std::runtime_error(std::string("cannot read the xbf: PCDM_RS_") +
                               (status >= 0 && status < 23 ? names[status] : std::to_string(status).c_str()));
  }
  auto doc = std::make_unique<Document>();
  const std::string stem = given_stem.empty() ? "document" : given_stem;
  Walker walker(*doc);
  occ::handle<XCAFDoc_ShapeTool> shapes = XCAFDoc_DocumentTool::ShapeTool(xdoc->Main());
  NCollection_Sequence<TDF_Label> free;
  shapes->GetFreeShapes(free);
  std::vector<Value> roots;
  for (int at = 1; at <= free.Length(); ++at) {
    const TDF_Label& label = free.Value(at);
    std::string name = label_name(label);
    if (name.empty()) name = free.Length() == 1 ? stem : stem + std::to_string(at);
    roots.push_back(walker.visit(label, TopLoc_Location(), {name}, std::nullopt, name,
                                 free.Length() == 1 ? Occurrence{} : Occurrence{at - 1}, {entry_of(label)}, {}));
  }
  if (roots.size() == 1) {
    doc->tree = roots[0];
    doc->name = roots[0].get("name")->text;
  } else {
    doc->name = stem;
    doc->tree.kind = Value::OBJECT;
    doc->tree.keys.emplace_back("name", string_value(stem));
    Value list;
    list.kind = Value::LIST;
    list.items = std::move(roots);
    doc->tree.keys.emplace_back("children", std::move(list));
  }
  walker.checked_keys();
  const TDF_Label main = xdoc->Main();
  // The document's records on its main label: the closure, the animations (by name, as from_record keeps them:
  // a later row of a name in the first one's place), the parameters (parameters.recorded: each its _RECORDED
  // fields, a row with no string name left out; text that is no list is none).
  if (auto text = label_text(main, CLOSURE_GUID); text && !text->empty()) doc->closure = Value::parse(*text);
  if (auto text = label_text(main, ANIMATIONS_GUID); text && !text->empty()) {
    for (const Value& row : Value::parse(*text).items) {
      const Value* name = row.get("name");
      const Value* duration = row.get("duration");
      if (!name || !duration) throw std::runtime_error("the document's animations name no name or duration");
      bool replaced = false;
      for (auto& [held, seconds] : doc->animations)
        if (held == name->text) { seconds = duration->number(); replaced = true; }
      if (!replaced) doc->animations.emplace_back(name->text, duration->number());
    }
  }
  doc->parameters.kind = Value::LIST;
  if (auto text = label_text(main, PARAMETERS_GUID); text && !text->empty()) {
    Value found;
    try {
      found = Value::parse(*text);
    } catch (const std::runtime_error&) {
      found = Value();
    }
    for (const Value& row : found.items) {
      const Value* name = row.kind == Value::OBJECT ? row.get("name") : nullptr;
      if (!name || name->kind != Value::STRING) continue;
      Value kept;
      kept.kind = Value::OBJECT;
      for (const char* key : RECORDED) {
        const Value* v = row.get(key);
        kept.keys.emplace_back(key, v ? *v : Value());
      }
      doc->parameters.items.push_back(std::move(kept));
    }
  }
  doc->kinematics = kinematics(main, walker.occurrences, walker.instance_paths, walker.worlds);
  return doc;
}

// document.untextured: the texture maps a part's materials carry, by material name.
std::vector<std::pair<std::string, std::vector<std::string>>> untextured(const Part& part) {
  std::map<std::string, std::set<std::string>> found;
  auto add = [&](const Value& given) {
    const Value* pbr = given.get("pbr");
    const Value* maps = pbr ? pbr->get("textures") : nullptr;
    if (!maps || maps->kind != Value::OBJECT || maps->keys.empty()) return;
    std::string name;
    const Value* physics = given.get("material");
    const Value* named = physics ? physics->get("name") : nullptr;
    if (named && named->kind == Value::STRING && !named->text.empty()) name = named->text;
    if (name.empty() && (named = pbr->get("name")) && named->kind == Value::STRING && !named->text.empty())
      name = named->text;
    if (name.empty()) name = "material";
    for (const auto& [map, _] : maps->keys) found[name].insert(map);
  };
  if (part.material) add(*part.material);
  for (const auto& [_, given] : part.face_materials) add(given);
  std::vector<std::pair<std::string, std::vector<std::string>>> listed;
  for (const auto& [name, maps] : found) listed.emplace_back(name, std::vector<std::string>(maps.begin(), maps.end()));
  return listed;
}

std::string structure(const Document& doc) {
  Json j;
  auto color = [&](const std::optional<Rgba>& rgba) {
    if (!rgba) { j.null(); return; }
    j.open_list();
    for (double c : *rgba) j.num(c);
    j.close_list();
  };
  auto names = [&](const std::map<int, std::string>& table) {
    j.open();
    for (const auto& [ordinal, name] : table) j.key(ordinal).str(name);
    j.close();
  };
  j.open().key("name").str(doc.name).key("units").str("mm").key("tessellation").str(TESSELLATION);
  j.key("prototypes").open_list();
  for (const auto& part : doc.parts) {
    j.open().key("index").integer(part->index).key("key").str(part->key).key("name").str(part->name);
    j.key("color");
    color(part->color);
    j.key("faceNames");
    names(part->face_names);
    j.key("edgeNames");
    names(part->edge_names);
    j.key("vertexNames");
    names(part->vertex_names);
    j.key("faceColors").open();
    for (const auto& [ordinal, rgba] : part->face_colors) {
      j.key(ordinal);
      color(rgba);
    }
    j.close().key("material");
    if (part->material) part->material->write(j); else j.null();
    j.key("faceMaterials").open();
    for (const auto& [ordinal, given] : part->face_materials) {
      j.key(ordinal);
      given.write(j);
    }
    j.close().key("frames").open();
    for (const auto& [name, values] : part->frames) {
      j.key(name).open_list();
      for (double v : values) j.num(v);
      j.close_list();
    }
    j.close();
    for (const auto& [name, value] : part->declared) {
      j.key(name);
      value.write(j);
    }
    auto maps = untextured(*part);
    if (!maps.empty()) {
      j.key("untextured").open();
      for (const auto& [name, listed] : maps) {
        j.key(name).open_list();
        for (const std::string& map : listed) j.str(map);
        j.close_list();
      }
      j.close();
    }
    j.close();
  }
  j.close_list().key("instances").open_list();
  for (const Instance& instance : doc.instances) {
    j.open().key("prototype").integer(instance.prototype).key("path").str(instance.path).key("matrix").open_list();
    for (double v : instance.matrix) j.num(v);
    j.close_list().key("color");
    color(instance.color);
    j.close();
  }
  j.close_list().key("tree");
  doc.tree.write(j);
  if (doc.kinematics) j.key("kinematics").raw(*doc.kinematics);
  if (!doc.animations.empty()) {
    j.key("animations").open_list();
    for (const auto& [name, duration] : doc.animations) j.open().key("name").str(name).key("duration").num(duration).close();
    j.close_list();
  }
  if (!doc.parameters.items.empty()) {
    j.key("parameters");
    doc.parameters.write(j);
  }
  j.key("closure");
  if (doc.closure) doc.closure->write(j); else j.null();
  j.close();
  return j.out;
}

}  // namespace vc
