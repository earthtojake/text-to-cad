// glb_motion.cpp: the GLB's node tree (glb._tree), and its clips: every configuration sequence baked by forward
// kinematics (export/motion.py, through mechanism.Timeline and LinkWorlds), every animation() the document records
// (export/animation.py), each track written as the fewest LINEAR keys within a tenth of a millimetre and of a degree
// (export/keys.py), as glb._animations writes them.
#include <algorithm>
#include <cmath>
#include <functional>
#include <cstring>
#include <limits>
#include <memory>
#include <set>
#include <stdexcept>
#include <tuple>

#include "glb.hpp"

namespace vc {
namespace glb {

namespace {

bool allclose(const Mat4& a, const Mat4& b, double atol) {
  for (int i = 0; i < 16; ++i)
    if (!(std::fabs(a[i] - b[i]) <= atol)) return false;
  return true;
}

std::vector<std::string> split(const std::string& path) {
  std::vector<std::string> found;
  size_t start = 0;
  while (true) {
    size_t slash = path.find('/', start);
    found.push_back(path.substr(start, slash == std::string::npos ? std::string::npos : slash - start));
    if (slash == std::string::npos) return found;
    start = slash + 1;
  }
}

std::string joined(const std::vector<std::string>& names, size_t from) {
  std::string found;
  for (size_t i = from; i < names.size(); ++i) found += (i > from ? "/" : "") + names[i];
  return found;
}

}  // namespace

Tree build_tree(const Document& doc, const std::map<int, int>& drawn) {
  Tree tree;
  const double ROT = std::sqrt(0.5);
  Value root = object();
  root.keys.emplace_back("name", string(doc.name));
  double rotation[4] = {-ROT, 0.0, 0.0, ROT}, scale[3] = {0.001, 0.001, 0.001};
  root.keys.emplace_back("rotation", reals(rotation, 4));
  root.keys.emplace_back("scale", reals(scale, 3));
  root.keys.emplace_back("children", list());
  tree.nodes.push_back(root);

  std::function<void(const Value&, std::vector<int>&)> members = [&](const Value& node, std::vector<int>& out) {
    const Value* children = node.get("children");
    if (!children) {
      int instance = (int)node.get("instance")->number();
      if (drawn.count(instance)) out.push_back(instance);
      return;
    }
    for (const Value& child : children->items) members(child, out);
  };

  std::function<void(const Value&, const Occurrence&, const std::vector<std::string>&, int, const Mat4&)> visit =
      [&](const Value& node, const Occurrence& path, const std::vector<std::string>& names, int parent,
          const Mat4& within) {
        std::vector<int> under;
        members(node, under);
        if (under.empty()) return;
        auto given = doc.locals.find(path);
        Mat4 local = given == doc.locals.end() ? eye() : from_column(given->second.data());
        const Value* children = node.get("children");
        std::string name;
        Mat4 world;
        int instance = -1;
        if (children) {
          name = joined(names, 1);
          world = matmul(within, local);
        } else {
          instance = (int)node.get("instance")->number();
          const Instance& placed = doc.instances[instance];
          std::vector<std::string> placed_path = split(placed.path);
          name = joined(placed_path, 1);
          if (name.empty()) name = placed_path.back();
          world = from_column(placed.matrix);
          // A part stands where the document places it: at its own placement in its assembly where that puts it
          // there, else where its instance stands, in its assembly's frame.
          if (given == doc.locals.end() || !allclose(matmul(within, local), world, 1e-9))
            local = within == eye() ? world : matmul(inverse(within), world);
        }
        Value entry = object();
        entry.keys.emplace_back("name", string(name));
        if (!children) entry.keys.emplace_back("mesh", integer(drawn.at(instance)));
        if (local != eye()) {
          double column[16];
          for (int r = 0; r < 4; ++r)
            for (int c = 0; c < 4; ++c) column[c * 4 + r] = local[r * 4 + c];
          entry.keys.emplace_back("matrix", reals(column, 16));
        }
        tree.nodes.push_back(entry);
        int index = (int)tree.nodes.size() - 1;
        setdefault(tree.nodes[parent], "children", list()).items.push_back(integer(index));
        Target target;
        target.node = index;
        target.parent = parent == 0 ? -1 : parent;
        target.members = under;
        target.instance = instance;
        target.matrix = world;
        target.within = within;
        target.name = name;
        tree.targets.push_back(target);
        if (children) {
          for (size_t at = 0; at < children->items.size(); ++at) {
            Occurrence inner = path;
            inner.push_back((int)at);
            std::vector<std::string> inner_names = names;
            inner_names.push_back(children->items[at].get("name")->text);
            visit(children->items[at], inner, inner_names, index, world);
          }
        }
      };

  const Value* children = doc.tree.get("children");
  const std::string& top = doc.tree.get("name")->text;
  if (children) {
    for (size_t at = 0; at < children->items.size(); ++at)
      visit(children->items[at], Occurrence{(int)at}, {top, children->items[at].get("name")->text}, 0, eye());
  } else {
    visit(doc.tree, Occurrence{}, {top}, 0, eye());
  }
  return tree;
}

// --- numpy's linear algebra on 4x4s ----------------------------------------------------------------------------

// np.linalg.inv: LAPACK's dgesv (A X = I) as numpy's OpenBLAS runs it: a left-looking (Crout) LU with partial pivoting,
// each entry less its dot product (fused multiply-adds from zero), a column scaled by its pivot's reciprocal; then
// X solved a column at a time, forward through L and back through U (fused updates, the diagonal's reciprocal).
Mat4 inverse(const Mat4& m) {
  double a[4][4];
  for (int r = 0; r < 4; ++r)
    for (int c = 0; c < 4; ++c) a[r][c] = m[r * 4 + c];
  int perm[4];
  for (int j = 0; j < 4; ++j) {
    double b[4];
    for (int i = 0; i < 4; ++i) b[i] = a[i][j];
    for (int i = 1; i < j; ++i) {
      double s = 0.0;
      for (int k = 0; k < i; ++k) s = std::fma(a[i][k], b[k], s);
      b[i] -= s;
    }
    for (int i = j; i < 4; ++i) {
      double s = 0.0;
      for (int k = 0; k < j; ++k) s = std::fma(a[i][k], b[k], s);
      b[i] -= s;
    }
    int p = j;
    for (int i = j + 1; i < 4; ++i)
      if (std::fabs(b[i]) > std::fabs(b[p])) p = i;
    perm[j] = p;
    for (int i = 0; i < 4; ++i) a[i][j] = b[i];
    if (p != j)
      for (int c = 0; c < 4; ++c) std::swap(a[j][c], a[p][c]);
    if (a[j][j] == 0) throw std::runtime_error("a singular matrix in the mechanism");
    if (j < 3) {
      double r = 1.0 / a[j][j];
      for (int i = j + 1; i < 4; ++i) a[i][j] *= r;
    }
  }
  double x[4][4];
  for (int r = 0; r < 4; ++r)
    for (int c = 0; c < 4; ++c) x[r][c] = r == c ? 1.0 : 0.0;
  for (int j = 0; j < 4; ++j)
    if (perm[j] != j)
      for (int c = 0; c < 4; ++c) std::swap(x[j][c], x[perm[j]][c]);
  for (int c = 0; c < 4; ++c) {
    double v[4];
    for (int i = 0; i < 4; ++i) v[i] = x[i][c];
    for (int j = 0; j < 4; ++j)
      for (int i = j + 1; i < 4; ++i) v[i] = std::fma(-a[i][j], v[j], v[i]);
    for (int j = 3; j >= 0; --j) {
      v[j] = v[j] * (1.0 / a[j][j]);
      for (int i = 0; i < j; ++i) v[i] = std::fma(-a[i][j], v[j], v[i]);
    }
    for (int i = 0; i < 4; ++i) x[i][c] = v[i];
  }
  Mat4 found;
  for (int r = 0; r < 4; ++r)
    for (int c = 0; c < 4; ++c) found[r * 4 + c] = x[r][c];
  return found;
}

namespace {

using Vec = std::vector<double>;
constexpr double PI = 3.141592653589793;
const double DEG = PI / 180.0;  // math.radians' factor
const double INF = std::numeric_limits<double>::infinity();

double dot_fma(const double* a, const double* b, int n) {  // np.dot of 1-D vectors
  double s = a[0] * b[0];
  for (int k = 1; k < n; ++k) s = std::fma(a[k], b[k], s);
  return s;
}
double norm_fma(const double* a, int n) { return std::sqrt(dot_fma(a, a, n)); }  // np.linalg.norm of a 1-D vector
double sum_axis(const double* a, const double* b, int n) {  // np.sum(a * b, axis=-1)
  double s = a[0] * b[0];
  for (int k = 1; k < n; ++k) s = s + a[k] * b[k];
  return s;
}
double norm_axis(const double* a, int n) { return std::sqrt(sum_axis(a, a, n)); }  // np.linalg.norm(..., axis=-1)

// motion.quaternions: a rotation matrix's unit quaternion (x, y, z, w), w >= 0, Shepperd's method.
std::array<double, 4> quaternion(const Mat4& m) {
  auto M = [&](int r, int c) { return m[r * 4 + c]; };
  double d0 = M(0, 0), d1 = M(1, 1), d2 = M(2, 2);
  double trace = (d0 + d1) + d2;
  std::array<double, 4> q;
  if (trace > 0) {
    double s = std::sqrt(trace + 1.0) * 2;
    q = {(M(2, 1) - M(1, 2)) / s, (M(0, 2) - M(2, 0)) / s, (M(1, 0) - M(0, 1)) / s, 0.25 * s};
  } else if (d0 > d1 && d0 > d2) {
    double s = std::sqrt(((1.0 + d0) - d1) - d2) * 2;
    q = {0.25 * s, (M(0, 1) + M(1, 0)) / s, (M(0, 2) + M(2, 0)) / s, (M(2, 1) - M(1, 2)) / s};
  } else if (d1 > d2) {
    double s = std::sqrt(((1.0 + d1) - d0) - d2) * 2;
    q = {(M(0, 1) + M(1, 0)) / s, 0.25 * s, (M(1, 2) + M(2, 1)) / s, (M(0, 2) - M(2, 0)) / s};
  } else {
    double s = std::sqrt(((1.0 + d2) - d0) - d1) * 2;
    q = {(M(0, 2) + M(2, 0)) / s, (M(1, 2) + M(2, 1)) / s, 0.25 * s, (M(1, 0) - M(0, 1)) / s};
  }
  double length = std::sqrt(dot_fma(q.data(), q.data(), 4));
  for (double& v : q) v = v / length;
  if (q[3] < 0)
    for (double& v : q) v = -v;
  return q;
}

// Python's float ** 3 and ** 2 (C's pow).
double cube(double s) { return std::pow(s, 3.0); }
double square(double s) { return std::pow(s, 2.0); }

// motion.hermite: glTF's CUBICSPLINE between two keys (rows in-tangent, value, out-tangent), at fraction s of span.
Vec hermite(const Vec* first, const Vec* second, double span, double s) {
  double a = (2 * cube(s) - 3 * square(s)) + 1;
  double b = span * ((cube(s) - 2 * square(s)) + s);
  double c = -2 * cube(s) + 3 * square(s);
  double d = span * (cube(s) - square(s));
  Vec found(first[1].size());
  for (size_t i = 0; i < found.size(); ++i)
    found[i] = ((a * first[1][i] + b * first[2][i]) + c * second[1][i]) + d * second[0][i];
  return found;
}

// --- the structure's kinematics ---------------------------------------------------------------------------------

struct Limit { double low, high; std::optional<double> lower, upper; };

struct KPair {
  std::string label, type;
  int links[2];
  bool framed = false;
  Mat4 frames[2];
  std::vector<std::pair<std::optional<double>, std::optional<double>>> limits;
};

struct KCoupling {
  std::optional<double> lower, upper;
  std::vector<std::tuple<std::string, int, double>> terms;
};

struct Kinematics {
  std::vector<std::vector<int>> link_instances;
  std::vector<Mat4> built;
  std::vector<KPair> pairs;
  std::map<std::string, int> pair_at;
  int ground = 0;
  std::map<std::string, Vec> as_built;
  std::vector<std::string> as_built_order;
  std::map<std::string, const Value*> configurations;
  std::map<std::string, KCoupling> couplings;
  std::vector<std::pair<std::string, const Value*>> motions;
  std::set<std::string> loop;
  Value source;  // the parsed block the pointers point into
};

std::optional<double> optional_number(const Value* v) {
  if (!v || v->kind == Value::NUL) return std::nullopt;
  return v->number();
}

// mechanism._as_tuple
Vec as_tuple(const Value& v) {
  if (v.is_number()) return {v.number()};
  Vec found;
  for (const Value& item : v.items) found.push_back(item.number());
  return found;
}

std::unique_ptr<Kinematics> read_kinematics(const std::string& text) {
  auto k = std::make_unique<Kinematics>();
  k->source = Value::parse(text);
  const Value& block = k->source;
  for (const Value& link : block.get("links")->items) {
    std::vector<int> instances;
    for (const Value& i : link.get("instances")->items) instances.push_back((int)i.number());
    k->link_instances.push_back(instances);
    double column[16];
    for (int i = 0; i < 16; ++i) column[i] = link.get("matrix")->items[i].number();
    k->built.push_back(from_column(column));
  }
  for (const Value& pair : block.get("pairs")->items) {
    KPair p;
    p.label = pair.get("label")->text;
    p.type = pair.get("type")->text;
    p.links[0] = (int)pair.get("links")->items[0].number();
    p.links[1] = (int)pair.get("links")->items[1].number();
    const Value* frames = pair.get("frames");
    if (frames && frames->kind == Value::LIST && !frames->items.empty()) {
      p.framed = true;
      for (int f = 0; f < 2; ++f) {
        double column[16];
        for (int i = 0; i < 16; ++i) column[i] = frames->items[f].items[i].number();
        p.frames[f] = from_column(column);
      }
    }
    if (const Value* limits = pair.get("limits"))
      for (const Value& limit : limits->items)
        p.limits.emplace_back(optional_number(&limit.items[0]), optional_number(&limit.items[1]));
    k->pair_at[p.label] = (int)k->pairs.size();
    k->pairs.push_back(p);
  }
  const Value* ground = block.get("ground");
  k->ground = ground && ground->is_number() ? (int)ground->number() : 0;
  for (const auto& [label, value] : block.get("asBuilt")->keys) {
    k->as_built[label] = as_tuple(value);
    k->as_built_order.push_back(label);
  }
  if (const Value* configurations = block.get("configurations"))
    for (const auto& [name, value] : configurations->keys) k->configurations[name] = &value;
  if (const Value* couplings = block.get("couplings"))
    for (const auto& [name, value] : couplings->keys) {
      KCoupling c;
      const Value* range = value.get("range");
      if (range && range->kind == Value::LIST && range->items.size() == 2) {
        c.lower = optional_number(&range->items[0]);
        c.upper = optional_number(&range->items[1]);
      }
      for (const Value& term : value.get("terms")->items)
        c.terms.emplace_back(term.items[0].text, (int)term.items[1].number(), term.items[2].number());
      k->couplings[name] = c;
    }
  if (const Value* motions = block.get("motions"))
    for (const auto& [name, value] : motions->keys) k->motions.emplace_back(name, &value);
  if (const Value* loop = block.get("loop"); loop && loop->kind == Value::LIST)
    for (const Value& label : loop->items) k->loop.insert(label.text);
  return k;
}

size_t dofs(const KPair& p) {
  if (p.type == "cylindrical") return 2;
  if (p.type == "spherical") return 3;
  return 1;
}

bool within(double value, const std::optional<double>& lower, const std::optional<double>& upper) {
  const double slack = 1e-9;
  return (!lower || value >= *lower - slack) && (!upper || value <= *upper + slack);
}

// mechanism._number_values
std::optional<Vec> number_values(const Value& v) {
  if (v.kind == Value::BOOL) return std::nullopt;
  if (v.is_number()) return Vec{v.number()};
  if (v.kind != Value::LIST || v.items.empty()) return std::nullopt;
  Vec found;
  for (const Value& item : v.items) {
    if (!item.is_number()) return std::nullopt;
    found.push_back(item.number());
  }
  return found;
}

// mechanism._checked
Vec checked(const KPair& pair, const Vec& found) {
  if (found.size() != dofs(pair)) throw std::runtime_error("joint '" + pair.label + "' takes " + std::to_string(dofs(pair)) + " values");
  for (size_t i = 0; i < found.size(); ++i) {
    if (!std::isfinite(found[i])) throw std::runtime_error("joint '" + pair.label + "' takes finite values");
    if (i < pair.limits.size() && !within(found[i], pair.limits[i].first, pair.limits[i].second))
      throw std::runtime_error("joint '" + pair.label + "' is outside its range");
  }
  return found;
}

using Values = std::map<std::string, Vec>;

// mechanism.resolve(kinematics, given, own=True): the values a pose sets every pair to, given joint values (by label,
// numbers) and coupling values.
Values resolve(const Kinematics& k, const std::vector<std::pair<std::string, Vec>>& given) {
  Values values = k.as_built;
  std::vector<std::pair<std::string, double>> controls;
  std::set<std::string> named;
  for (const auto& [label, value] : given) {
    named.insert(label);
    auto pair = k.pair_at.find(label);
    if (pair == k.pair_at.end()) {
      auto coupling = k.couplings.find(label);
      if (coupling == k.couplings.end()) throw std::runtime_error("the pose names no joint '" + label + "'");
      if (value.size() != 1 || !std::isfinite(value[0])) throw std::runtime_error("coupling '" + label + "' takes a number");
      controls.emplace_back(label, value[0]);
      continue;
    }
    if (k.loop.count(label)) throw std::runtime_error("joint '" + label + "' closes a loop and cannot be posed");
    values[label] = checked(k.pairs[pair->second], value);
  }
  std::map<std::string, Vec> moved;
  for (const auto& [name, value] : controls) {
    const KCoupling& c = k.couplings.at(name);
    if (!within(value, c.lower, c.upper)) throw std::runtime_error("coupling '" + name + "' is outside its range");
    for (const auto& [label, index, ratio] : c.terms) {
      if (named.count(label)) throw std::runtime_error("a pose sets a coupling and its joint");
      auto row = moved.find(label);
      if (row == moved.end()) row = moved.emplace(label, k.as_built.at(label)).first;
      row->second[index] += ratio * value;
    }
  }
  for (const auto& [label, row] : moved) values[label] = checked(k.pairs[k.pair_at.at(label)], row);
  return values;
}

std::vector<std::pair<std::string, Vec>> given_of(const Value& object_) {
  std::vector<std::pair<std::string, Vec>> found;
  for (const auto& [label, value] : object_.keys) {
    auto numbers = number_values(value);
    if (!numbers) throw std::runtime_error("joint '" + label + "' takes numbers");
    found.emplace_back(label, *numbers);
  }
  return found;
}

// mechanism._rotation and pair_motion: what a pair's value does between its two frames.
Mat4 rotation_about(int axis, double degrees) {
  double angle = degrees * DEG, c = std::cos(angle), s = std::sin(angle);
  Mat4 found = eye();
  static const int IJ[3][2] = {{1, 2}, {2, 0}, {0, 1}};
  int i = IJ[axis][0], j = IJ[axis][1];
  found[i * 4 + i] = c;
  found[i * 4 + j] = -s;
  found[j * 4 + i] = s;
  found[j * 4 + j] = c;
  return found;
}

Mat4 pair_motion(const std::string& kind, const Vec& values) {
  if (kind == "revolute") return rotation_about(2, values[0]);
  if (kind == "prismatic") { Mat4 m = eye(); m[2 * 4 + 3] = values[0]; return m; }
  if (kind == "cylindrical") { Mat4 m = rotation_about(2, values[0]); m[2 * 4 + 3] = values[1]; return m; }
  if (kind == "spherical")
    return matmul(matmul(rotation_about(0, values[0]), rotation_about(1, values[1])), rotation_about(2, values[2]));
  throw std::runtime_error("a " + kind + " pair has no value");
}

// mechanism.LinkWorlds: each link's placement at given values, the pairs followed from the ground.
class LinkWorlds {
 public:
  explicit LinkWorlds(const Kinematics& k) : k_(k) {
    for (size_t at = 0; at < k.pairs.size(); ++at)
      if (k.pairs[at].framed) pairs_.push_back((int)at);
    for (int at : pairs_) {
      const KPair& pair = k.pairs[at];
      posed_.push_back({pair.frames[0], inverse(pair.frames[1]), pair.frames[1], inverse(pair.frames[0])});
      Mat4 item_1 = inverse(k.built[pair.links[0]]), item_2 = inverse(k.built[pair.links[1]]);
      held_.push_back({item_1, inverse(item_2), item_2, inverse(item_1)});
    }
  }

