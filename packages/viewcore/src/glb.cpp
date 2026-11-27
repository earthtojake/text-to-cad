// glb.cpp: an .xbf's GLB, as cad's export/glb.py writes it: a mesh per part (positions and normals one accessor
// pair, a primitive per look), a glTF material per look (threejs_materials' to_gltf, then glb._material), the
// assembly as nodes under one root in glTF's frame, and every configuration sequence and animation() as a glTF
// animation (glb_motion.cpp). numpy's arithmetic is mirrored where it reaches the bytes: its small matrix products
// are chains of fused multiply-adds, its reductions along an axis plain sums in order (glb.hpp).
#include <algorithm>
#include <cmath>
#include <cstring>
#include <map>
#include <set>
#include <stdexcept>

#include "glb.hpp"

namespace vc {
namespace glb {

// --- JSON written as Python's json.dumps(separators=(",", ":")) with ensure_ascii ----------------------------------

namespace {

void ascii_string(std::string& out, const std::string& text) {
  out += '"';
  for (size_t i = 0; i < text.size(); ++i) {
    unsigned char c = text[i];
    switch (c) {
      case '"': out += "\\\""; continue;
      case '\\': out += "\\\\"; continue;
      case '\n': out += "\\n"; continue;
      case '\r': out += "\\r"; continue;
      case '\t': out += "\\t"; continue;
      case '\b': out += "\\b"; continue;
      case '\f': out += "\\f"; continue;
      default: break;
    }
    if (c >= 0x20 && c < 0x7f) { out += (char)c; continue; }
    uint32_t code = c;
    if (c >= 0x80) {  // a UTF-8 sequence read whole
      int more = c >= 0xF0 ? 3 : c >= 0xE0 ? 2 : 1;
      code = c & (0x3F >> more);
      for (int k = 0; k < more && i + 1 < text.size(); ++k) code = (code << 6) | ((unsigned char)text[++i] & 0x3F);
    }
    char buf[16];
    if (code >= 0x10000) {
      code -= 0x10000;
      std::snprintf(buf, sizeof buf, "\\u%04x\\u%04x", 0xD800 + (code >> 10), 0xDC00 + (code & 0x3FF));
    } else {
      std::snprintf(buf, sizeof buf, "\\u%04x", code);
    }
    out += buf;
  }
  out += '"';
}

}  // namespace

void dumps(std::string& out, const Value& v) {
  switch (v.kind) {
    case Value::NUL: out += "null"; break;
    case Value::BOOL: out += v.flag ? "true" : "false"; break;
    case Value::INT: out += v.text; break;
    case Value::REAL: append_double(out, v.real); break;
    case Value::STRING: ascii_string(out, v.text); break;
    case Value::LIST:
      out += '[';
      for (size_t i = 0; i < v.items.size(); ++i) {
        if (i) out += ',';
        dumps(out, v.items[i]);
      }
      out += ']';
      break;
    case Value::OBJECT:
      out += '{';
      for (size_t i = 0; i < v.keys.size(); ++i) {
        if (i) out += ',';
        ascii_string(out, v.keys[i].first);
        out += ':';
        dumps(out, v.keys[i].second);
      }
      out += '}';
      break;
  }
}

Value real(double x) { Value v; v.kind = Value::REAL; v.real = x; return v; }
Value integer(long long n) { Value v; v.kind = Value::INT; v.text = std::to_string(n); return v; }
Value string(const std::string& s) { Value v; v.kind = Value::STRING; v.text = s; return v; }
Value boolean(bool b) { Value v; v.kind = Value::BOOL; v.flag = b; return v; }
Value object() { Value v; v.kind = Value::OBJECT; return v; }
Value list() { Value v; v.kind = Value::LIST; return v; }
Value reals(const double* x, size_t n) {
  Value v = list();
  for (size_t i = 0; i < n; ++i) v.items.push_back(real(x[i]));
  return v;
}

Value* at(Value& object_, const std::string& key) {
  for (auto& [k, v] : object_.keys)
    if (k == key) return &v;
  return nullptr;
}

Value& put(Value& object_, const std::string& key, Value value) {
  if (Value* held = at(object_, key)) { *held = std::move(value); return *held; }
  object_.keys.emplace_back(key, std::move(value));
  return object_.keys.back().second;
}

Value& setdefault(Value& object_, const std::string& key, Value value) {
  if (Value* held = at(object_, key)) return *held;
  object_.keys.emplace_back(key, std::move(value));
  return object_.keys.back().second;
}

bool pop(Value& object_, const std::string& key, Value* out) {
  for (auto it = object_.keys.begin(); it != object_.keys.end(); ++it) {
    if (it->first == key) {
      if (out) *out = std::move(it->second);
      object_.keys.erase(it);
      return true;
    }
  }
  return false;
}

// Python's truth of a JSON value.
bool truthy(const Value* v) {
  if (!v) return false;
  switch (v->kind) {
    case Value::NUL: return false;
    case Value::BOOL: return v->flag;
    case Value::INT: case Value::REAL: return v->number() != 0;
    case Value::STRING: return !v->text.empty();
    case Value::LIST: return !v->items.empty();
    case Value::OBJECT: return !v->keys.empty();
  }
  return false;
}

// --- the writer ------------------------------------------------------------------------------------------------

namespace {

constexpr uint32_t MAGIC = 0x46546C67, VERSION = 2, JSON_CHUNK = 0x4E4F534A, BIN_CHUNK = 0x004E4942;

// The PbrValues fields threejs_materials knows, by the camelCase name its to_dict writes.
const std::set<std::string>& known_values() {
  static const std::set<std::string> found = {
      "color", "metalness", "roughness", "ior", "normalScale", "emissive", "emissiveIntensity", "transmission",
      "opacity", "transparent", "alphaTest", "clearcoat", "clearcoatRoughness", "sheen", "sheenColor",
      "sheenRoughness", "anisotropy", "anisotropyRotation", "specularIntensity", "specularColor", "attenuationColor",
      "attenuationDistance", "thickness", "iridescence", "iridescenceIOR", "iridescenceThicknessRange", "dispersion",
      "displacementScale", "side"};
  return found;
}

// pbr_from_json(scalar_pbr(...)).override(metalness=..., roughness=...).values.to_dict(): the look's scalar values,
// None-valued and unknown keys left out, metalness and roughness given where they are not.
struct PbrValues {
  std::map<std::string, Value> values;
  const Value* get(const char* name) const {
    auto found = values.find(name);
    return found == values.end() ? nullptr : &found->second;
  }
};

PbrValues pbr_values(const Value& given) {
  PbrValues found;
  const Value* pbr = given.get("pbr");
  const Value* values = pbr ? pbr->get("values") : nullptr;
  if (values) {
    for (const auto& [key, value] : values->keys) {
      std::string name = key == "iridescenceIor" ? "iridescenceIOR" : key;
      if (known_values().count(name) && value.kind != Value::NUL) found.values[name] = value;
    }
  }
  if (!found.get("metalness")) found.values["metalness"] = real(0.0);
  if (!found.get("roughness")) found.values["roughness"] = real(0.5);
  return found;
}

bool positive(const Value* v) { return v && v->is_number() && v->number() > 0; }

// threejs_materials' _GltfBuilder.add_material then pygltflib's to_json (None and empty values left out), for a
// look with no texture maps: what glb._material starts from.
Value builder_material(const Value& given, const PbrValues& pbr, const std::string& name) {
  auto val = [&](const char* key) { return pbr.get(key); };
  auto first3 = [](const Value& v) {
    if (v.kind != Value::LIST) return v;
    Value cut = list();
    for (size_t i = 0; i < std::min<size_t>(3, v.items.size()); ++i) cut.items.push_back(v.items[i]);
    return cut;
  };
  // _build_extensions
  Value extensions = object();
  if (const Value* ior = val("ior")) put(extensions, "KHR_materials_ior", object()).keys.emplace_back("ior", *ior);
  if (positive(val("transmission")))
    put(extensions, "KHR_materials_transmission", object()).keys.emplace_back("transmissionFactor", *val("transmission"));
  Value volume = object();
  if (positive(val("thickness"))) volume.keys.emplace_back("thicknessFactor", *val("thickness"));
  if (const Value* att = val("attenuationColor")) volume.keys.emplace_back("attenuationColor", first3(*att));
  if (const Value* dist = val("attenuationDistance")) volume.keys.emplace_back("attenuationDistance", *dist);
  if (!volume.keys.empty()) put(extensions, "KHR_materials_volume", volume);
  if (positive(val("clearcoat"))) {
    Value ext = object();
    ext.keys.emplace_back("clearcoatFactor", *val("clearcoat"));
    if (const Value* rough = val("clearcoatRoughness")) ext.keys.emplace_back("clearcoatRoughnessFactor", *rough);
    put(extensions, "KHR_materials_clearcoat", ext);
  }
  if (positive(val("sheen"))) {
    Value ext = object();
    if (const Value* color = val("sheenColor")) ext.keys.emplace_back("sheenColorFactor", first3(*color));
    if (const Value* rough = val("sheenRoughness")) ext.keys.emplace_back("sheenRoughnessFactor", *rough);
    put(extensions, "KHR_materials_sheen", ext);
  }
  if (positive(val("iridescence"))) {
    Value ext = object();
    ext.keys.emplace_back("iridescenceFactor", *val("iridescence"));
    if (const Value* ior = val("iridescenceIOR")) ext.keys.emplace_back("iridescenceIor", *ior);
    const Value* range = val("iridescenceThicknessRange");
    if (range && range->kind == Value::LIST && range->items.size() == 2) {
      ext.keys.emplace_back("iridescenceThicknessMinimum", range->items[0]);
      ext.keys.emplace_back("iridescenceThicknessMaximum", range->items[1]);
    }
    put(extensions, "KHR_materials_iridescence", ext);
  }
  if (positive(val("anisotropy"))) {
    Value ext = object();
    ext.keys.emplace_back("anisotropyStrength", *val("anisotropy"));
    if (const Value* rotation = val("anisotropyRotation")) ext.keys.emplace_back("anisotropyRotation", *rotation);
    put(extensions, "KHR_materials_anisotropy", ext);
  }
  const Value* intensity = val("specularIntensity");
  const Value* specular = val("specularColor");
  if (intensity || specular) {
    Value ext = object();
    if (intensity) ext.keys.emplace_back("specularFactor", *intensity);
    if (specular) ext.keys.emplace_back("specularColorFactor", first3(*specular));
    if (!ext.keys.empty()) put(extensions, "KHR_materials_specular", ext);
  }
  const Value* strength = val("emissiveIntensity");
  if (strength && !(strength->is_number() && strength->number() == 1.0)) {
    Value ext = object();
    ext.keys.emplace_back("emissiveStrength", *strength);
    put(extensions, "KHR_materials_emissive_strength", ext);
  }
  if (positive(val("dispersion"))) {
    Value ext = object();
    ext.keys.emplace_back("dispersion", *val("dispersion"));
    put(extensions, "KHR_materials_dispersion", ext);
    if (!at(extensions, "KHR_materials_volume")) {
      Value v = object();
      v.keys.emplace_back("thicknessFactor", integer(0));
      put(extensions, "KHR_materials_volume", v);
    }
  }
  // pygltflib's delete_empty_keys: an empty dict is no key.
  for (auto it = extensions.keys.begin(); it != extensions.keys.end();)
    it = it->second.keys.empty() ? extensions.keys.erase(it) : it + 1;

  Value entry = object();
  if (!extensions.keys.empty()) entry.keys.emplace_back("extensions", extensions);
  Value pbr_mr = object();
  // The base colour factor is glb._material's own (written over); only its place matters here.
  pbr_mr.keys.emplace_back("baseColorFactor", list());
  pbr_mr.keys.emplace_back("metallicFactor", *val("metalness"));
  pbr_mr.keys.emplace_back("roughnessFactor", *val("roughness"));
  entry.keys.emplace_back("pbrMetallicRoughness", pbr_mr);
  const Value* emissive = val("emissive");
  double zeros[3] = {0, 0, 0};
  entry.keys.emplace_back("emissiveFactor", emissive && emissive->kind == Value::LIST ? first3(*emissive) : reals(zeros, 3));
  std::string mode = "OPAQUE";
  const Value* alpha_test = val("alphaTest");
  if (alpha_test) mode = "MASK";
  else if (const Value* t = val("transparent"); t && t->kind == Value::BOOL && t->flag) mode = "BLEND";
  entry.keys.emplace_back("alphaMode", string(mode));
  if (alpha_test) entry.keys.emplace_back("alphaCutoff", *alpha_test);
  const Value* side = val("side");
  entry.keys.emplace_back("doubleSided", boolean(side && side->is_number() && side->number() == 2));
  entry.keys.emplace_back("name", string(name));
  (void)given;
  return entry;
}

}  // namespace

// glb._material: a look as a glTF material.
Value material_entry(const Look& look, double thickness) {
  const std::array<double, 4>& rgba = look.rgba;
  if (!look.material) {
    Value entry = object();
    Value pbr = object();
    pbr.keys.emplace_back("baseColorFactor", reals(rgba.data(), 4));
    pbr.keys.emplace_back("metallicFactor", real(0.0));
    pbr.keys.emplace_back("roughnessFactor", real(0.6));
    entry.keys.emplace_back("pbrMetallicRoughness", pbr);
    entry.keys.emplace_back("doubleSided", boolean(false));
    entry.keys.emplace_back("alphaMode", string(rgba[3] < 1.0 ? "BLEND" : "OPAQUE"));
    return entry;
  }
  const Value& given = *look.material;
  PbrValues values = pbr_values(given);
  const Value* pbr = given.get("pbr");
  const Value* physics = given.get("material");
  const Value* pbr_name = pbr ? pbr->get("name") : nullptr;
  const Value* physical_name = physics ? physics->get("name") : nullptr;
  std::string name = truthy(pbr_name) ? pbr_name->text : (physical_name ? physical_name->text : std::string());
  Value entry = builder_material(given, values, pbr_name && pbr_name->kind == Value::STRING ? pbr_name->text : name);
  put(entry, "name", string(name));
  Value& extras = setdefault(entry, "extras", object());
  Value cad = object();
  cad.keys.emplace_back("material", physical_name ? *physical_name : Value());
  put(extras, "cad", cad);
  // glb._alpha
  const Value* transmission = values.get("transmission");
  double alpha = rgba[3];
  if (truthy(transmission)) {
    const Value* opacity = values.get("opacity");
    alpha = opacity ? std::min(opacity->number(), 1.0) : 1.0;
  }
  Value& pbr_mr = *at(entry, "pbrMetallicRoughness");
  double base[4] = {rgba[0], rgba[1], rgba[2], alpha};
  put(pbr_mr, "baseColorFactor", reals(base, 4));
  put(entry, "alphaMode", string(alpha < 1.0 ? "BLEND" : "OPAQUE"));
  if (truthy(transmission)) {
    Value& extensions = setdefault(entry, "extensions", object());
    Value& volume = setdefault(extensions, "KHR_materials_volume", object());
    put(volume, "thicknessFactor", real(thickness));
  }
  return entry;
}

namespace {

// glb.tangents: a tangent per vertex for an anisotropic look, in float32 as numpy makes it.
std::string tangents(const MeshArrays& mesh) {
  std::string out((size_t)mesh.nodes * 16, '\0');
  float* t = reinterpret_cast<float*>(&out[0]);
  for (uint32_t v = 0; v < mesh.nodes; ++v) {
    const float* n = mesh.normals + 3 * v;
    // np.cross(normal, (0, 0, 1))
    float x = n[1] * 1.0f - n[2] * 0.0f, y = n[2] * 0.0f - n[0] * 1.0f, z = n[0] * 0.0f - n[1] * 0.0f;
    float length = std::sqrt((x * x + y * y) + z * z);
    if (length < 1e-3f) {  // np.cross(normal, (1, 0, 0))
      x = n[1] * 0.0f - n[2] * 0.0f;
      y = n[2] * 1.0f - n[0] * 0.0f;
      z = n[0] * 0.0f - n[1] * 1.0f;
    }
    length = std::sqrt((x * x + y * y) + z * z);
    if (length > 0) {
      float d = std::max(length, (float)1e-12);
      x /= d; y /= d; z /= d;
    } else {
      x = 1.0f; y = 0.0f; z = 0.0f;
    }
    t[4 * v] = x; t[4 * v + 1] = y; t[4 * v + 2] = z; t[4 * v + 3] = 1.0f;
  }
  return out;
}

// glb._thickness: the smallest extent of the part's box, in float32.
double thickness_of(const MeshArrays& mesh) {
  if (!mesh.nodes) return 0.0;
  float low[3], high[3];
  for (int c = 0; c < 3; ++c) low[c] = high[c] = mesh.positions[c];
  for (uint32_t v = 1; v < mesh.nodes; ++v)
    for (int c = 0; c < 3; ++c) {
      float x = mesh.positions[3 * v + c];
      low[c] = std::min(low[c], x);
      high[c] = std::max(high[c], x);
    }
  float least = high[0] - low[0];
  for (int c = 1; c < 3; ++c) least = std::min(least, high[c] - low[c]);
  return least;
}

std::string floats(const float* data, size_t count) {
  return std::string(reinterpret_cast<const char*>(data), count * 4);
}

}  // namespace

std::string glb_document(Document& doc) {
  // Each placed prototype's mesh (export/mesh.meshes), in the order first placed.
  std::map<int, MeshArrays> held;
  for (const Instance& placed : doc.instances)
    if (!held.count(placed.prototype)) held[placed.prototype] = mesh_arrays(part_mesh(*doc.parts[placed.prototype]));

  Buffers buffers;
  std::vector<Value> materials;
  std::vector<std::pair<std::pair<Look, std::optional<double>>, int>> material_at;
  std::set<std::string> used;

  auto material = [&](const Look& look, double thickness) {
    const Value* values = look.material && look.material->get("pbr") ? look.material->get("pbr")->get("values") : nullptr;
    std::optional<double> keyed;
    if (look.material && truthy(values ? values->get("transmission") : nullptr)) keyed = thickness;
    for (const auto& [key, index] : material_at)
      if (key.first == look && key.second == keyed) return index;
    Value entry = material_entry(look, thickness);
    if (const Value* extensions = at(entry, "extensions"))
      for (const auto& [name, _] : extensions->keys) used.insert(name);
    materials.push_back(entry);
    material_at.push_back({{look, keyed}, (int)materials.size() - 1});
    return (int)materials.size() - 1;
  };

  std::vector<Value> meshes;
  struct Shared { int positions, normals, tangents = -1; std::map<std::string, int> spans; };
  std::map<int, Shared> shared;
  std::vector<std::pair<std::pair<int, std::optional<Rgba>>, int>> mesh_at;

  auto mesh_of = [&](int index, const std::optional<Rgba>& color) -> int {
    for (const auto& [key, found] : mesh_at)
      if (key.first == index && key.second == color) return found;
    const MeshArrays& mesh = held[index];
    if (!mesh.triangles()) return -1;
    const Part& part = *doc.parts[index];
    if (!shared.count(index)) {
      Shared s;
      s.positions = buffers.add(floats(mesh.positions, 3 * (size_t)mesh.nodes), mesh.nodes, 34962, "VEC3", 5126,
                                mesh.positions);
      s.normals = buffers.add(floats(mesh.normals, 3 * (size_t)mesh.nodes), mesh.nodes, 34962, "VEC3", 5126,
                              mesh.normals);
      shared[index] = s;
    }
    Shared& s = shared[index];
    auto looks = look_groups(mesh, part, color);
    Value attributes = object();
    attributes.keys.emplace_back("POSITION", integer(s.positions));
    attributes.keys.emplace_back("NORMAL", integer(s.normals));
    bool anisotropic = false;
    for (const auto& [look, _] : looks) {
      const Value* pbr = look.material ? look.material->get("pbr") : nullptr;
      const Value* values = pbr ? pbr->get("values") : nullptr;
      anisotropic = anisotropic || truthy(values ? values->get("anisotropy") : nullptr);
    }
    if (anisotropic) {
      if (s.tangents < 0) s.tangents = buffers.add(tangents(mesh), mesh.nodes, 34962, "VEC4", 5126);
      attributes.keys.emplace_back("TANGENT", integer(s.tangents));
    }
    double thickness = thickness_of(mesh);
    bool narrow = mesh.nodes <= 65535;
    Value primitives = list();
    for (const auto& [look, indices] : looks) {
      std::string span(reinterpret_cast<const char*>(indices.data()), indices.size() * 4);
      auto found = s.spans.find(span);
      int accessor;
      if (found == s.spans.end()) {
        std::string data;
        if (narrow) {
          std::vector<uint16_t> narrowed(indices.begin(), indices.end());
          data.assign(reinterpret_cast<const char*>(narrowed.data()), narrowed.size() * 2);
        } else {
          data = span;
        }
        accessor = s.spans[span] = buffers.add(data, indices.size(), 34963, "SCALAR", narrow ? 5123 : 5125);
      } else {
        accessor = found->second;
      }
      Value primitive = object();
      primitive.keys.emplace_back("attributes", attributes);
      primitive.keys.emplace_back("indices", integer(accessor));
      primitive.keys.emplace_back("material", integer(material(look, thickness)));
      primitives.items.push_back(primitive);
    }
    Value entry = object();
    entry.keys.emplace_back("name", string(part.name));
    entry.keys.emplace_back("primitives", primitives);
    meshes.push_back(entry);
    mesh_at.push_back({{index, color}, (int)meshes.size() - 1});
    return (int)meshes.size() - 1;
  };

  std::map<int, int> drawn;  // instance -> its mesh
  for (size_t i = 0; i < doc.instances.size(); ++i) {
    const Instance& placed = doc.instances[i];
    std::optional<Rgba> color = placed.color;  // the core keeps an instance's colour only where it is its own
    if (held[placed.prototype].triangles()) {
      int found = mesh_of(placed.prototype, color);
      if (found >= 0) drawn[(int)i] = found;
    }
  }
  Tree tree = build_tree(doc, drawn);
  std::vector<int> shown;
  for (size_t i = 0; i < doc.instances.size(); ++i)
    if (drawn.count((int)i)) shown.push_back((int)i);
  std::vector<Value> animations = bake_animations(doc, held, shown, tree, buffers);

  Value document = object();
  Value asset = object();
  asset.keys.emplace_back("version", string("2.0"));
  asset.keys.emplace_back("generator", string("cad"));
  document.keys.emplace_back("asset", asset);
  document.keys.emplace_back("scene", integer(0));
  Value scene = object();
  scene.keys.emplace_back("name", string(doc.name));
  Value roots = list();
  roots.items.push_back(integer(0));
  scene.keys.emplace_back("nodes", roots);
  Value scenes = list();
  scenes.items.push_back(scene);
  document.keys.emplace_back("scenes", scenes);
  auto listed = [](std::vector<Value> items) { Value v = list(); v.items = std::move(items); return v; };
  document.keys.emplace_back("nodes", listed(std::move(tree.nodes)));
  document.keys.emplace_back("meshes", listed(std::move(meshes)));
  document.keys.emplace_back("materials", listed(std::move(materials)));
  document.keys.emplace_back("accessors", listed(std::move(buffers.accessors)));
  document.keys.emplace_back("bufferViews", listed(std::move(buffers.views)));
  Value buffer = object();
  buffer.keys.emplace_back("byteLength", integer((long long)buffers.blob.size()));
  Value buffer_list = list();
  buffer_list.items.push_back(buffer);
  document.keys.emplace_back("buffers", buffer_list);
  if (!animations.empty()) document.keys.emplace_back("animations", listed(std::move(animations)));
  if (!used.empty()) {
    Value names = list();
    for (const std::string& name : used) names.items.push_back(string(name));  // a std::set: sorted
    document.keys.emplace_back("extensionsUsed", names);
  }
  std::string text;
  dumps(text, document);
  while (text.size() % 4) text += ' ';
  std::string& blob = buffers.blob;
  while (blob.size() % 4) blob += '\0';
  std::string out;
  auto u32 = [&](uint32_t x) { out.append(reinterpret_cast<const char*>(&x), 4); };
  u32(MAGIC);
  u32(VERSION);
  u32((uint32_t)(12 + 8 + text.size() + 8 + blob.size()));
  u32((uint32_t)text.size());
  u32(JSON_CHUNK);
  out += text;
  u32((uint32_t)blob.size());
  u32(BIN_CHUNK);
  out += blob;
  return out;
}

}  // namespace glb

std::string glb_bytes(Document& doc) { return glb::glb_document(doc); }

}  // namespace vc
