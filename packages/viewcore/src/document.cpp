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

namespace {

const char* KEY_GUID = "c8f2d4a6-1b3e-4f5a-9c7d-2e8b6a4f0d13";
const int MAX_OCCURRENCES = 250000;
const int MAX_ASSEMBLY_DEPTH = 64;

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

// document._prototype (names and colours; materials and declarations are not read).
std::unique_ptr<Part> make_part(int index, const TDF_Label& label, const TopoDS_Shape& shape) {
  auto part = std::make_unique<Part>();
  part->index = index;
  part->shape = shape.Located(TopLoc_Location());
  part->bytes = shape_bytes(part->shape);
  part->key = blake2b_hex(part->bytes.data(), part->bytes.size());
  part->color = label_color(label);
  NCollection_Sequence<TDF_Label> subs;
  XCAFDoc_ShapeTool::GetSubShapes(label, subs);
  if (subs.Length()) {
    ShapeMap faces, edges, vertices;
    bool vertices_mapped = false;
    TopExp::MapShapes(shape, TopAbs_FACE, faces);
    TopExp::MapShapes(shape, TopAbs_EDGE, edges);
    std::vector<std::pair<TopoDS_Shape, Rgba>> holding;
    for (int at = 1; at <= subs.Length(); ++at) {
      const TDF_Label& sub = subs.Value(at);
      TopoDS_Shape held = XCAFDoc_ShapeTool::GetShape(sub);
      if (held.IsNull()) continue;
      TopAbs_ShapeEnum kind = held.ShapeType();
      if (kind != TopAbs_FACE && kind != TopAbs_EDGE && kind != TopAbs_VERTEX) {
        if (auto rgba = label_color(sub)) holding.emplace_back(held, *rgba);
      } else if (kind == TopAbs_FACE) {
        int ordinal = faces.FindIndex(held);
        if (ordinal) {
          std::string name = label_name(sub);
          if (!name.empty()) part->face_names[ordinal] = name;
          if (auto rgba = label_color(sub)) part->face_colors[ordinal] = *rgba;
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
  }
  std::string name = label_name(label);
  part->name = name.empty() ? "part" + std::to_string(index + 1) : name;
  return part;
}

class Walker {
 public:
  Document& doc;
  std::map<std::string, int> by_entry;
  std::map<int, std::string> claims;
  int counted = 0;

  explicit Walker(Document& d) : doc(d) {}

  void visit(const TDF_Label& label, const TopLoc_Location& location, const std::vector<std::string>& path,
             std::optional<Rgba> inherited, const std::string& name, int depth, const std::set<std::string>& ancestors) {
    if (++counted > MAX_OCCURRENCES) throw std::runtime_error("the assembly names too many occurrences");
    if (depth > MAX_ASSEMBLY_DEPTH) throw std::runtime_error("the assembly is too deep");
    std::optional<Rgba> color = label_color(label);
    if (!color) color = inherited;
    if (XCAFDoc_ShapeTool::IsAssembly(label)) {
      std::string own = entry_of(label);
      if (ancestors.count(own)) throw std::runtime_error("an assembly contains itself");
      std::set<std::string> inner = ancestors;
      inner.insert(own);
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
        visit(referred, placed, child_path, child_color, child_name, depth + 1, inner);
      }
      return;
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
    // document._matrix: 4x4, column-major.
    const gp_Trsf transform = placed.Transformation();
    for (int column = 0; column < 4; ++column)
      for (int row = 0; row < 4; ++row)
        instance.matrix[column * 4 + row] =
            row < 3 ? transform.Value(row + 1, column + 1) : (column == 3 ? 1.0 : 0.0);
    const Part& prototype = *doc.parts[index];
    if (color != prototype.color) instance.color = color;
    doc.instances.push_back(instance);
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

std::unique_ptr<Document> open_xbf(const uint8_t* data, size_t size) {
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
  Walker walker(*doc);
  occ::handle<XCAFDoc_ShapeTool> shapes = XCAFDoc_DocumentTool::ShapeTool(xdoc->Main());
  NCollection_Sequence<TDF_Label> free;
  shapes->GetFreeShapes(free);
  for (int at = 1; at <= free.Length(); ++at) {
    const TDF_Label& label = free.Value(at);
    std::string name = label_name(label);
    // Python names an unnamed root by the file's stem, which bytes do not carry: "document" stands for it.
    if (name.empty()) name = free.Length() == 1 ? "document" : "document" + std::to_string(at);
    walker.visit(label, TopLoc_Location(), {name}, std::nullopt, name, free.Length() == 1 ? 0 : 1, {});
  }
  walker.checked_keys();
  return doc;
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
  j.open().key("prototypes").open_list();
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
    j.close().close();
  }
  j.close_list().key("instances").open_list();
  for (const Instance& instance : doc.instances) {
    j.open().key("prototype").integer(instance.prototype).key("path").str(instance.path).key("matrix").open_list();
    for (double v : instance.matrix) j.num(v);
    j.close_list().key("color");
    color(instance.color);
    j.close();
  }
  j.close_list().close();
  return j.out;
}

}  // namespace vc