  std::vector<Mat4> operator()(const Values& values) {
    size_t count = k_.built.size();
    if (!count) return {};
    std::set<std::string> valued;
    for (int at : pairs_)
      if (values.count(k_.pairs[at].label)) valued.insert(k_.pairs[at].label);
    auto steps = orders_.find(valued);
    if (steps == orders_.end()) steps = orders_.emplace(valued, order(valued)).first;
    std::vector<std::optional<Mat4>> found(count);
    found[k_.ground] = k_.built[k_.ground];
    for (const auto& [at, forward, posed] : steps->second) {
      const KPair& pair = k_.pairs[pairs_[at]];
      int first = pair.links[0], second = pair.links[1];
      const std::array<Mat4, 4>& items = posed ? posed_[at] : held_[at];
      Mat4 moved = posed ? pair_motion(pair.type, values.at(pair.label)) : eye();
      if (forward)
        found[second] = matmul(matmul(matmul(*found[first], items[0]), moved), items[1]);
      else
        found[first] = matmul(matmul(matmul(*found[second], items[2]), inverse(moved)), items[3]);
    }
    std::vector<Mat4> worlds;
    for (size_t at = 0; at < count; ++at) worlds.push_back(found[at] ? *found[at] : k_.built[at]);
    return worlds;
  }

 private:
  const Kinematics& k_;
  std::vector<int> pairs_;
  std::vector<std::array<Mat4, 4>> posed_, held_;
  std::map<std::set<std::string>, std::vector<std::tuple<int, bool, bool>>> orders_;

