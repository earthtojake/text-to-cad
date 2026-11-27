// exports.cpp: the mesh exports' shared ground (export/mesh.py) and the STL (export/stl.py).
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <map>
#include <numeric>
#include <stdexcept>

#include <zlib.h>

#include "exports.hpp"

namespace vc {

const std::string& part_mesh(Part& part) {
  if (!part.meshed) {
    std::set<int> unmeshed;
    part.mesh = mesh_bytes(part.bytes, &unmeshed);
    part.unmeshed = unmeshed;
    part.meshed = true;
  }
  return part.mesh;
}

namespace {

Look look_of(const std::optional<Rgba>& color, const std::optional<Value>& material) {
  Look look;
  look.rgba = color ? *color : DEFAULT_COLOR;
  if (material && !(material->kind == Value::OBJECT && material->keys.empty()) && material->kind != Value::NUL)
    look.material = material;
  return look;
}

}  // namespace

std::vector<std::pair<Look, std::vector<uint32_t>>> look_groups(const MeshArrays& mesh, const Part& part,
                                                               const std::optional<Rgba>& color, bool painted) {
  std::optional<Rgba> base = color ? color : part.color;
  const std::optional<Value>& material = part.material;
  if (material && !color && !base) base = DEFAULT_COLOR;
  Look own = look_of(base, material);
  std::vector<std::pair<Look, std::vector<uint32_t>>> found;
  if (!painted || (part.face_colors.empty() && part.face_materials.empty())) {
    found.emplace_back(own, std::vector<uint32_t>(mesh.indices, mesh.indices + mesh.nindices));
    return found;
  }
  for (uint32_t f = 0; f < mesh.nfaces; ++f) {
    int ordinal = (int)mesh.faces[3 * f];
    uint32_t first = mesh.faces[3 * f + 1], count = mesh.faces[3 * f + 2];
    Look look;
    auto given = part.face_materials.find(ordinal);
    auto painted_colour = part.face_colors.find(ordinal);
    if (given != part.face_materials.end()) {
      look = look_of(painted_colour != part.face_colors.end() ? std::optional<Rgba>(painted_colour->second) : base,
                     given->second);
    } else if (painted_colour != part.face_colors.end()) {
      look = look_of(painted_colour->second, std::nullopt);
    } else {
      look = own;
    }
    size_t at = 0;
    while (at < found.size() && !(found[at].first == look)) ++at;
    if (at == found.size()) found.emplace_back(look, std::vector<uint32_t>());
    found[at].second.insert(found[at].second.end(), mesh.indices + first, mesh.indices + first + count);
  }
  return found;
}

// export/stl.py: binary STL, every placed triangle in millimetres (float32, as numpy places them), its normal from
// its corners; the header the document's name (ASCII, others as '?'), padded to 80 bytes with spaces.
std::string stl_bytes(Document& doc) {
  std::vector<MeshArrays> meshes(doc.parts.size());
  std::vector<bool> made(doc.parts.size(), false);
  uint32_t total = 0;
  for (const Instance& placed : doc.instances) {
    if (!made[placed.prototype]) {
      meshes[placed.prototype] = mesh_arrays(part_mesh(*doc.parts[placed.prototype]));
      made[placed.prototype] = true;
    }
    total += meshes[placed.prototype].triangles();
  }
  std::string header;
  // name.encode("ascii", "replace"): each character not ASCII one '?' (a UTF-8 sequence is one character).
  for (size_t i = 0; i < doc.name.size(); ++i) {
    unsigned char c = doc.name[i];
    if (c < 0x80) { header += (char)c; continue; }
    header += '?';
    while (i + 1 < doc.name.size() && ((unsigned char)doc.name[i + 1] & 0xC0) == 0x80) ++i;
  }
  header = header.substr(0, 80);
  header.resize(80, ' ');
  std::string out = header;
  out.append(reinterpret_cast<const char*>(&total), 4);
  out.reserve(84 + (size_t)total * 50);
  for (const Instance& placed : doc.instances) {
    const MeshArrays& mesh = meshes[placed.prototype];
    if (!mesh.triangles()) continue;
    // mesh.placed_points: points @ m[:3, :3].T + m[:3, 3], in float32, numpy's product a chain of fused
    // multiply-adds.
    const double* m = placed.matrix;  // column-major: m[column * 4 + row]
    float r[3][3], t[3];
    for (int row = 0; row < 3; ++row) {
      for (int column = 0; column < 3; ++column) r[row][column] = (float)m[column * 4 + row];
      t[row] = (float)m[12 + row];
    }
    std::vector<float> points((size_t)mesh.nodes * 3);
    for (uint32_t v = 0; v < mesh.nodes; ++v) {
      const float* p = mesh.positions + 3 * v;
      for (int row = 0; row < 3; ++row)
        points[3 * v + row] = std::fmaf(p[2], r[row][2], std::fmaf(p[1], r[row][1], p[0] * r[row][0])) + t[row];
    }
    for (uint32_t tri = 0; tri < mesh.triangles(); ++tri) {
      const float* c[3];
      for (int k = 0; k < 3; ++k) c[k] = &points[3 * mesh.indices[3 * tri + k]];
      float a[3], b[3], n[3];
      for (int i = 0; i < 3; ++i) { a[i] = c[1][i] - c[0][i]; b[i] = c[2][i] - c[0][i]; }
      n[0] = a[1] * b[2] - a[2] * b[1];
      n[1] = a[2] * b[0] - a[0] * b[2];
      n[2] = a[0] * b[1] - a[1] * b[0];
      float length = std::sqrt(n[0] * n[0] + n[1] * n[1] + n[2] * n[2]);
      if (length > 0)
        for (float& v : n) v /= length;
      char row[50] = {};
      std::memcpy(row, n, 12);
      for (int k = 0; k < 3; ++k) std::memcpy(row + 12 + 12 * k, c[k], 12);
      out.append(row, 50);
    }
  }
  return out;
}

// --- 3MF (export/threemf.py) -------------------------------------------------------------------------------------

namespace {

std::string format(const char* spec, double value) {
  char buf[64];
  std::snprintf(buf, sizeof buf, spec, value);
  return buf;
}

// Python's round(value, n): the correctly rounded decimal, read back.
double round_to(double value, int places) {
  char buf[512];
  std::snprintf(buf, sizeof buf, "%.*f", places, value);
  return std::strtod(buf, nullptr);
}

// xml.sax.saxutils.escape
std::string xml_escape(const std::string& text) {
  std::string out;
  for (char c : text) {
    if (c == '&') out += "&amp;";
    else if (c == '>') out += "&gt;";
    else if (c == '<') out += "&lt;";
    else out += c;
  }
  return out;
}

// xml.sax.saxutils.quoteattr
std::string quoteattr(const std::string& text) {
  std::string data;
  for (char c : xml_escape(text)) {
    if (c == '\n') data += "&#10;";
    else if (c == '\r') data += "&#13;";
    else if (c == '\t') data += "&#9;";
    else data += c;
  }
  if (data.find('"') != std::string::npos) {
    if (data.find('\'') != std::string::npos) {
      std::string quoted;
      for (char c : data) quoted += c == '"' ? std::string("&quot;") : std::string(1, c);
      return "\"" + quoted + "\"";
    }
    return "'" + data + "'";
  }
  return "\"" + data + "\"";
}

int srgb_byte(double value) {
  value = std::min(std::max(value, 0.0), 1.0);
  value = value <= 0.0031308 ? value * 12.92 : 1.055 * std::pow(value, 1 / 2.4) - 0.055;
  return (int)std::nearbyint(value * 255);  // Python's round: half to even
}

std::string hex_colour(const std::array<double, 4>& rgba) {
  char buf[16];
  std::snprintf(buf, sizeof buf, "#%02X%02X%02X%02X", srgb_byte(rgba[0]), srgb_byte(rgba[1]), srgb_byte(rgba[2]),
                (int)std::nearbyint(rgba[3] * 255));
  return buf;
}

const Value* path_of(const Value& value, std::initializer_list<const char*> keys) {
  const Value* at = &value;
  for (const char* key : keys) {
    if (!at || at->kind != Value::OBJECT) return nullptr;
    at = at->get(key);
  }
  return at;
}

double number_or(const Value* value, double otherwise) {
  return value && value->is_number() ? value->number() : otherwise;
}

// formats/gltf.drawn_alpha: a transmissive look fades by its PBR opacity's preview alone.
double drawn_alpha(double alpha, const Value* values) {
  const Value* given = values ? values->get("transmission") : nullptr;
  double transmission = given && given->is_number() ? given->number() : 0.0;
  if (transmission <= 0) return alpha;
  const Value* opacity = values->get("opacity");
  double a = !opacity || opacity->kind == Value::NUL ? 1.0 : std::min(opacity->number(), 1.0);
  return a >= 1.0 && transmission > 0 ? round_to(std::max(0.15, 1.0 - 0.7 * transmission), 4) : a;
}

// threemf._merged: positions welded where they round alike to 1e-5 mm, the kept ones sorted as numpy.unique sorts
// rows, each the first of its group; and per old position its kept index.
void merged(const MeshArrays& mesh, std::vector<uint32_t>& kept, std::vector<uint32_t>& remap) {
  const uint32_t n = mesh.nodes;
  std::vector<std::array<int64_t, 3>> keys(n);
  for (uint32_t v = 0; v < n; ++v)
    for (int c = 0; c < 3; ++c) keys[v][c] = (int64_t)std::nearbyint((double)mesh.positions[3 * v + c] / 1e-5);
  std::vector<uint32_t> order(n);
  std::iota(order.begin(), order.end(), 0);
  std::stable_sort(order.begin(), order.end(), [&](uint32_t a, uint32_t b) { return keys[a] < keys[b]; });
  remap.assign(n, 0);
  kept.clear();
  for (uint32_t at = 0; at < n; ++at) {
    uint32_t v = order[at];
    if (at == 0 || keys[v] != keys[order[at - 1]]) kept.push_back(v);
    remap[v] = (uint32_t)kept.size() - 1;
  }
}

// A zip as Python's zipfile writes one with writestr to a seekable file: each entry deflated (zlib's default level,
// raw), dated ZIP_DATE, version 20, made on a Unix system, mode 0600.
std::string zipped(const std::vector<std::pair<std::string, std::string>>& entries) {
  auto u16 = [](std::string& out, uint32_t v) { out += (char)(v & 255); out += (char)((v >> 8) & 255); };
  auto u32 = [&](std::string& out, uint32_t v) { u16(out, v & 0xFFFF); u16(out, v >> 16); };
  const uint32_t DOS_TIME = 0, DOS_DATE = (0 << 9) | (1 << 5) | 1;  // 1980-01-01 00:00:00
  std::string out, central;
  for (const auto& [name, text] : entries) {
    z_stream z{};
    if (deflateInit2(&z, Z_DEFAULT_COMPRESSION, Z_DEFLATED, -15, 8, Z_DEFAULT_STRATEGY) != Z_OK)
      throw std::runtime_error("deflate failed to start");
    std::string packed(deflateBound(&z, (uLong)text.size()) + 16, '\0');
    z.next_in = reinterpret_cast<Bytef*>(const_cast<char*>(text.data()));
    z.avail_in = (uInt)text.size();
    z.next_out = reinterpret_cast<Bytef*>(packed.data());
    z.avail_out = (uInt)packed.size();
    if (deflate(&z, Z_FINISH) != Z_STREAM_END) throw std::runtime_error("deflate failed");
    packed.resize(z.total_out);
    deflateEnd(&z);
    uint32_t crc = (uint32_t)crc32(0, reinterpret_cast<const Bytef*>(text.data()), (uInt)text.size());
    uint32_t offset = (uint32_t)out.size();
    u32(out, 0x04034b50); out += (char)20; out += (char)0; u16(out, 0); u16(out, 8); u16(out, DOS_TIME); u16(out, DOS_DATE);
    u32(out, crc); u32(out, (uint32_t)packed.size()); u32(out, (uint32_t)text.size()); u16(out, (uint32_t)name.size()); u16(out, 0);
    out += name;
    out += packed;
    u32(central, 0x02014b50); central += (char)20; central += (char)3; central += (char)20; central += (char)0;
    u16(central, 0); u16(central, 8); u16(central, DOS_TIME); u16(central, DOS_DATE); u32(central, crc);
    u32(central, (uint32_t)packed.size()); u32(central, (uint32_t)text.size()); u16(central, (uint32_t)name.size());
    u16(central, 0); u16(central, 0); u16(central, 0); u16(central, 0); u32(central, 0600u << 16); u32(central, offset);
    central += name;
  }
  uint32_t at = (uint32_t)out.size();
  out += central;
  u32(out, 0x06054b50); u16(out, 0); u16(out, 0); u16(out, (uint32_t)entries.size()); u16(out, (uint32_t)entries.size());
  u32(out, (uint32_t)central.size()); u32(out, at); u16(out, 0);
  return out;
}

}  // namespace

std::string threemf_bytes(Document& doc) {
  const char* CORE = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02";
  const char* MATERIALS = "http://schemas.microsoft.com/3dmanufacturing/material/2015/02";
  const int BASE_ID = 1, PROPERTIES_ID = 2;
  std::vector<Look> looks;
  auto look_index = [&](const Look& look) -> int {
    for (size_t i = 0; i < looks.size(); ++i)
      if (looks[i] == look) return (int)i;
    looks.push_back(look);
    return (int)looks.size() - 1;
  };
  std::vector<std::string> objects;
  std::vector<std::tuple<int, std::optional<Rgba>, int>> object_at;  // (part, colour) -> id, 0 for none
  auto object_of = [&](int index, const std::optional<Rgba>& color) -> int {
    for (const auto& [i, c, id] : object_at)
      if (i == index && c == color) return id;
    Part& part = *doc.parts[index];
    MeshArrays mesh = mesh_arrays(part_mesh(part));
    if (!mesh.triangles()) {
      object_at.emplace_back(index, color, 0);
      return 0;
    }
    int fallback = look_index(look_groups(mesh, part, color, false)[0].first);
    std::vector<uint32_t> kept, remap;
    merged(mesh, kept, remap);
    std::string vertices;
    for (uint32_t v : kept) {
      const float* p = mesh.positions + 3 * v;
      vertices += "<vertex x=\"" + format("%.6g", p[0]) + "\" y=\"" + format("%.6g", p[1]) + "\" z=\"" +
                  format("%.6g", p[2]) + "\"/>";
    }
    std::string rows;
    for (const auto& [look, indices] : look_groups(mesh, part, color, true)) {
      int at = look_index(look);
      std::string tail = at == fallback ? "/>" : " pid=\"" + std::to_string(BASE_ID) + "\" p1=\"" + std::to_string(at) + "\"/>";
      for (size_t t = 0; t + 2 < indices.size(); t += 3) {
        uint32_t a = remap[indices[t]], b = remap[indices[t + 1]], c = remap[indices[t + 2]];
        if (a == b || b == c || a == c) continue;
        rows += "<triangle v1=\"" + std::to_string(a) + "\" v2=\"" + std::to_string(b) + "\" v3=\"" + std::to_string(c) + "\"" + tail;
      }
    }
    int ident = (int)objects.size() + 3;
    objects.push_back("<object id=\"" + std::to_string(ident) + "\" type=\"model\" name=" + quoteattr(part.name) +
                      " pid=\"" + std::to_string(BASE_ID) + "\" pindex=\"" + std::to_string(fallback) +
                      "\"><mesh><vertices>" + vertices + "</vertices><triangles>" + rows + "</triangles></mesh></object>");
    object_at.emplace_back(index, color, ident);
    return ident;
  };
  std::string items;
  for (const Instance& placed : doc.instances) {
    int ident = object_of(placed.prototype, placed.color);
    if (!ident) continue;
    const double* m = placed.matrix;
    std::string transform;
    for (int k : {0, 1, 2, 4, 5, 6, 8, 9, 10, 12, 13, 14}) transform += (transform.empty() ? "" : " ") + format("%.9g", m[k]);
    items += "<item objectid=\"" + std::to_string(ident) + "\" transform=\"" + transform + "\"/>";
  }
  std::string bases, metallic;
  bool shown = false;
  for (size_t at = 0; at < looks.size(); ++at) {
    std::array<double, 4> rgba = looks[at].rgba;
    std::string name;
    if (looks[at].material) {
      shown = true;
      const Value& given = *looks[at].material;
      const Value* named = path_of(given, {"material", "name"});
      name = named && named->kind == Value::STRING ? named->text : "";
      const Value* values = path_of(given, {"pbr", "values"});
      rgba[3] = drawn_alpha(rgba[3], values);
      metallic += "<m:pbmetallic name=" + quoteattr(name) + " metallicness=\"" +
                  format("%.6g", number_or(values ? values->get("metalness") : nullptr, 0.0)) + "\" roughness=\"" +
                  format("%.6g", number_or(values ? values->get("roughness") : nullptr, 0.5)) + "\"/>";
    } else {
      name = "colour " + std::to_string(at + 1);
      metallic += "<m:pbmetallic name=" + quoteattr(name) + " metallicness=\"0\" roughness=\"0.6\"/>";
    }
    bases += "<base name=" + quoteattr(name) + " displaycolor=\"" + hex_colour(rgba) + "\"/>";
  }
  std::string resources = shown ? "<m:pbmetallicdisplayproperties id=\"" + std::to_string(PROPERTIES_ID) + "\">" + metallic +
                                      "</m:pbmetallicdisplayproperties>"
                                : "";
  std::string group = shown ? " m:displaypropertiesid=\"" + std::to_string(PROPERTIES_ID) + "\"" : "";
  std::string model = std::string("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n") +
                      "<model unit=\"millimeter\" xml:lang=\"en-US\" xmlns=\"" + CORE + "\" xmlns:m=\"" + MATERIALS + "\">" +
                      "<metadata name=\"Title\">" + xml_escape(doc.name) + "</metadata>" + "<resources>" + resources +
                      "<basematerials id=\"" + std::to_string(BASE_ID) + "\"" + group + ">" + bases + "</basematerials>";
  for (const std::string& object : objects) model += object;
  model += "</resources><build>" + items + "</build></model>";
  const std::string content_types =
      "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
      "<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">"
      "<Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/>"
      "<Default Extension=\"model\" ContentType=\"application/vnd.ms-package.3dmanufacturing-3dmodel+xml\"/>"
      "</Types>";
  const std::string relationships =
      "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
      "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">"
      "<Relationship Target=\"/3D/3dmodel.model\" Id=\"rel0\" "
      "Type=\"http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel\"/></Relationships>";
  return zipped({{"[Content_Types].xml", content_types}, {"_rels/.rels", relationships}, {"3D/3dmodel.model", model}});
}

}  // namespace vc
