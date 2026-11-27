// mechanism.cpp: a document's mechanism read as cad's mechanism.read reads it, and written as the structure's
// "kinematics" (mechanism.block): the subtree under Main() marked by mechanism.GUID, of standard attributes only
// (names, NamedData, reference lists, real and integer arrays, assembly item references). See mechanism.py's module
// docstring for the layout.
#include <algorithm>
#include <cmath>
#include <deque>
#include <limits>
#include <map>
#include <optional>
#include <set>
#include <string>
#include <vector>

#include <NCollection_HArray1.hxx>
#include <Standard_GUID.hxx>
#include <TCollection_AsciiString.hxx>
#include <TCollection_ExtendedString.hxx>
#include <TDF_ChildIterator.hxx>
#include <TDF_Label.hxx>
#include <TDF_Tool.hxx>
#include <TDataStd_IntegerArray.hxx>
#include <TDataStd_Name.hxx>
#include <TDataStd_NamedData.hxx>
#include <TDataStd_RealArray.hxx>
#include <TDataStd_ReferenceList.hxx>
#include <XCAFDoc_AssemblyItemId.hxx>
#include <XCAFDoc_AssemblyItemRef.hxx>

#include "core.hpp"

namespace vc {

namespace {

const char* GUID = "5b0e7a64-3c1d-4f8e-a2b9-6d4c1e7f9a20";
const char* SCHEMA = "cadgen.kinematics/2";
const char* COUPLER = "KinematicPairWithMotionCoupling";
const char* SCREW = "SCREW_PAIR";

struct Dof { const char* unit; const char* lower; const char* upper; };
struct Kind { const char* name; const char* entity; std::vector<Dof> dofs; };
const Dof ROTATION{"deg", "lower_limit_actual_rotation", "upper_limit_actual_rotation"};
const Dof TRANSLATION{"mm", "lower_limit_actual_translation", "upper_limit_actual_translation"};
const std::vector<Kind>& kinds() {
  static const std::vector<Kind> found = {
      {"revolute", "REVOLUTE_PAIR", {ROTATION}},
      {"prismatic", "PRISMATIC_PAIR", {TRANSLATION}},
      {"cylindrical", "CYLINDRICAL_PAIR", {ROTATION, TRANSLATION}},
      {"spherical", "SPHERICAL_PAIR",
       {{"deg", "lower_limit_roll", "upper_limit_roll"}, {"deg", "lower_limit_pitch", "upper_limit_pitch"},
        {"deg", "lower_limit_yaw", "upper_limit_yaw"}}},
  };
  return found;
}
const Kind* kind_of(const std::string& name) {
  for (const Kind& k : kinds())
    if (name == k.name) return &k;
  return nullptr;
}

using Limit = std::pair<std::optional<double>, std::optional<double>>;
using Values = std::vector<double>;
// A dict of pair label -> values, in insertion order.
using State = std::vector<std::pair<std::string, Values>>;

Values* state_at(State& state, const std::string& label) {
  for (auto& [held, values] : state)
    if (held == label) return &values;
  return nullptr;
}

struct Link { std::string name; std::vector<Occurrence> members; };
struct Pair {
  std::string label;
  const Kind* kind;
  int links[2];
  std::optional<std::array<std::vector<double>, 2>> frames;
  std::vector<Limit> limits;
  size_t dofs() const { return kind->dofs.size(); }
};
struct Key { double t; std::optional<std::string> configuration; State values; };
struct Motion { std::string name; std::vector<Key> keys; std::string ease; };
struct Coupling { std::string name; State ratios; };

struct Mechanism {
  std::string name;
  std::vector<Link> links;
  int ground = 0;
  std::vector<Pair> pairs;
  State as_built;
  std::vector<std::pair<std::string, State>> configurations;
  std::vector<std::pair<std::string, Motion>> motions;
  std::vector<std::pair<std::string, Coupling>> couplings;
};

template <typename T>
void put(std::vector<std::pair<std::string, T>>& dict, const std::string& name, T value) {
  for (auto& [held, item] : dict)
    if (held == name) { item = std::move(value); return; }
  dict.emplace_back(name, std::move(value));
}

std::string entry(const TDF_Label& label) {
  TCollection_AsciiString text;
  TDF_Tool::Entry(label, text);
  return text.ToCString();
}

std::string name_of(const TDF_Label& label) {
  occ::handle<TDataStd_Name> found;
  if (!label.IsNull() && label.FindAttribute(TDataStd_Name::GetID(), found)) return utf8(found->Get());
  return "";
}

std::vector<TDF_Label> children(const TDF_Label& label) {
  std::vector<TDF_Label> found;
  if (label.IsNull()) return found;
  for (TDF_ChildIterator it(label, false); it.More(); it.Next()) found.push_back(it.Value());
  return found;
}

occ::handle<TDataStd_NamedData> named(const TDF_Label& label) {
  occ::handle<TDataStd_NamedData> data;
  if (label.IsNull() || !label.FindAttribute(TDataStd_NamedData::GetID(), data)) return nullptr;
  data->LoadDeferredData();
  return data;
}

std::optional<std::string> text_of(const occ::handle<TDataStd_NamedData>& data, const char* key) {
  TCollection_ExtendedString k(key);
  if (data.IsNull() || !data->HasString(k)) return std::nullopt;
  return utf8(data->GetString(k));
}

std::optional<double> real_of(const occ::handle<TDataStd_NamedData>& data, const char* key) {
  TCollection_ExtendedString k(key);
  if (data.IsNull() || !data->HasReal(k)) return std::nullopt;
  return data->GetReal(k);
}

std::optional<std::vector<double>> array_of(const occ::handle<TDataStd_NamedData>& data, const char* key) {
  TCollection_ExtendedString k(key);
  if (data.IsNull() || !data->HasArrayOfReals(k)) return std::nullopt;
  const occ::handle<NCollection_HArray1<double>>& array = data->GetArrayOfReals(k);
  std::vector<double> found;
  if (!array.IsNull())
    for (int at = array->Lower(); at <= array->Upper(); ++at) found.push_back(array->Value(at));
  return found;
}

std::vector<std::string> references(const TDF_Label& label) {
  std::vector<std::string> found;
  occ::handle<TDataStd_ReferenceList> list;
  if (label.IsNull() || !label.FindAttribute(TDataStd_ReferenceList::GetID(), list)) return found;
  for (const TDF_Label& item : list->List()) found.push_back(entry(item));
  return found;
}

// mechanism._read_state
State read_state(const TDF_Label& label, const std::vector<std::string>& refs, const std::map<std::string, int>& pair_at,
                 const std::vector<Pair>& pairs) {
  State rows;
  occ::handle<TDataStd_RealArray> reals;
  occ::handle<TDataStd_IntegerArray> dofs;
  if (refs.empty() || label.IsNull() || !label.FindAttribute(TDataStd_RealArray::GetID(), reals) ||
      !label.FindAttribute(TDataStd_IntegerArray::GetID(), dofs))
    return rows;
  for (size_t row = 0; row < refs.size(); ++row) {
    auto found = pair_at.find(refs[row]);
    if (found == pair_at.end()) throw std::runtime_error("a mechanism state names a pair the mechanism has not");
    const Pair& pair = pairs[found->second];
    Values* values = state_at(rows, pair.label);
    if (!values) {
      rows.emplace_back(pair.label, Values(pair.dofs(), 0.0));
      values = &rows.back().second;
    }
    int index = dofs->Value(dofs->Lower() + (int)row);
    if (index < 0 || index >= (int)values->size()) throw std::runtime_error("a mechanism state's value is out of its pair");
    (*values)[index] = reals->Value(reals->Lower() + (int)row);
  }
  return rows;
}

int value_index(const Kind* kind, const std::string& type) {
  return std::string(kind->name) == "cylindrical" && type == "translation" ? 1 : 0;
}

// mechanism._read_couplers
std::optional<Coupling> read_couplers(const std::string& name, const TDF_Label& label,
                                      const std::map<std::string, int>& pair_at, const std::vector<Pair>& pairs) {
  struct Relation { std::pair<std::string, int> a, b; double ra, rb; };
  std::vector<Relation> relations;
  std::vector<std::pair<std::string, double>> screws;
  for (const TDF_Label& coupler : children(label)) {
    occ::handle<TDataStd_NamedData> data = named(coupler);
    std::optional<std::string> entity = text_of(data, "entity");
    std::vector<const Pair*> ends;
    for (const std::string& at : references(coupler)) {
      auto found = pair_at.find(at);
      if (found != pair_at.end()) ends.push_back(&pairs[found->second]);
    }
    std::optional<double> pitch = real_of(data, "pitch");
    if (entity && *entity == SCREW && ends.size() == 1 && pitch) {
      screws.emplace_back(ends[0]->label, *pitch);
      continue;
    }
    if (!entity || *entity != COUPLER || ends.size() != 2) continue;
    std::optional<std::vector<double>> scales = array_of(data, "CouplingRatios");
    std::string given = text_of(data, "CouplingTypes").value_or("");
    std::vector<std::string> types;
    size_t start = 0;
    while (true) {
      size_t comma = given.find(',', start);
      types.push_back(given.substr(start, comma == std::string::npos ? std::string::npos : comma - start));
      if (comma == std::string::npos) break;
      start = comma + 1;
    }
    if (!scales || scales->size() != 2 || types.size() != 2) continue;
    relations.push_back({{ends[0]->label, value_index(ends[0]->kind, types[0])},
                         {ends[1]->label, value_index(ends[1]->kind, types[1])}, -(*scales)[1], (*scales)[0]});
  }
  std::vector<std::pair<std::pair<std::string, int>, double>> ratios;  // a dict, in insertion order
  auto setdefault = [&](const std::pair<std::string, int>& key, double value) -> double& {
    for (auto& [held, ratio] : ratios)
      if (held == key) return ratio;
    ratios.emplace_back(key, value);
    return ratios.back().second;
  };
  for (const Relation& r : relations) {
    setdefault(r.a, r.ra);
    setdefault(r.b, r.rb);
  }
  for (const auto& [label_, pitch] : screws) {
    double turn = setdefault({label_, 0}, 1.0);
    setdefault({label_, 1}, 0.0) = turn * pitch / 360.0;
  }
  if (ratios.empty()) return std::nullopt;
  Coupling coupling{name, {}};
  for (const auto& [key, ratio] : ratios) {
    const Pair* pair = nullptr;
    for (const Pair& p : pairs)
      if (p.label == key.first) { pair = &p; break; }
    Values* values = state_at(coupling.ratios, key.first);
    if (!values) {
      coupling.ratios.emplace_back(key.first, Values(pair->dofs(), 0.0));
      values = &coupling.ratios.back().second;
    }
    if (key.second < (int)values->size()) (*values)[key.second] = ratio;
  }
  return coupling;
}

const std::map<std::string, std::string>& eases() {
  static const std::map<std::string, std::string> found = {{"linear_interpolation_type", "linear"},
                                                           {"synchronous_interpolation_type", "cubic"}};
  return found;
}

// mechanism.read
std::optional<Mechanism> read(const TDF_Label& main, const std::map<std::string, Occurrence>& occurrences) {
  Standard_GUID marker(GUID);
  TDF_Label root;
  for (const TDF_Label& label : children(main))
    if (label.IsAttribute(marker)) { root = label; break; }
  if (root.IsNull()) return std::nullopt;
  Mechanism m;
  TDF_Label top = root.FindChild(1, false);
  std::map<std::string, int> link_at, pair_at;
  for (const TDF_Label& label : children(top.FindChild(1, false))) {
    Link link{name_of(label), {}};
    for (const TDF_Label& member : children(label)) {
      occ::handle<XCAFDoc_AssemblyItemRef> item;
      if (member.FindAttribute(XCAFDoc_AssemblyItemRef::GetID(), item)) {
        auto found = occurrences.find(item->GetItem().ToString().ToCString());
        if (found != occurrences.end()) link.members.push_back(found->second);
      }
    }
    link_at[entry(label)] = (int)m.links.size();
    m.links.push_back(std::move(link));
  }
  for (const TDF_Label& label : children(top.FindChild(2, false))) {
    occ::handle<TDataStd_NamedData> data = named(label);
    std::string entity = text_of(data, "entity").value_or("");
    const std::string suffix = "_WITH_RANGE";
    if (entity.size() >= suffix.size() && entity.compare(entity.size() - suffix.size(), suffix.size(), suffix) == 0)
      entity.erase(entity.size() - suffix.size());
    const Kind* kind = nullptr;
    for (const Kind& k : kinds())
      if (entity == k.entity) kind = &k;
    std::vector<int> ends;
    bool missing = false;
    for (const std::string& at : references(label)) {
      auto found = link_at.find(at);
      if (found == link_at.end()) missing = true; else ends.push_back(found->second);
    }
    if (!kind || missing || ends.size() != 2) continue;
    Pair pair{name_of(label), kind, {ends[0], ends[1]}, std::nullopt, {}};
    auto first = array_of(data, "transform_item_1"), second = array_of(data, "transform_item_2");
    if (first && second) pair.frames = std::array<std::vector<double>, 2>{*first, *second};
    for (const Dof& dof : kind->dofs) pair.limits.emplace_back(real_of(data, dof.lower), real_of(data, dof.upper));
    pair_at[entry(label)] = (int)m.pairs.size();
    m.pairs.push_back(std::move(pair));
  }
  std::vector<std::string> top_refs = references(top);
  auto ground = link_at.find(top_refs.empty() ? "" : top_refs[0]);
  m.ground = ground == link_at.end() ? 0 : ground->second;
  TDF_Label held_state = top.FindChild(3, false);
  m.as_built = read_state(held_state, references(held_state), pair_at, m.pairs);
  std::vector<TDF_Label> configuration_labels = children(top.FindChild(4, false));
  std::map<std::string, std::string> configuration_named;
  for (const TDF_Label& label : configuration_labels) {
    put(m.configurations, name_of(label), read_state(label, references(label), pair_at, m.pairs));
    configuration_named[entry(label)] = name_of(label);
  }
  for (const TDF_Label& label : children(top.FindChild(5, false))) {
    Motion motion{name_of(label), {}, "cubic"};
    int at = 0;
    for (const TDF_Label& segment : children(label)) {
      std::vector<std::string> refs = references(segment);
      occ::handle<TDataStd_NamedData> data = named(segment);
      double t = real_of(data, "t_parameter").value_or(0.0);
      if (at++ == 0) {
        auto ease = eases().find(text_of(data, "interpolation").value_or(""));
        motion.ease = ease == eases().end() ? "cubic" : ease->second;
      }
      auto configuration = refs.empty() ? configuration_named.end() : configuration_named.find(refs[0]);
      if (configuration != configuration_named.end())
        motion.keys.push_back({t, configuration->second, {}});
      else
        motion.keys.push_back({t, std::nullopt, read_state(segment, refs, pair_at, m.pairs)});
    }
    put(m.motions, motion.name, motion);
  }
  for (const TDF_Label& label : children(top.FindChild(6, false))) {
    std::optional<Coupling> coupling = read_couplers(name_of(label), label, pair_at, m.pairs);
    if (coupling) put(m.couplings, coupling->name, *coupling);
  }
  m.name = name_of(top);
  return m;
}

// --- mechanism.block ---

// numpy's dot of two 3-vectors (its float64 dot is a chain of fused multiply-adds), and linalg.norm (sqrt of the dot).
double dot3(const double a[3], const double b[3]) { return std::fma(a[2], b[2], std::fma(a[1], b[1], a[0] * b[0])); }

// mechanism.frame_matrix: Z the axis, X the ref_direction made normal to Z, Y their cross product.
std::array<double, 16> frame_matrix(const std::vector<double>& ax2) {
  double z[3] = {ax2[3], ax2[4], ax2[5]}, x[3] = {ax2[6], ax2[7], ax2[8]};
  double nz = std::sqrt(dot3(z, z));
  for (double& c : z) c /= nz;
  double d = dot3(x, z);
  for (int i = 0; i < 3; ++i) x[i] -= d * z[i];
  double nx = std::sqrt(dot3(x, x));
  for (double& c : x) c /= nx;
  double y[3] = {z[1] * x[2] - z[2] * x[1], z[2] * x[0] - z[0] * x[2], z[0] * x[1] - z[1] * x[0]};
  // Column-major: X, Y, Z, origin.
  return {x[0], x[1], x[2], 0, y[0], y[1], y[2], 0, z[0], z[1], z[2], 0, ax2[0], ax2[1], ax2[2], 1};
}

// mechanism._tree's loop (and _loop): the pairs that close one, or none.
std::optional<std::vector<std::string>> loop_of(const Mechanism& m) {
  std::map<int, std::optional<int>> via{{m.ground, std::nullopt}};
  std::set<int> reached{m.ground};
  std::deque<int> queue{m.ground};
  std::set<size_t> used;
  std::optional<std::vector<std::string>> loop;
  auto chain = [&](int link) {
    std::vector<int> found;
    while (via.count(link) && via[link]) {
      int at = *via[link];
      found.push_back(at);
      const Pair& pair = m.pairs[at];
      link = pair.links[1] == link ? pair.links[0] : pair.links[1];
    }
    return found;
  };
  while (!queue.empty()) {
    int link = queue.front();
    queue.pop_front();
    for (size_t at = 0; at < m.pairs.size(); ++at) {
      const Pair& pair = m.pairs[at];
      if (used.count(at) || (pair.links[0] != link && pair.links[1] != link) || pair.links[0] == pair.links[1]) continue;
      used.insert(at);
      int other = pair.links[0] == link ? pair.links[1] : pair.links[0];
      if (reached.count(other)) {
        if (!loop) {
          std::vector<int> left = chain(link), right = chain(other);
          while (!left.empty() && !right.empty() && left.back() == right.back()) {
            left.pop_back();
            right.pop_back();
          }
          std::vector<std::string> labels;
          for (int i : left) labels.push_back(m.pairs[i].label);
          labels.push_back(m.pairs[at].label);
          for (auto i = right.rbegin(); i != right.rend(); ++i) labels.push_back(m.pairs[*i].label);
          loop = labels;
        }
        continue;
      }
      reached.insert(other);
      via[other] = (int)at;
      queue.push_back(other);
    }
  }
  return loop;
}

void json_value(Json& out, const Values& values) {
  if (values.size() == 1) {
    out.num(values[0]);
    return;
  }
  out.open_list();
  for (double v : values) out.num(v);
  out.close_list();
}

void state_json(Json& out, const State& state) {
  out.open();
  for (const auto& [label, values] : state) {
    out.key(label);
    json_value(out, values);
  }
  out.close();
}

void optional_num(Json& out, std::optional<double> value) {
  if (value) out.num(*value); else out.null();
}

}  // namespace

std::optional<std::string> kinematics(const TDF_Label& main, const std::map<std::string, Occurrence>& occurrences,
                                      const std::vector<Occurrence>& instance_paths,
                                      const std::map<Occurrence, std::array<double, 16>>& worlds) {
  std::optional<Mechanism> found = read(main, occurrences);
  if (!found) return std::nullopt;
  const Mechanism& m = *found;
  std::map<Occurrence, int> owner;
  for (size_t at = 0; at < m.links.size(); ++at)
    for (const Occurrence& path : m.links[at].members) owner[path] = (int)at;
  std::vector<std::vector<int>> members(m.links.size());
  if (!m.links.empty()) {
    for (size_t index = 0; index < instance_paths.size(); ++index) {
      const Occurrence& path = instance_paths[index];
      int holder = m.ground;
      for (int depth = (int)path.size(); depth >= 0; --depth) {
        auto held = owner.find(Occurrence(path.begin(), path.begin() + depth));
        if (held != owner.end()) { holder = held->second; break; }
      }
      if (holder >= 0 && holder < (int)members.size()) members[holder].push_back((int)index);
    }
  }
  std::optional<std::vector<std::string>> loop = loop_of(m);
  Json out;
  out.open().key("schema").str(SCHEMA).key("name").str(m.name).key("ground").integer(m.ground);
  out.key("links").open_list();
  for (size_t at = 0; at < m.links.size(); ++at) {
    const Link& link = m.links[at];
    out.open().key("name").str(link.name).key("instances").open_list();
    for (int i : members[at]) out.integer(i);
    out.close_list().key("matrix").open_list();
    std::array<double, 16> matrix = {1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1};
    if (!link.members.empty()) {
      auto world = worlds.find(link.members[0]);
      if (world == worlds.end()) throw std::runtime_error("a mechanism's link names no occurrence of the document");
      matrix = world->second;
    }
    for (double v : matrix) out.num(v);
    out.close_list().close();
  }
  out.close_list().key("pairs").open_list();
  for (const Pair& pair : m.pairs) {
    out.open().key("label").str(pair.label).key("type").str(pair.kind->name);
    out.key("links").open_list().integer(pair.links[0]).integer(pair.links[1]).close_list();
    out.key("frames");
    if (pair.frames) {
      out.open_list();
      for (const std::vector<double>& frame : *pair.frames) {
        if (frame.size() < 9) throw std::runtime_error("a pair's frame is no AXIS2_PLACEMENT_3D");
        out.open_list();
        for (double v : frame_matrix(frame)) out.num(v);
        out.close_list();
      }
      out.close_list();
    } else {
      out.null();
    }
    out.key("limits").open_list();
    for (const Limit& limit : pair.limits) {
      out.open_list();
      optional_num(out, limit.first);
      optional_num(out, limit.second);
      out.close_list();
    }
    out.close_list().key("units").open_list();
    for (const Dof& dof : pair.kind->dofs) out.str(dof.unit);
    out.close_list().close();
  }
  out.close_list().key("asBuilt");
  state_json(out, m.as_built);
  out.key("configurations").open();
  for (const auto& [name, state] : m.configurations) {
    out.key(name);
    state_json(out, state);
  }
  out.close().key("couplings").open();
  for (const auto& [name, coupling] : m.couplings) {
    // mechanism._coupling_json and _derived_range
    double lower = -std::numeric_limits<double>::infinity(), upper = std::numeric_limits<double>::infinity();
    for (const auto& [label, ratios] : coupling.ratios) {
      const Pair* pair = nullptr;
      for (const Pair& p : m.pairs)
        if (p.label == label) pair = &p;
      Values built(ratios.size(), 0.0);
      for (const auto& [held, values] : m.as_built)
        if (held == label) built = values;
      for (size_t index = 0; index < ratios.size(); ++index) {
        double ratio = ratios[index];
        if (!ratio || index >= pair->limits.size()) continue;
        std::optional<double> ends[2];
        const std::optional<double> bounds[2] = {pair->limits[index].first, pair->limits[index].second};
        for (int i = 0; i < 2; ++i)
          if (bounds[i]) ends[i] = (*bounds[i] - built[index]) / ratio;
        if (ratio < 0) std::swap(ends[0], ends[1]);
        if (ends[0]) lower = std::max(lower, *ends[0]);
        if (ends[1]) upper = std::min(upper, *ends[1]);
      }
    }
    out.key(name).open().key("range").open_list();
    for (double end : {lower, upper}) {
      if (std::isinf(end)) out.null(); else out.num(std::fabs(end) < 1e-9 ? 0.0 : end);
    }
    out.close_list().key("terms").open_list();
    for (const Pair& pair : m.pairs) {
      for (const auto& [label, ratios] : coupling.ratios) {
        if (label != pair.label) continue;
        for (size_t index = 0; index < ratios.size(); ++index)
          out.open_list().str(label).integer((long long)index).num(ratios[index]).close_list();
      }
    }
    out.close_list().close();
  }
  out.close().key("motions").open();
  for (const auto& [name, motion] : m.motions) {
    out.key(name).open().key("duration").num(motion.keys.empty() ? 0.0 : motion.keys.back().t);
    out.key("ease").str(motion.ease).key("keys").open_list();
    for (const Key& key : motion.keys) {
      out.open().key("t").num(key.t);
      if (key.configuration) {
        out.key("configuration").str(*key.configuration);
      } else {
        out.key("values");
        state_json(out, key.values);
      }
      out.close();
    }
    out.close_list().close();
  }
  out.close().key("loop");
  if (loop) {
    out.open_list();
    for (const std::string& label : *loop) out.str(label);
    out.close_list();
  } else {
    out.null();
  }
  out.key("warnings").open_list();
  if (loop) {
    std::string joined;
    for (size_t i = 0; i < loop->size(); ++i) joined += (i ? ", " : "") + (*loop)[i];
    out.str("pairs " + joined + " close a loop, which has no pose without a solver: posing them is refused");
  }
  out.close_list().close();
  return out.out;
}

}  // namespace vc