  std::vector<std::tuple<int, bool, bool>> order(const std::set<std::string>& valued) const {
    std::vector<bool> found(k_.built.size(), false);
    found[k_.ground] = true;
    std::vector<int> pending;
    for (size_t at = 0; at < pairs_.size(); ++at) pending.push_back((int)at);
    std::vector<std::tuple<int, bool, bool>> steps;
    bool progress = true;
    while (!pending.empty() && progress) {
      progress = false;
      std::vector<int> snapshot = pending;
      for (int at : snapshot) {
        const KPair& pair = k_.pairs[pairs_[at]];
        int first = pair.links[0], second = pair.links[1];
        bool is_valued = valued.count(pair.label) > 0;
        if (found[first] && !found[second]) {
          steps.emplace_back(at, true, is_valued);
          found[second] = true;
        } else if (found[second] && !found[first]) {
          steps.emplace_back(at, false, is_valued);
          found[first] = true;
        } else if (!found[first]) {
          continue;
        }
        pending.erase(std::find(pending.begin(), pending.end(), at));
        progress = true;
      }
    }
    return steps;
  }
};

// mechanism._interpolated: values at t between keys, linear or cubic (each step eased in and out).
Vec interpolated(const Vec& times, const std::vector<Vec>& table, const std::string& ease, double t) {
  if (t <= times[0]) return table[0];
  if (t >= times.back()) return table.back();
  int at = (int)(std::upper_bound(times.begin(), times.end(), t) - times.begin()) - 1;
  at = std::min(at, (int)times.size() - 2);
  double span = times[at + 1] - times[at];
  double s = (t - times[at]) / span;
  Vec found(table[at].size());
  if (ease == "linear") {
    for (size_t i = 0; i < found.size(); ++i) found[i] = table[at][i] + s * (table[at + 1][i] - table[at][i]);
  } else {
    double w = s * s * (3.0 - 2.0 * s);
    for (size_t i = 0; i < found.size(); ++i) found[i] = table[at][i] + w * (table[at + 1][i] - table[at][i]);
  }
  return found;
}

// mechanism.Timeline: a motion's pair values over its clip.
struct Timeline {
  const Kinematics& k;
  std::string ease;
  Vec times;
  double duration = 0;
  std::vector<std::string> labels;
  std::vector<size_t> sizes;
  std::vector<Vec> table;
  Vec lower, upper;

  Timeline(const Kinematics& kin, const Value& entry) : k(kin) {
    ease = entry.get("ease")->text;
    std::set<std::string> moving;
    std::vector<Values> poses;
    for (const Value& key : entry.get("keys")->items) {
      times.push_back(key.get("t")->number());
      if (const Value* configuration = key.get("configuration")) {
        const Value& given = *k.configurations.at(configuration->text);
        for (const auto& [label, _] : given.keys) moving.insert(label);
        poses.push_back(resolve(k, given_of(given)));
      } else {
        const Value& given = *key.get("values");
        for (const auto& [label, _] : given.keys) moving.insert(label);
        poses.push_back(resolve(k, given_of(given)));
      }
    }
    duration = times.back();
    labels.assign(moving.begin(), moving.end());
    for (const std::string& label : labels) sizes.push_back(poses[0].at(label).size());
    for (const Values& pose : poses) {
      Vec row;
      for (const std::string& label : labels)
        for (double v : pose.at(label)) row.push_back(v);
      table.push_back(row);
    }
    for (const std::string& label : labels)
      for (const auto& [low, high] : k.pairs[k.pair_at.at(label)].limits) {
        lower.push_back(low ? *low : -INF);
        upper.push_back(high ? *high : INF);
      }
  }

  Values values(double t) const {
    Vec flat = interpolated(times, table, ease, t);
    for (size_t i = 0; i < flat.size(); ++i) flat[i] = std::min(std::max(flat[i], lower[i]), upper[i]);
    std::vector<std::pair<std::string, Vec>> joints;
    size_t at = 0;
    for (size_t i = 0; i < labels.size(); ++i) {
      joints.emplace_back(labels[i], Vec(flat.begin() + at, flat.begin() + at + sizes[i]));
      at += sizes[i];
    }
    return resolve(k, joints);
  }
};

std::vector<Mat4> link_worlds(const Kinematics& k, const Values& values) { return LinkWorlds(k)(values); }

std::map<int, int> owners(const Kinematics& k) {
  std::map<int, int> found;
  for (size_t link = 0; link < k.link_instances.size(); ++link)
    for (int index : k.link_instances[link]) found[index] = (int)link;
  return found;
}

// A clip's signature of an instance (motion.chosen): what moves it, whether its node may carry others; none.
using Signature = std::optional<std::pair<std::string, bool>>;

// motion.chosen
std::vector<const Target*> chosen(const std::vector<Target>& targets, const std::function<Signature(int)>& signature) {
  std::set<int> covered;
  std::vector<const Target*> found;
  for (const Target& target : targets) {
    if (target.parent >= 0 && covered.count(target.parent)) {
      covered.insert(target.node);
      continue;
    }
    std::set<std::optional<std::pair<std::string, bool>>> signs;
    for (int index : target.members) signs.insert(signature(index));
    if (signs.size() != 1) continue;
    const Signature& sign = *signs.begin();
    if (!sign || (target.instance < 0 && !sign->second)) continue;
    found.push_back(&target);
    covered.insert(target.node);
  }
  return found;
}

bool near_eye(const Mat4& m) {
  Mat4 e = eye();
  for (int i = 0; i < 16; ++i)
    if (!(std::fabs(m[i] - e[i]) <= 1e-9)) return false;
  return true;
}

// --- motion.clips --------------------------------------------------------------------------------------------

// One key of a clip: per moving node, its translation's and rotation's (in-tangent, value, out-tangent).
struct KeyRows { std::vector<std::array<Vec, 3>> translation, rotation; };

struct Motion {
  const Kinematics& k;
  Timeline timeline;
  LinkWorlds worlds;
  std::vector<Mat4> unrest;
  std::map<int, int> owner;
  std::map<int, Mat4> base;
  std::vector<int> instances, links;

  Motion(const Kinematics& kin, const Value& entry, const std::vector<const Target*>& targets)
      : k(kin), timeline(kin, entry), worlds(kin) {
    for (const Mat4& matrix : link_worlds(k, k.as_built)) unrest.push_back(inverse(matrix));
    std::map<int, int> link_of = owners(k);
    for (const Target* target : targets) {
      std::set<int> found;
      bool none = false;
      for (int index : target->members) {
        auto at = link_of.find(index);
        if (at == link_of.end()) none = true; else found.insert(at->second);
      }
      if (!none && found.size() == 1) owner[target->node] = *found.begin();
    }
    for (const Target* target : targets)
      if (owner.count(target->node)) base[target->node] = target->matrix;
    std::set<int> moved;
    const Vec& breaks = timeline.times;
    Vec times(breaks.begin(), breaks.end());
    for (size_t i = 0; i + 1 < breaks.size(); ++i)
      for (double s : {0.25, 0.5, 0.75}) times.push_back(breaks[i] + (breaks[i + 1] - breaks[i]) * s);
    for (double t : times) {
      std::vector<Mat4> now = worlds(timeline.values(t));
      for (size_t link = 0; link < now.size(); ++link)
        if (!moved.count((int)link) && !near_eye(matmul(now[link], unrest[link]))) moved.insert((int)link);
    }
    std::set<int> linked;
    for (const Target* target : targets) {
      auto at = owner.find(target->node);
      if (at != owner.end() && moved.count(at->second)) {
        instances.push_back(target->node);
        linked.insert(at->second);
      }
    }
    links.assign(linked.begin(), linked.end());
  }

  // Every moving node's translation and rotation at t.
  void at(double t, std::vector<Vec>& translations, std::vector<Vec>& rotations) {
    translations.clear();
    rotations.clear();
    if (instances.empty()) return;
    std::vector<Mat4> now = worlds(timeline.values(t));
    std::map<int, Mat4> moved;
    for (int link : links) moved[link] = matmul(now[link], unrest[link]);
    for (int node : instances) {
      Mat4 m = matmul(moved[owner[node]], base[node]);
      translations.push_back({m[3], m[7], m[11]});
      auto q = quaternion(m);
      rotations.push_back(Vec(q.begin(), q.end()));
    }
  }
};

double sign_against(const Vec& a, const Vec& b) { return sum_axis(a.data(), b.data(), (int)a.size()) < 0 ? -1.0 : 1.0; }

// motion._Keys
struct ClipKeys {
  Motion& motion;
  double period, step;
  std::map<double, KeyRows> held;

  explicit ClipKeys(Motion& m) : motion(m), period(m.timeline.duration), step(1e-5 * m.timeline.duration) {}

  const KeyRows& key(double t) {
    auto found = held.find(t);
    if (found != held.end()) return found->second;
    std::vector<Vec> translation, rotation;
    motion.at(t, translation, rotation);
    double h = step;
    size_t n = translation.size();
    auto side = [&](double sign) {  // left (-1) or right (+1): one-sided derivatives
      std::vector<Vec> t1, r1, t2, r2;
      motion.at(t + sign * h, t1, r1);
      motion.at(t + sign * 2 * h, t2, r2);
      std::vector<Vec> dt(n), dr(n);
      for (size_t i = 0; i < n; ++i) {
        double s1 = sign_against(r1[i], rotation[i]), s2 = sign_against(r2[i], rotation[i]);
        dt[i].resize(3);
        dr[i].resize(4);
        for (int c = 0; c < 3; ++c)
          dt[i][c] = sign < 0 ? ((3 * translation[i][c] - 4 * t1[i][c]) + t2[i][c]) / (2 * h)
                              : ((-3 * translation[i][c] + 4 * t1[i][c]) - t2[i][c]) / (2 * h);
        for (int c = 0; c < 4; ++c) {
          double a = r1[i][c] * s1, b = r2[i][c] * s2;
          dr[i][c] = sign < 0 ? ((3 * rotation[i][c] - 4 * a) + b) / (2 * h) : ((-3 * rotation[i][c] + 4 * a) - b) / (2 * h);
        }
      }
      return std::make_pair(dt, dr);
    };
    std::optional<std::pair<std::vector<Vec>, std::vector<Vec>>> before, after;
    if (t - 2 * h >= 0) before = side(-1);
    if (t + 2 * h <= period) after = side(+1);
    if (!before) before = after;
    if (!after) after = before;
    KeyRows rows;
    for (size_t i = 0; i < n; ++i) {
      rows.translation.push_back({before->first[i], translation[i], after->first[i]});
      rows.rotation.push_back({before->second[i], rotation[i], after->second[i]});
    }
    return held[t] = rows;
  }
};

const double CHECKS[7] = {1 / 8.0, 2 / 8.0, 3 / 8.0, 4 / 8.0, 5 / 8.0, 6 / 8.0, 7 / 8.0};

// motion._deviation
std::pair<double, double> deviation(ClipKeys& keys, double a, double b) {
  KeyRows first = keys.key(a), second = keys.key(b);
  for (size_t i = 0; i < second.rotation.size(); ++i)
    if (sum_axis(first.rotation[i][1].data(), second.rotation[i][1].data(), 4) < 0)
      for (Vec& row : second.rotation[i])
        for (double& v : row) v = v * -1.0;
  double span = b - a, worst_t = 0, worst_r = 0;
  for (double s : CHECKS) {
    std::vector<Vec> translation, rotation;
    keys.motion.at(a + span * s, translation, rotation);
    for (size_t i = 0; i < translation.size(); ++i) {
      Vec got_t = hermite(first.translation[i].data(), second.translation[i].data(), span, s);
      Vec got_r = hermite(first.rotation[i].data(), second.rotation[i].data(), span, s);
      double length = norm_axis(got_r.data(), 4);
      for (double& v : got_r) v = v / length;
      Vec off(3);
      for (int c = 0; c < 3; ++c) off[c] = got_t[c] - translation[i][c];
      worst_t = std::max(worst_t, norm_axis(off.data(), 3));
      double dot = std::min(std::max(std::fabs(sum_axis(got_r.data(), rotation[i].data(), 4)), 0.0), 1.0);
      worst_r = std::max(worst_r, 2 * std::acos(dot));
    }
  }
  return {worst_t, worst_r};
}

struct Clip {
  std::string name;
  double duration;
  Vec times;
  std::vector<int> instances;
  std::vector<std::vector<std::array<Vec, 3>>> translations, rotations;  // per node, per key
};

std::vector<Clip> clips(const Kinematics& k, const std::vector<Target>& all, double size) {
  std::vector<const Target*> targets;
  std::map<int, int> link_of = owners(k);
  if (!k.motions.empty() && !all.empty())
    targets = chosen(all, [&](int index) -> Signature {
      auto at = link_of.find(index);
      if (at == link_of.end()) return std::nullopt;
      return std::make_pair(std::to_string(at->second), true);
    });
  std::vector<Clip> found;
  double linear = 1e-3 * std::max(1.0, size), angular = 1e-3;
  for (const auto& [name, entry] : k.motions) {
    Motion motion(k, *entry, targets);
    ClipKeys keys(motion);
    std::set<double> unique(motion.timeline.times.begin(), motion.timeline.times.end());
    Vec times(unique.begin(), unique.end());
    for (size_t i = 0; i + 1 < times.size(); ++i) unique.insert((times[i] + times[i + 1]) / 2);
    times.assign(unique.begin(), unique.end());
    if (!motion.instances.empty()) {
      while (true) {
        std::vector<double> split;
        for (size_t i = 0; i + 1 < times.size(); ++i) {
          auto [t_off, r_off] = deviation(keys, times[i], times[i + 1]);
          if (t_off > linear || r_off > angular) split.push_back((times[i] + times[i + 1]) / 2);
        }
        if (split.empty()) break;
        std::set<double> grown(times.begin(), times.end());
        grown.insert(split.begin(), split.end());
        if (grown.size() == times.size() || grown.size() > 4097)
          throw std::runtime_error("motion '" + name + "': its clip does not settle within the tolerance in 4097 keys");
        times.assign(grown.begin(), grown.end());
      }
    }
    Clip clip{name, motion.timeline.duration, times, motion.instances, {}, {}};
    if (!motion.instances.empty()) {
      std::vector<const KeyRows*> rows;
      for (double t : times) rows.push_back(&keys.key(t));
      for (size_t at = 0; at < motion.instances.size(); ++at) {
        std::vector<std::array<Vec, 3>> translations, rotations;
        for (const KeyRows* row : rows) {
          translations.push_back(row->translation[at]);
          rotations.push_back(row->rotation[at]);
        }
        for (size_t key = 1; key < rotations.size(); ++key)
          if (dot_fma(rotations[key][1].data(), rotations[key - 1][1].data(), 4) < 0)
            for (Vec& row : rotations[key])
              for (double& v : row) v = -v;
        clip.translations.push_back(translations);
        clip.rotations.push_back(rotations);
      }
    }
    found.push_back(clip);
  }
  return found;
}

// --- export/animation.py: the document's animation() records baked ---------------------------------------------

// animation._about: the rotation about a pivot as a 4x4.
Mat4 about(const double rotation[3][3], const double pivot[3]) {
  Mat4 m = eye();
  for (int r = 0; r < 3; ++r) {
    for (int c = 0; c < 3; ++c) m[r * 4 + c] = rotation[r][c];
    double turned = rotation[r][0] * pivot[0];
    turned = std::fma(rotation[r][1], pivot[1], turned);
    turned = std::fma(rotation[r][2], pivot[2], turned);
    m[r * 4 + 3] = pivot[r] - turned;
  }
  return m;
}

// animation._turn: the rigid turn by `radians` about the line through `pivot` along unit `axis`.
Mat4 turn(const Vec& axis, double radians, const Vec& pivot) {
  double x = axis[0], y = axis[1], z = axis[2];
  double c = std::cos(radians), s = std::sin(radians), k = 1.0 - std::cos(radians);
  double r[3][3] = {{c + x * x * k, x * y * k - z * s, x * z * k + y * s},
                    {y * x * k + z * s, c + y * y * k, y * z * k - x * s},
                    {z * x * k - y * s, z * y * k + x * s, c + z * z * k}};
  return about(r, pivot.data());
}

// animation._rotation: a quaternion's rotation matrix.
void rotation_of(const Vec& given, double r[3][3]) {
  double length = norm_fma(given.data(), 4);
  double x = given[0] / length, y = given[1] / length, z = given[2] / length, w = given[3] / length;
  double m[3][3] = {{1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)},
                    {2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)},
                    {2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)}};
  std::memcpy(r, m, sizeof m);
}

// animation._slerp
Vec slerp1(const Vec& a, Vec b, double s) {
  double dot = dot_fma(a.data(), b.data(), (int)a.size());
  if (dot < 0) {
    for (double& v : b) v = -v;
    dot = -dot;
  }
  Vec found(a.size());
  if (dot > 0.9995) {
    for (size_t i = 0; i < a.size(); ++i) found[i] = a[i] + s * (b[i] - a[i]);
    double length = norm_fma(found.data(), (int)found.size());
    for (double& v : found) v = v / length;
    return found;
  }
  double theta = std::acos(std::min(1.0, dot));
  double first = std::sin((1 - s) * theta), second = std::sin(s * theta), whole = std::sin(theta);
  for (size_t i = 0; i < a.size(); ++i) found[i] = (first * a[i] + second * b[i]) / whole;
  return found;
}

// animation._Keyed: one authored channel's curve.
struct Keyed {
  Vec times;
  std::vector<Vec> values;
  std::string interpolation;
  bool is_quaternion = false;

  Keyed(const std::vector<std::pair<double, Vec>>& keys, const std::string& how, bool q = false)
      : interpolation(how), is_quaternion(q) {
    for (const auto& [t, value] : keys) {
      times.push_back(t);
      values.push_back(value);
    }
    if (q)
      for (size_t at = 1; at < values.size(); ++at)
        if (dot_fma(values[at].data(), values[at - 1].data(), (int)values[at].size()) < 0)
          for (double& v : values[at]) v = -v;
  }
  double start() const { return times[0]; }
  const Vec& last() const { return values.back(); }
  std::optional<Vec> at(double t) const {
    if (t < times[0]) return std::nullopt;
    if (t >= times.back()) return values.back();
    int k = (int)(std::upper_bound(times.begin(), times.end(), t) - times.begin()) - 1;
    if (interpolation == "STEP") return values[k];
    double s = (t - times[k]) / (times[k + 1] - times[k]);
    const Vec &a = values[k], &b = values[k + 1];
    Vec found(a.size());
    if (interpolation == "LINEAR") {
      if (is_quaternion) return slerp1(a, b, s);
      for (size_t i = 0; i < a.size(); ++i) found[i] = a[i] + s * (b[i] - a[i]);
      return found;
    }
    double w = s * s * (3.0 - 2.0 * s);
    for (size_t i = 0; i < a.size(); ++i) found[i] = a[i] + w * (b[i] - a[i]);
    if (is_quaternion) {
      double length = norm_fma(found.data(), (int)found.size());
      for (double& v : found) v = v / length;
    }
    return found;
  }
};

// animation._Group: one reference's channels.
struct Group {
  std::vector<Occurrence> leaves;
  size_t size = 0;
  int first = 0;
  std::vector<Keyed> translations;
  struct Rotation { Keyed curve; std::optional<Vec> axis; Vec pivot; };
  std::vector<Rotation> rotations;
  std::vector<Keyed> scales;
  Vec centre = Vec(3, 0.0);

  Mat4 matrix(double t) const {
    Mat4 found = eye();
    for (const Rotation& r : rotations) {
      auto value = r.curve.at(t);
      if (!value) continue;
      Mat4 moved;
      if (r.axis) {
        moved = turn(*r.axis, (*value)[0] * DEG, r.pivot);
      } else {
        double m[3][3];
        rotation_of(*value, m);
        moved = about(m, r.pivot.data());
      }
      found = matmul(moved, found);
    }
    for (const Keyed& curve : translations) {
      auto value = curve.at(t);
      if (value)
        for (int c = 0; c < 3; ++c) found[c * 4 + 3] += (*value)[c];
    }
    return found;
  }
  double factor(double t) const {
    double value = 1.0;
    for (const Keyed& curve : scales) {
      auto found = curve.at(t);
      if (!found) break;
      value = (*found)[0];
    }
    return value;
  }
};

// animation._Pose: the mechanism over the animation.
struct PoseTrack { double start; std::string interpolation; Vec times; std::vector<Vec> rows; std::vector<double> key_times; };

struct Pose {
  const Kinematics& k;
  std::vector<PoseTrack> tracks;
  std::vector<std::string> labels;
  std::vector<size_t> sizes;
  std::vector<Mat4> unrest;
  std::map<double, std::vector<Mat4>> held;

  Pose(const Kinematics& kin, std::vector<PoseTrack> given) : k(kin), tracks(std::move(given)) {
    std::stable_sort(tracks.begin(), tracks.end(), [](const PoseTrack& a, const PoseTrack& b) { return a.start < b.start; });
    for (const auto& [label, _] : k.as_built) labels.push_back(label);  // a std::map: sorted
    for (const std::string& label : labels) sizes.push_back(k.as_built.at(label).size());
    for (const Mat4& matrix : link_worlds(k, k.as_built)) unrest.push_back(inverse(matrix));
  }

  Values values(double t) const {
    size_t at = 0;
    for (size_t index = 0; index < tracks.size(); ++index)
      if (tracks[index].start <= t) at = index;
    const PoseTrack& track = tracks[at];
    Vec row;
    if (track.interpolation == "STEP" || track.times.size() == 1) {
      int k_at = (int)(std::upper_bound(track.times.begin(), track.times.end(), t) - track.times.begin()) - 1;
      row = track.rows[std::max(0, k_at)];
    } else {
      row = interpolated(track.times, track.rows, track.interpolation == "CUBICSPLINE" ? "cubic" : "linear", t);
    }
    Values found;
    size_t offset = 0;
    for (size_t i = 0; i < labels.size(); ++i) {
      found[labels[i]] = Vec(row.begin() + offset, row.begin() + offset + sizes[i]);
      offset += sizes[i];
    }
    return found;
  }

  const std::vector<Mat4>& deltas(double t) {
    auto found = held.find(t);
    if (found != held.end()) return found->second;
    std::vector<Mat4> worlds = link_worlds(k, values(t)), moved;
    for (size_t i = 0; i < worlds.size(); ++i) moved.push_back(matmul(worlds[i], unrest[i]));
    return held[t] = moved;
  }

  Vec times() const {
    std::set<double> found;
    for (const PoseTrack& track : tracks) found.insert(track.times.begin(), track.times.end());
    return Vec(found.begin(), found.end());
  }
};

Vec numbers(const Value& v) {
  if (v.is_number()) return {v.number()};
  Vec found;
  for (const Value& item : v.items) found.push_back(item.number());
  return found;
}

Occurrence occurrence_of(const Value& v) {
  Occurrence found;
  for (const Value& item : v.items) found.push_back((int)item.number());
  return found;
}

std::vector<std::pair<double, Vec>> ramp(const std::vector<std::pair<double, Vec>>& keys, const Vec& first, const Vec& last) {
  if (keys.size() == 1) return {{keys[0].first, last}};
  return {{keys[0].first, first}, {keys.back().first, last}};
}

// placed_points of a part's box corners, in float32 (glb._size and animation's box).
std::array<float, 24> moved_corners(const MeshArrays& mesh, const double* column) {
  float least[3], most[3];
  for (int c = 0; c < 3; ++c) least[c] = most[c] = mesh.positions[c];
  for (uint32_t v = 1; v < mesh.nodes; ++v)
    for (int c = 0; c < 3; ++c) {
      least[c] = std::min(least[c], mesh.positions[3 * v + c]);
      most[c] = std::max(most[c], mesh.positions[3 * v + c]);
    }
  float r[3][3], t[3];
  for (int row = 0; row < 3; ++row) {
    for (int col = 0; col < 3; ++col) r[row][col] = (float)column[col * 4 + row];
    t[row] = (float)column[12 + row];
  }
  std::array<float, 24> found;
  int n = 0;
  for (int i = 0; i < 2; ++i)
    for (int j = 0; j < 2; ++j)
      for (int k = 0; k < 2; ++k) {
        float p[3] = {i ? most[0] : least[0], j ? most[1] : least[1], k ? most[2] : least[2]};
        for (int row = 0; row < 3; ++row)
          found[n * 3 + row] = std::fmaf(p[2], r[row][2], std::fmaf(p[1], r[row][1], p[0] * r[row][0])) + t[row];
        ++n;
      }
  return found;
}

struct Channel {
  int instance;
  std::string path, interpolation;
  Vec times;
  std::vector<std::vector<Vec>> values;  // per key: one row, or three (CUBICSPLINE)
};

// animation._Animation: one resolved animation over the GLB's nodes.
struct Animation {
  const Document& doc;
  double duration;
  std::map<int, const MeshArrays*> held;
  std::map<int, int> placed;  // instance -> its prototype, for each placement the GLB draws
  std::map<Occurrence, int> index_of;
  std::vector<std::unique_ptr<Group>> group_list;
  std::map<std::vector<Occurrence>, Group*> groups;
  std::map<std::vector<Occurrence>, std::vector<int>> members;
  std::map<int, std::vector<Group*>> of;
  std::unique_ptr<Pose> pose;
  std::map<int, int> link;
  struct Aim { Mat4 matrix; std::vector<Group*> of; std::optional<int> link; };
  std::map<int, Aim> targets;
  std::map<double, std::map<const Group*, Mat4>> held_at;

  Animation(const Document& d, const Kinematics* k, const Value& row, const std::map<int, MeshArrays>& meshes,
            const std::vector<int>& shown)
      : doc(d) {
    duration = row.get("duration")->number();
    for (int index : shown) {
      placed[index] = doc.instances[index].prototype;
      held[doc.instances[index].prototype] = &meshes.at(doc.instances[index].prototype);
    }
    std::function<void(const Value&, const Occurrence&)> visit = [&](const Value& node, const Occurrence& path) {
      if (const Value* children = node.get("children")) {
        for (size_t at = 0; at < children->items.size(); ++at) {
          Occurrence inner = path;
          inner.push_back((int)at);
          visit(children->items[at], inner);
        }
      } else {
        index_of[path] = (int)node.get("instance")->number();
      }
    };
    visit(doc.tree, {});

    auto box = [&](const std::vector<int>& instances) -> std::optional<Vec> {
      double low[3] = {INF, INF, INF}, high[3] = {-INF, -INF, -INF};
      for (int index : instances) {
        auto corners = moved_corners(*held[placed[index]], doc.instances[index].matrix);
        for (int c = 0; c < 3; ++c) {
          float least = corners[c], most = corners[c];
          for (int n = 1; n < 8; ++n) {
            least = std::min(least, corners[n * 3 + c]);
            most = std::max(most, corners[n * 3 + c]);
          }
          low[c] = std::min(low[c], (double)least);
          high[c] = std::max(high[c], (double)most);
        }
      }
      if (!(std::isfinite(low[0]) && std::isfinite(low[1]) && std::isfinite(low[2]))) return std::nullopt;
      return Vec{(low[0] + high[0]) / 2, (low[1] + high[1]) / 2, (low[2] + high[2]) / 2};
    };
    auto group = [&](const std::vector<Occurrence>& leaves, int order) -> Group* {
      auto found = groups.find(leaves);
      if (found != groups.end()) return found->second;
      std::vector<int> instances;
      for (const Occurrence& leaf : leaves) {
        auto at = index_of.find(leaf);
        if (at != index_of.end() && placed.count(at->second)) instances.push_back(at->second);
      }
      group_list.push_back(std::make_unique<Group>());
      Group* g = group_list.back().get();
      g->leaves = leaves;
      g->size = leaves.size();
      g->first = order;
      groups[leaves] = g;
      members[leaves] = instances;
      auto centre = box(instances);
      g->centre = centre ? *centre : Vec(3, 0.0);
      return g;
    };

    struct Track {
      std::string path, interpolation;
      std::vector<std::pair<double, const Value*>> keys;
      std::vector<std::vector<Occurrence>> groups;
      const Value* extra;
      int order;
    };
    std::vector<Track> tracks;
    for (const Value& t : row.get("tracks")->items) {
      Track track{t.items[0].text, t.items[1].text, {}, {}, &t.items[4], (int)t.items[6].number()};
      for (const Value& key : t.items[2].items) track.keys.emplace_back(key.items[0].number(), &key.items[1]);
      for (const Value& g : t.items[3].items) {
        std::vector<Occurrence> leaves;
        for (const Value& leaf : g.items) leaves.push_back(occurrence_of(leaf));
        track.groups.push_back(leaves);
      }
      tracks.push_back(track);
    }
    std::stable_sort(tracks.begin(), tracks.end(), [](const Track& a, const Track& b) {
      return std::make_tuple(a.keys.front().first, a.keys.back().first, a.order) <
             std::make_tuple(b.keys.front().first, b.keys.back().first, b.order);
    });
    auto vec_keys = [](const Track& track) {
      std::vector<std::pair<double, Vec>> found;
      for (const auto& [t, value] : track.keys) found.emplace_back(t, numbers(*value));
      return found;
    };
    std::vector<PoseTrack> pose_tracks;
    for (const Track& track : tracks) {
      const Value* extra = track.extra->kind == Value::NUL ? nullptr : track.extra;
      if (track.path == "pose") {
        if (!k) throw std::runtime_error("an animation poses a document with no mechanism");
        PoseTrack p;
        p.start = track.keys.front().first;
        p.interpolation = track.interpolation;
        for (const auto& [t, values] : track.keys) {
          p.times.push_back(t);
          std::map<std::string, Vec> given;
          for (const Value& item : values->items) given[item.items[0].text] = numbers(item.items[1]);
          Vec flat;
          for (const auto& [label, rest] : k->as_built) {  // sorted labels
            auto at = given.find(label);
            for (double v : at == given.end() ? rest : at->second) flat.push_back(v);
          }
          p.rows.push_back(flat);
        }
        pose_tracks.push_back(p);
        continue;
      }
      if (track.path == "translation" && extra && extra->items[0].text == "explode") {
        std::string how = extra->items[1].text;
        const Value& given = extra->items[2];
        double distance = extra->items[3].number();
        std::vector<Group*> held_groups;
        for (const auto& leaves : track.groups) held_groups.push_back(group(leaves, track.order));
        std::map<size_t, Vec> moves;
        if (how == "direction") {
          Vec axis = numbers(given);
          std::vector<size_t> ranked(held_groups.size());
          for (size_t i = 0; i < ranked.size(); ++i) ranked[i] = i;
          std::vector<double> along(held_groups.size());
          for (size_t i = 0; i < ranked.size(); ++i) along[i] = dot_fma(held_groups[i]->centre.data(), axis.data(), 3);
          std::stable_sort(ranked.begin(), ranked.end(), [&](size_t a, size_t b) {
            return std::make_pair(along[a], a) < std::make_pair(along[b], b);
          });
          for (size_t rank = 0; rank < ranked.size(); ++rank) {
            Vec move(3);
            for (int c = 0; c < 3; ++c) move[c] = axis[c] * distance * (double)rank;
            moves[ranked[rank]] = move;
          }
        } else {
          Vec middle(3, 0.0);
          if (given.kind != Value::NUL) {
            middle = numbers(given);
          } else {  // np.mean of the centres: their sum in order, over their count
            for (int c = 0; c < 3; ++c) {
              double s = 0;
              for (Group* g : held_groups) s += g->centre[c];
              middle[c] = s / (double)held_groups.size();
            }
          }
          for (size_t at = 0; at < held_groups.size(); ++at) {
            Vec away(3);
            for (int c = 0; c < 3; ++c) away[c] = held_groups[at]->centre[c] - middle[c];
            double length = norm_fma(away.data(), 3);
            Vec move(3, 0.0);
            if (length > 1e-9)
              for (int c = 0; c < 3; ++c) move[c] = away[c] / length * distance;
            moves[at] = move;
          }
        }
        for (size_t at = 0; at < held_groups.size(); ++at)
          held_groups[at]->translations.emplace_back(ramp(vec_keys(track), Vec(3, 0.0), moves[at]), track.interpolation);
        continue;
      }
      for (const auto& leaves : track.groups) {
        Group* item = group(leaves, track.order);
        if (track.path == "translation") {
          std::vector<std::pair<double, Vec>> keys;
          if (!extra) {
            keys = vec_keys(track);
          } else {
            Vec before(3, 0.0);
            for (const Keyed& curve : item->translations)
              for (int c = 0; c < 3; ++c) before[c] = before[c] + curve.last()[c];
            Vec target = numbers(extra->items[1]), last(3);
            for (int c = 0; c < 3; ++c) last[c] = (target[c] - item->centre[c]) - before[c];
            keys = ramp(vec_keys(track), Vec(3, 0.0), last);
          }
          item->translations.emplace_back(keys, track.interpolation);
        } else if (track.path == "rotation") {
          if (extra->items[0].text == "quaternion") {
            std::vector<std::pair<double, Vec>> keys;
            for (const auto& [t, value] : track.keys) {
              double m[3][3], zero[3] = {0, 0, 0};
              rotation_of(numbers(*value), m);
              auto q = quaternion(about(m, zero));
              keys.emplace_back(t, Vec(q.begin(), q.end()));
            }
            Vec pivot = extra->items[1].kind != Value::NUL ? numbers(extra->items[1]) : item->centre;
            item->rotations.push_back({Keyed(keys, track.interpolation, true), std::nullopt, pivot});
          } else {
            Vec turned = numbers(extra->items[1]);
            const Value& given = extra->items[2];
            bool absolute = extra->items[3].kind == Value::BOOL && extra->items[3].flag;
            std::vector<std::pair<double, Vec>> keys = vec_keys(track);
            if (absolute) {
              double before = 0;  // Python's sum from 0
              for (const auto& r : item->rotations)
                if (r.axis) before = before + r.curve.last()[0] * dot_fma(r.axis->data(), turned.data(), 3);
              keys = ramp(keys, Vec{0.0}, Vec{keys.back().second[0] - before});
            }
            Vec pivot = given.kind != Value::NUL ? numbers(given) : item->centre;
            item->rotations.push_back({Keyed(keys, track.interpolation), turned, pivot});
          }
        } else {
          std::vector<std::pair<double, Vec>> keys;
          for (size_t i = 0; i < track.keys.size(); ++i) {
            const Value* value = track.keys[i].second;
            if (i == 0 && value->kind == Value::NUL)
              keys.emplace_back(track.keys[i].first, Vec{item->scales.empty() ? 1.0 : item->scales.back().last()[0]});
            else
              keys.emplace_back(track.keys[i].first, numbers(*value));
          }
          item->scales.emplace_back(keys, track.interpolation);
        }
      }
    }
    // Outermost first: the largest reference, then the first named.
    std::vector<Group*> ordered;
    for (auto& g : group_list) ordered.push_back(g.get());
    std::stable_sort(ordered.begin(), ordered.end(), [](const Group* a, const Group* b) {
      return std::make_pair(-(long)a->size, a->first) < std::make_pair(-(long)b->size, b->first);
    });
    for (Group* item : ordered)
      for (int index : members[item->leaves]) of[index].push_back(item);
    if (!pose_tracks.empty()) {
      pose = std::make_unique<Pose>(*k, pose_tracks);
      std::map<int, int> owner = owners(*k);
      Vec times = pose->times();
      std::set<double> checks(times.begin(), times.end());
      for (size_t i = 0; i + 1 < times.size(); ++i) checks.insert((times[i] + times[i + 1]) / 2);
      std::set<int> moved;
      for (double t : checks) {
        const std::vector<Mat4>& deltas = pose->deltas(t);
        for (size_t l = 0; l < deltas.size(); ++l)
          if (!near_eye(deltas[l])) moved.insert((int)l);
      }
      for (const auto& [index, _] : placed) {
        auto at = owner.find(index);
        if (at != owner.end() && moved.count(at->second)) link[index] = at->second;
      }
    }
  }

  // What changes a node, per path: its channels' interpolations and key times (animation._paths).
  using Paths = std::map<std::string, std::pair<std::set<std::string>, std::set<double>>>;
  Paths paths_of(const std::vector<Group*>& groups_of, std::optional<int> link_of) const {
    Paths found;
    auto add = [&](const std::string& path, const std::string& curve, const Vec& times) {
      auto& entry = found[path];
      entry.first.insert(curve);
      entry.second.insert(times.begin(), times.end());
    };
    for (const Group* item : groups_of) {
      for (const Keyed& curve : item->translations) add("translation", curve.interpolation, curve.times);
      for (const auto& r : item->rotations) {
        add("translation", r.curve.interpolation, r.curve.times);
        add("rotation", r.curve.interpolation, r.curve.times);
      }
      for (const Keyed& curve : item->scales) add("scale", curve.interpolation, curve.times);
    }
    if (link_of && pose)
      for (const PoseTrack& track : pose->tracks)
        for (const char* path : {"translation", "rotation"}) add(path, track.interpolation, track.times);
    return found;
  }

  Signature signature(int index) const {
    auto groups_at = of.find(index);
    std::vector<Group*> mine = groups_at == of.end() ? std::vector<Group*>() : groups_at->second;
    auto link_at = link.find(index);
    std::optional<int> link_of = link_at == link.end() ? std::nullopt : std::optional<int>(link_at->second);
    Paths paths = paths_of(mine, link_of);
    if (paths.empty()) return std::nullopt;
    if (paths.count("scale")) return std::make_pair("scale:" + std::to_string(index), false);
    std::string key;
    for (const Group* g : mine) key += std::to_string((uintptr_t)g) + ",";
    key += "|" + (link_of ? std::to_string(*link_of) : std::string("none"));
    return std::make_pair(key, true);
  }

  void aim(const Target& target) {
    int first = target.members[0];
    auto groups_at = of.find(first);
    auto link_at = link.find(first);
    targets[target.node] = {target.matrix, groups_at == of.end() ? std::vector<Group*>() : groups_at->second,
                            link_at == link.end() ? std::nullopt : std::optional<int>(link_at->second)};
  }

  Mat4 matrix(int key, double t) {
    auto& held_now = held_at[t];
    const Aim& aimed = targets.at(key);
    Mat4 found = aimed.matrix;
    if (aimed.link) found = matmul(pose->deltas(t)[*aimed.link], found);
    for (auto it = aimed.of.rbegin(); it != aimed.of.rend(); ++it) {
      auto moved = held_now.find(*it);
      if (moved == held_now.end()) moved = held_now.emplace(*it, (*it)->matrix(t)).first;
      found = matmul(moved->second, found);
    }
    return found;
  }

  Vec value(int key, const std::string& path, double t) {
    if (path == "scale") {
      double factor = 1.0;
      for (const Group* item : targets.at(key).of) factor *= item->factor(t);
      return Vec(3, factor);
    }
    Mat4 m = matrix(key, t);
    if (path == "translation") return {m[3], m[7], m[11]};
    auto q = quaternion(m);
    return Vec(q.begin(), q.end());
  }
};

// animation._distance
double distance(const std::string& path, Vec got, const Vec& truth) {
  if (path == "rotation") {
    double length = norm_fma(got.data(), (int)got.size());
    for (double& v : got) v = v / length;
    return 2 * std::acos(std::min(1.0, std::fabs(dot_fma(got.data(), truth.data(), (int)got.size()))));
  }
  Vec off(got.size());
  for (size_t i = 0; i < got.size(); ++i) off[i] = got[i] - truth[i];
  if (path == "scale") {
    double worst = std::fabs(off[0]);
    for (double v : off) worst = std::max(worst, std::fabs(v));
    return worst;
  }
  return norm_fma(off.data(), (int)off.size());
}

// animation._signed: each rotation key on its predecessor's side.
void signed_rows(const std::string& path, std::vector<std::vector<Vec>>& rows) {
  if (path != "rotation") return;
  for (size_t at = 1; at < rows.size(); ++at) {
    const Vec& here = rows[at].size() == 3 ? rows[at][1] : rows[at][0];
    const Vec& before = rows[at - 1].size() == 3 ? rows[at - 1][1] : rows[at - 1][0];
    if (dot_fma(here.data(), before.data(), (int)here.size()) < 0)
      for (Vec& row : rows[at])
        for (double& v : row) v = -v;
  }
}

// animation._channel
Channel channel_of(Animation& motion, int index, const std::string& path, const std::set<std::string>& kinds,
                   const std::set<double>& breaks, double limit, const std::string& name) {
  double duration = motion.duration;
  std::string ease = "cubic";
  if (kinds.size() == 1) ease = *kinds.begin() == "STEP" ? "step" : *kinds.begin() == "LINEAR" ? "linear" : "cubic";
  auto at = [&](double t) { return motion.value(index, path, t); };
  if (ease == "step") {
    std::set<double> unique(breaks);
    unique.insert(0.0);
    unique.insert(duration);
    Channel c{index, path, "STEP", Vec(unique.begin(), unique.end()), {}};
    for (double t : c.times) c.values.push_back({at(t)});
    signed_rows(path, c.values);
    return c;
  }
  std::set<double> unique{0.0, duration};
  for (double t : breaks)
    if (0.0 <= t && t <= duration) unique.insert(t);
  Vec times(unique.begin(), unique.end());
  if (ease == "cubic") {
    for (size_t i = 0; i + 1 < times.size(); ++i) unique.insert((times[i] + times[i + 1]) / 2);
    times.assign(unique.begin(), unique.end());
  }
  double h = 1e-5 * duration;
  std::map<double, std::vector<Vec>> keys;
  auto key = [&](double t) -> const std::vector<Vec>& {
    auto found = keys.find(t);
    if (found != keys.end()) return found->second;
    Vec value = at(t);
    if (ease == "linear") return keys[t] = {value};
    auto near = [&](double u) {
      Vec other = at(u);
      if (path == "rotation" && dot_fma(other.data(), value.data(), (int)value.size()) < 0)
        for (double& v : other) v = -v;
      return other;
    };
    std::optional<Vec> before, after;
    if (t - 2 * h >= 0) {
      Vec a = near(t - h), b = near(t - 2 * h), d(value.size());
      for (size_t i = 0; i < d.size(); ++i) d[i] = ((3 * value[i] - 4 * a[i]) + b[i]) / (2 * h);
      before = d;
    }
    if (t + 2 * h <= duration) {
      Vec a = near(t + h), b = near(t + 2 * h), d(value.size());
      for (size_t i = 0; i < d.size(); ++i) d[i] = ((-3 * value[i] + 4 * a[i]) - b[i]) / (2 * h);
      after = d;
    }
    if (!before) before = after;
    if (!after) after = before;
    return keys[t] = {*before, value, *after};
  };
  auto deviation_of = [&](double a, double b) {
    std::vector<Vec> first = key(a), second = key(b);
    double worst = 0.0;
    const Vec& f = ease == "cubic" ? first[1] : first[0];
    const Vec& s2 = ease == "cubic" ? second[1] : second[0];
    if (path == "rotation") {
      double dot = dot_fma(f.data(), s2.data(), (int)f.size());
      if (dot < 0) {
        for (Vec& row : second)
          for (double& v : row) v = -v;
        dot = -dot;
      }
      if (2 * std::acos(std::min(1.0, dot)) > 120.0 * DEG) return INF;
    }
    for (double s : CHECKS) {
      double t = a + (b - a) * s;
      Vec got;
      if (ease == "cubic") {
        got = hermite(first.data(), second.data(), b - a, s);
      } else if (path == "rotation") {
        got = slerp1(first[0], second[0], s);
      } else {
        got.resize(first[0].size());
        for (size_t i = 0; i < got.size(); ++i) got[i] = first[0][i] + s * (second[0][i] - first[0][i]);
      }
      worst = std::max(worst, distance(path, got, at(t)));
    }
    return worst;
  };
  while (true) {
    std::vector<double> split;
    for (size_t i = 0; i + 1 < times.size(); ++i)
      if (deviation_of(times[i], times[i + 1]) > limit) split.push_back((times[i] + times[i + 1]) / 2);
    if (split.empty()) break;
    std::set<double> grown(times.begin(), times.end());
    grown.insert(split.begin(), split.end());
    if (grown.size() == times.size() || grown.size() > 4097)
      throw std::runtime_error("the " + path + " of '" + name + "' does not settle within the tolerance in 4097 keys");
    times.assign(grown.begin(), grown.end());
  }
  Channel c{index, path, ease == "cubic" ? "CUBICSPLINE" : "LINEAR", times, {}};
  for (double t : times) c.values.push_back(key(t));
  signed_rows(path, c.values);
  return c;
}

// animation._moves: whether a channel puts its node anywhere but where it stands at rest.
bool moves(const Channel& c, const Vec& rest) {
  for (const auto& row : c.values) {
    const Vec& value = row.size() == 3 ? row[1] : row[0];
    if (c.path == "rotation") {
      if (std::fabs(std::fabs(dot_fma(value.data(), rest.data(), 4)) - 1.0) > 1e-9) return true;
    } else {
      for (size_t i = 0; i < value.size(); ++i)
        if (std::fabs(value[i] - rest[i]) > 1e-9) return true;
    }
  }
  return false;
}

struct BakedAnimation { std::string name; double duration; std::vector<Channel> channels; };

// animation.bake
std::vector<BakedAnimation> bake(const Document& doc, const Kinematics* k, const std::map<int, MeshArrays>& meshes,
                                 const std::vector<int>& shown, const std::vector<Target>& targets, double size) {
  std::vector<BakedAnimation> found;
  if (doc.animations_record.empty()) return found;
  Value rows = Value::parse(doc.animations_record);
  // animations.from_json: by name, a later row of a name in the first one's place.
  std::vector<const Value*> by_name;
  for (const Value& row : rows.items) {
    bool replaced = false;
    for (const Value*& held : by_name)
      if (held->get("name")->text == row.get("name")->text) { held = &row; replaced = true; }
    if (!replaced) by_name.push_back(&row);
  }
  std::map<std::string, double> tolerance = {{"translation", 1e-3 * std::max(1.0, size)}, {"rotation", 1e-3},
                                             {"scale", 1e-3}};
  for (const Value* row : by_name) {
    Animation motion(doc, k, *row, meshes, shown);
    BakedAnimation baked{row->get("name")->text, motion.duration, {}};
    for (const Target* target : chosen(targets, [&](int index) { return motion.signature(index); })) {
      motion.aim(*target);
      const auto& aimed = motion.targets.at(target->node);
      for (const auto& [path, how] : motion.paths_of(aimed.of, aimed.link)) {
        Channel c = channel_of(motion, target->node, path, how.first, how.second, tolerance[path], target->name);
        Vec rest;
        if (path == "translation") rest = {target->matrix[3], target->matrix[7], target->matrix[11]};
        else if (path == "rotation") { auto q = quaternion(target->matrix); rest.assign(q.begin(), q.end()); }
        else rest = Vec(3, 1.0);
        if (!moves(c, rest)) continue;
        baked.channels.push_back(c);
      }
    }
    found.push_back(baked);
  }
  return found;
}


// --- export/keys.py: a baked track written as the fewest LINEAR keys within KEY_MM and KEY_DEGREES ------------

constexpr double KEY_MM = 0.1, KEY_DEGREES = 0.1, JUMP = 1e-6, MOST_TURN_DEGREES = 120.0, SLACK = 0.05;
constexpr int SAMPLES = 8, MOST_SAMPLES = 4096, WINDOW = 16;

using Rows = std::vector<Vec>;

// keys._slerp, one row: glTF's LINEAR rotation from a to b by s (three.js's slerpFlat), numpy's elementwise way.
Vec slerp_row(const Vec& a, Vec b, double s) {
  double dot = sum_axis(a.data(), b.data(), 4);
  if (dot < 0)
    for (double& v : b) v = -v;
  double theta = std::acos(std::min(std::max(std::fabs(dot), 0.0), 1.0));
  double sine = std::sin(theta);
  bool near = sine < 1e-6;
  double safe = near ? 1.0 : sine;
  double first = near ? 1.0 - s : std::sin((1.0 - s) * theta) / safe;
  double second = near ? s : std::sin(s * theta) / safe;
  Vec found(4);
  for (int i = 0; i < 4; ++i) found[i] = first * a[i] + second * b[i];
  double length = norm_axis(found.data(), 4);
  for (double& v : found) v = v / length;
  return found;
}

// keys._apart
double apart(const std::string& path, const Vec& got, const Vec& truth) {
  if (path == "rotation") {
    double dot = std::fabs(sum_axis(got.data(), truth.data(), 4));
    return 2.0 * std::acos(std::min(std::max(dot, 0.0), 1.0));
  }
  Vec off(got.size());
  for (size_t i = 0; i < got.size(); ++i) off[i] = got[i] - truth[i];
  if (path == "scale") {
    double worst = std::fabs(off[0]);
    for (double v : off) worst = std::max(worst, std::fabs(v));
    return worst;
  }
  return norm_axis(off.data(), (int)off.size());
}

// keys.linear: a baked track's LINEAR keys. `rows` per key: one row, or three (CUBICSPLINE: in-tangent, value,
// out-tangent). Returns the kept times and values.
std::pair<Vec, Rows> linear_keys(const Vec& times, const std::vector<std::vector<Vec>>& rows, const std::string& interpolation,
                                 const std::string& path, double duration, double reach) {
  bool cubic = interpolation == "CUBICSPLINE";
  size_t count = times.size();
  Rows values;
  for (const auto& row : rows) values.push_back(cubic ? row[1] : row[0]);
  if (count < 2) return {times, values};
  size_t width = values[0].size();
  bool rotation = path == "rotation";
  double limit = rotation ? KEY_DEGREES * DEG : path == "scale" ? (reach > 0 ? KEY_MM / reach : INF) : KEY_MM;
  double most_turn = MOST_TURN_DEGREES * DEG;

  Vec spans(count - 1);
  for (size_t i = 0; i + 1 < count; ++i) spans[i] = times[i + 1] - times[i];
  Vec each(count - 1, rotation && interpolation == "LINEAR" ? (double)SAMPLES : 1.0);
  if (cubic && std::isfinite(limit)) {
    for (size_t i = 0; i + 1 < count; ++i) {
      Vec a(width), b(width);
      for (size_t c = 0; c < width; ++c) {
        double p0 = values[i][c], m0 = rows[i][2][c] * spans[i], p1 = values[i + 1][c], m1 = rows[i + 1][0][c] * spans[i];
        a[c] = ((-6 * p0 - 4 * m0) + 6 * p1) - 2 * m1;
        b[c] = ((6 * p0 + 2 * m0) - 6 * p1) + 4 * m1;
      }
      double bend = std::max(norm_axis(a.data(), (int)width), norm_axis(b.data(), (int)width));
      bend = bend * (rotation ? 2.0 : 1.0);
      each[i] = std::max(each[i], std::ceil(std::sqrt(bend / (8 * SLACK * limit))));
    }
  }
  std::vector<size_t> jumps;
  for (size_t i = 0; i + 1 < count; ++i)
    if (spans[i] < JUMP * duration) {
      jumps.push_back(i);
      each[i] = 1;
    }
  std::vector<long> counts(count - 1);
  for (size_t i = 0; i + 1 < count; ++i) counts[i] = (long)std::min(each[i], (double)MOST_SAMPLES);
  double held = limit * (1 - SLACK);
  std::vector<long> starts(count, 0);
  for (size_t i = 0; i + 1 < count; ++i) starts[i + 1] = starts[i] + counts[i];
  long total = starts.back() + 1;
  std::vector<long> step(total);
  Vec fraction(total), at(total);
  {
    long n = 0;
    for (size_t i = 0; i + 1 < count; ++i)
      for (long k = 0; k < counts[i]; ++k) step[n++] = (long)i;
    step[n] = (long)count - 2;
    for (long j = 0; j < total - 1; ++j)
      fraction[j] = (double)(j - starts[step[j]]) / (double)counts[step[j]];
    fraction[total - 1] = 1.0;
    for (long j = 0; j < total; ++j) at[j] = times[step[j]] + fraction[j] * spans[step[j]];
    for (size_t i = 0; i < count; ++i) at[starts[i]] = times[i];
  }
  Rows truth(total, Vec(width));
  auto lerp = [&](long j) {
    Vec found(width);
    double s = fraction[j];
    for (size_t c = 0; c < width; ++c) found[c] = values[step[j]][c] + s * (values[step[j] + 1][c] - values[step[j]][c]);
    return found;
  };
  for (long j = 0; j < total; ++j) {
    double s = fraction[j];
    long k = step[j];
    if (cubic) {
      // numpy's power(s, 3) of an array, as C's pow; s ** 2 a square.
      double s3 = std::pow(s, 3.0), s2 = s * s;
      double span = spans[k];
      double c0 = (2 * s3 - 3 * s2) + 1, c1 = span * ((s3 - 2 * s2) + s), c2 = -2 * s3 + 3 * s2, c3 = span * (s3 - s2);
      for (size_t c = 0; c < width; ++c)
        truth[j][c] = ((c0 * rows[k][1][c] + c1 * rows[k][2][c]) + c2 * rows[k + 1][1][c]) + c3 * rows[k + 1][0][c];
      if (rotation) {
        double length = norm_axis(truth[j].data(), (int)width);
        for (double& v : truth[j]) v = v / length;
      }
    } else if (rotation) {
      truth[j] = slerp_row(values[k], values[k + 1], s);
    } else {
      truth[j] = lerp(j);
    }
  }
  for (size_t i = 0; i < count; ++i) truth[starts[i]] = values[i];

  // The candidates: every key, and every sample of a step its own two keys' line does not hold.
  std::vector<bool> loose(count - 1, false);
  if (cubic) {
    for (size_t i = 0; i + 1 < count; ++i) {
      double worst = -INF;
      for (long j = starts[i]; j < starts[i + 1]; ++j) {
        Vec straight = rotation ? slerp_row(values[step[j]], values[step[j] + 1], fraction[j]) : lerp(j);
        worst = std::max(worst, apart(path, straight, truth[j]));
      }
      loose[i] = worst > held;
    }
  }
  if (rotation)
    for (size_t i = 0; i + 1 < count; ++i) {
      double turned = 2.0 * std::acos(std::min(std::max(std::fabs(sum_axis(values[i].data(), values[i + 1].data(), 4)), 0.0), 1.0));
      loose[i] = loose[i] || turned > most_turn;
    }
  for (size_t i : jumps) loose[i] = false;
  std::vector<bool> whole(total, false), is_start(total, false);
  {
    long n = 0;
    for (size_t i = 0; i + 1 < count; ++i)
      for (long k = 0; k < counts[i]; ++k) whole[n++] = loose[i];
  }
  for (size_t i = 0; i < count; ++i) whole[starts[i]] = is_start[starts[i]] = true;
  // A sample becomes a key only where its time, as the GLB writes it (float32), is after the one before.
  std::vector<float> written(total);
  for (long j = 0; j < total; ++j) written[j] = (float)at[j];
  std::vector<long> inner;
  for (long j = 0; j < total; ++j)
    if (whole[j] && !is_start[j]) inner.push_back(j);
  for (long j : inner)
    if (written[j] <= written[j - 1] || written[j] >= written[std::min(j + 1, total - 1)]) whole[j] = false;
  std::vector<long> candidates;
  for (long j = 0; j < total; ++j)
    if (whole[j]) candidates.push_back(j);
  std::vector<long> place(total, -1);
  for (size_t i = 0; i < candidates.size(); ++i) place[candidates[i]] = (long)i;
  std::vector<bool> forced(candidates.size(), false);
  forced[0] = forced.back() = true;
  for (size_t i : jumps) {
    forced[place[starts[i]]] = true;
    forced[place[starts[i + 1]]] = true;
  }
  std::vector<long> pinned;
  for (size_t i = 0; i < forced.size(); ++i)
    if (forced[i]) pinned.push_back((long)i);

  // Whether the line from candidate `first` to each of `ends` holds every sample it spans.
  auto holds = [&](long first, const std::vector<long>& ends) {
    long a = candidates[first];
    std::vector<bool> ok(ends.size(), true);
    if (rotation)
      for (size_t e = 0; e < ends.size(); ++e) {
        long b = candidates[ends[e]];
        double turned = 2.0 * std::acos(std::min(std::max(std::fabs(dot_fma(truth[b].data(), truth[a].data(), 4)), 0.0), 1.0));
        ok[e] = ok[e] && turned <= most_turn;
      }
    long last_b = candidates[ends.back()];
    if (a + 1 >= last_b) return ok;
    for (size_t e = 0; e < ends.size(); ++e) {
      long b = candidates[ends[e]];
      double worst = 0.0;
      for (long inside = a + 1; inside < last_b; ++inside) {
        double off = 0.0;
        if (inside < b) {
          double f = (at[inside] - at[a]) / (at[b] - at[a]);
          Vec got(width);
          if (rotation) {
            got = slerp_row(truth[a], truth[b], f);
          } else {
            for (size_t c = 0; c < width; ++c) got[c] = truth[a][c] + f * (truth[b][c] - truth[a][c]);
          }
          off = apart(path, got, truth[inside]);
        }
        worst = inside == a + 1 ? off : std::max(worst, off);
      }
      ok[e] = ok[e] && worst <= held;
    }
    return ok;
  };

  std::vector<long> kept{0};
  long first = 0, last = (long)candidates.size() - 1;
  while (first < last) {
    long bound = *std::upper_bound(pinned.begin(), pinned.end(), first);
    long top = std::min(first + (long)WINDOW, bound);
    std::vector<long> ends;
    for (long e = first + 1; e <= top; ++e) ends.push_back(e);
    std::vector<bool> ok = holds(first, ends);
    long best = first + 1;
    for (size_t e = 0; e < ends.size(); ++e)
      if (ok[e]) best = ends[e];
    if (best == top && top < bound) {
      long good = top, width_ = WINDOW;
      std::optional<long> bad;
      while (!bad && good < bound) {
        width_ *= 2;
        long probe = std::min(first + width_, bound);
        if (holds(first, {probe})[0]) good = probe; else bad = probe;
      }
      while (bad && *bad - good > 1) {
        long middle = (good + *bad) / 2;
        if (holds(first, {middle})[0]) good = middle; else bad = middle;
      }
      best = good;
    }
    kept.push_back(best);
    first = best;
  }
  Vec out_times;
  Rows out;
  for (long i : kept) {
    out_times.push_back(at[candidates[i]]);
    out.push_back(truth[candidates[i]]);
  }
  if (rotation)
    for (size_t k = 1; k < out.size(); ++k)
      if (dot_fma(out[k].data(), out[k - 1].data(), 4) < 0)
        for (double& v : out[k]) v = -v;
  return {out_times, out};
}


// --- glb._animations ---------------------------------------------------------------------------------------------

// glb._size: the model's size, the diagonal of every placed mesh's box.
double model_size(const Document& doc, const std::map<int, MeshArrays>& held, const std::vector<int>& shown) {
  double low[3] = {INF, INF, INF}, high[3] = {-INF, -INF, -INF};
  for (int index : shown) {
    const Instance& placed = doc.instances[index];
    auto corners = moved_corners(held.at(placed.prototype), placed.matrix);
    for (int c = 0; c < 3; ++c) {
      float least = corners[c], most = corners[c];
      for (int n = 1; n < 8; ++n) {
        least = std::min(least, corners[n * 3 + c]);
        most = std::max(most, corners[n * 3 + c]);
      }
      low[c] = std::min(low[c], (double)least);
      high[c] = std::max(high[c], (double)most);
    }
  }
  if (!(std::isfinite(low[0]) && std::isfinite(low[1]) && std::isfinite(low[2]))) return 1.0;
  double d[3] = {high[0] - low[0], high[1] - low[1], high[2] - low[2]};
  return norm_fma(d, 3);
}

// glb._conjugate_left: the 4x4 that multiplies a quaternion on the left by q's conjugate.
std::array<double, 16> conjugate_left(const std::array<double, 4>& q) {
  double x = -q[0], y = -q[1], z = -q[2], w = q[3];
  return {w, -z, y, x, z, w, -x, y, -y, x, w, z, -x, -y, -z, w};
}

// glb._local_rows: a track's rows, in the document's frame, made its node's parent's (`within`).
std::vector<std::vector<Vec>> local_rows(const std::string& path, const std::string& interpolation,
                                         std::vector<std::vector<Vec>> rows, const Mat4& within) {
  if (path == "scale" || within == eye()) return rows;
  if (path == "translation") {
    // rows @ within[:3, :3]: each row times the matrix (fused, in order); the offset within[:3, 3] @ within[:3, :3].
    auto turned = [&](const Vec& v) {
      Vec found(3);
      for (int j = 0; j < 3; ++j) {
        double s = v[0] * within[0 * 4 + j];
        s = std::fma(v[1], within[1 * 4 + j], s);
        s = std::fma(v[2], within[2 * 4 + j], s);
        found[j] = s;
      }
      return found;
    };
    Vec origin = {within[3], within[7], within[11]};
    Vec offset = turned(origin);
    for (auto& key : rows) {
      for (size_t r = 0; r < key.size(); ++r) {
        key[r] = turned(key[r]);
        bool value = interpolation != "CUBICSPLINE" || r == 1;
        if (value)
          for (int c = 0; c < 3; ++c) key[r][c] = key[r][c] - offset[c];
      }
    }
    return rows;
  }
  // rows @ conjugate_left(quaternion(within)).T
  std::array<double, 16> m = conjugate_left(quaternion(within));
  for (auto& key : rows)
    for (Vec& row : key) {
      Vec found(4);
      for (int j = 0; j < 4; ++j) {
        double s = row[0] * m[j * 4 + 0];
        for (int k = 1; k < 4; ++k) s = std::fma(row[k], m[j * 4 + k], s);
        found[j] = s;
      }
      row = found;
    }
  return rows;
}

std::string bytes_of(const Vec& v) { return std::string(reinterpret_cast<const char*>(v.data()), v.size() * 8); }

}  // namespace

std::vector<Value> bake_animations(const Document& doc, const std::map<int, MeshArrays>& held,
                                   const std::vector<int>& shown, Tree& tree, Buffers& buffers) {
  std::unique_ptr<Kinematics> k;
  if (doc.kinematics) k = read_kinematics(*doc.kinematics);
  bool motions = k && !k->motions.empty();
  if (tree.targets.empty() || !(motions || !doc.animations_record.empty())) return {};
  double size = model_size(doc, held, shown);
  std::vector<Clip> baked = motions ? clips(*k, tree.targets, size) : std::vector<Clip>();
  std::vector<BakedAnimation> animations = doc.animations_record.empty()
                                               ? std::vector<BakedAnimation>()
                                               : bake(doc, k.get(), held, shown, tree.targets, size);
  std::set<int> animated;
  for (const Clip& clip : baked) animated.insert(clip.instances.begin(), clip.instances.end());
  for (const BakedAnimation& a : animations)
    for (const Channel& c : a.channels) animated.insert(c.instance);
  std::map<int, const Target*> target_of;
  for (const Target& target : tree.targets) target_of[target.node] = &target;
  for (int index : animated) {
    Value& node = tree.nodes[index];
    Value matrix;
    Mat4 local = eye();
    if (pop(node, "matrix", &matrix)) {
      double column[16];
      for (int i = 0; i < 16; ++i) column[i] = matrix.items[i].number();
      local = from_column(column);
    }
    double translation[3] = {local[3], local[7], local[11]};
    node.keys.emplace_back("translation", reals(translation, 3));
    auto q = quaternion(local);
    node.keys.emplace_back("rotation", reals(q.data(), 4));
  }

  std::map<std::pair<std::string, std::string>, int> data;
  auto accessor = [&](const Rows& rows, const char* kind) {
    std::vector<float> array;
    for (const Vec& row : rows)
      for (double v : row) array.push_back((float)v);
    std::string bytes(reinterpret_cast<const char*>(array.data()), array.size() * 4);
    auto key = std::make_pair(std::string(kind), bytes);
    auto found = data.find(key);
    if (found != data.end()) return found->second;
    int index = buffers.add(bytes, rows.size(), 0, kind, 5126);
    if (std::string(kind) == "SCALAR") {
      Value& entry = buffers.accessors[index];
      entry.keys.emplace_back("min", reals(std::array<double, 1>{(double)array.front()}.data(), 1));
      entry.keys.emplace_back("max", reals(std::array<double, 1>{(double)array.back()}.data(), 1));
    }
    data[key] = index;
    return index;
  };

  std::map<int, double> reaches;
  auto reach = [&](int node) {
    int prototype = doc.instances[target_of.at(node)->members[0]].prototype;
    auto found = reaches.find(prototype);
    if (found != reaches.end()) return found->second;
    const MeshArrays& mesh = held.at(prototype);
    double far = 0.0;
    for (uint32_t v = 0; v < mesh.nodes; ++v) {
      double p[3] = {mesh.positions[3 * v], mesh.positions[3 * v + 1], mesh.positions[3 * v + 2]};
      double d = norm_axis(p, 3);
      far = v == 0 ? d : std::max(far, d);
    }
    return reaches[prototype] = mesh.nodes ? far : 0.0;
  };

  std::map<std::string, std::pair<Vec, Rows>> written;
  struct Track { int node; std::string path, interpolation; Vec times; std::vector<std::vector<Vec>> rows; };
  std::vector<Value> found;
  auto animation = [&](const std::string& name, double duration, const char* clip_kind, const std::vector<Track>& tracks) {
    Value samplers = list(), channels = list();
    std::map<std::tuple<int, std::string, int>, int> shared;
    for (const Track& track : tracks) {
      std::vector<std::vector<Vec>> rows = local_rows(track.path, track.interpolation, track.rows,
                                                      target_of.at(track.node)->within);
      std::string interpolation = track.interpolation;
      Vec times = track.times;
      Rows out;
      if (interpolation == "STEP") {
        for (const auto& key : rows)
          for (const Vec& row : key) out.push_back(row);
      } else {
        double far = track.path == "scale" ? reach(track.node) : 0.0;
        std::string cache = track.path + "|" + track.interpolation + "|" + bytes_of({duration, far}) + bytes_of(times);
        for (const auto& key : rows)
          for (const Vec& row : key) cache += bytes_of(row);
        auto at = written.find(cache);
        if (at == written.end())
          at = written.emplace(cache, linear_keys(times, rows, track.interpolation, track.path, duration, far)).first;
        interpolation = "LINEAR";
        times = at->second.first;
        out = at->second.second;
      }
      Rows time_rows;
      for (double t : times) time_rows.push_back({t});
      int input = accessor(time_rows, "SCALAR");
      int output = accessor(out, track.path == "rotation" ? "VEC4" : "VEC3");
      auto key = std::make_tuple(input, interpolation, output);
      auto at = shared.find(key);
      int sampler;
      if (at == shared.end()) {
        sampler = shared[key] = (int)samplers.items.size();
        Value entry = object();
        entry.keys.emplace_back("input", integer(input));
        entry.keys.emplace_back("interpolation", string(interpolation));
        entry.keys.emplace_back("output", integer(output));
        samplers.items.push_back(entry);
      } else {
        sampler = at->second;
      }
      Value channel = object(), target = object();
      channel.keys.emplace_back("sampler", integer(sampler));
      target.keys.emplace_back("node", integer(track.node));
      target.keys.emplace_back("path", string(track.path));
      channel.keys.emplace_back("target", target);
      channels.items.push_back(channel);
    }
    Value entry = object(), extras = object(), cad = object();
    entry.keys.emplace_back("name", string(name));
    entry.keys.emplace_back("channels", channels);
    entry.keys.emplace_back("samplers", samplers);
    cad.keys.emplace_back("duration", real(duration));
    cad.keys.emplace_back("kind", string(clip_kind));
    extras.keys.emplace_back("cad", cad);
    entry.keys.emplace_back("extras", extras);
    found.push_back(entry);
  };

  for (const Clip& clip : baked) {
    if (clip.instances.empty()) continue;
    std::vector<Track> tracks;
    for (size_t i = 0; i < clip.instances.size(); ++i) {
      Track translation{clip.instances[i], "translation", "CUBICSPLINE", clip.times, {}};
      for (const auto& key : clip.translations[i]) translation.rows.push_back({key[0], key[1], key[2]});
      Track rotation{clip.instances[i], "rotation", "CUBICSPLINE", clip.times, {}};
      for (const auto& key : clip.rotations[i]) rotation.rows.push_back({key[0], key[1], key[2]});
      tracks.push_back(translation);
      tracks.push_back(rotation);
    }
    animation(clip.name, clip.duration, "motion", tracks);
  }
  for (const BakedAnimation& a : animations) {
    if (a.channels.empty()) continue;
    std::vector<Track> tracks;
    for (const Channel& c : a.channels) tracks.push_back({c.instance, c.path, c.interpolation, c.times, c.values});
    animation(a.name, a.duration, "animation", tracks);
  }
  return found;
}



}  // namespace glb
}  // namespace vc
