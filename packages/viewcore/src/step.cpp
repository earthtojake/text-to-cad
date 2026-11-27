// step.cpp: an .xbf's STEP, as cad's export/step.py writes it: AP242 by OCCT's XCAF writer from the document (names,
// colours, materials, element names on sub-shapes), each usage of a prototype placed apart while it is transferred
// (step._usages_apart), standard reflectance for material-bearing parts and faces (step_style.write_visual_styles),
// the header's time stamp pinned, and the written bytes settled so the same document writes the same bytes
// (step._settle: unused styles pruned, presentations renumbered in the document's order, assembly occurrences numbered
// from 1, densities in the unit their numbers are in). The module docstrings of step.py and step_style.py say why.
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <functional>
#include <map>
#include <regex>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <tuple>
#include <vector>

#include <APIHeaderSection_MakeHeader.hxx>
#include <IFSelect_ReturnStatus.hxx>
#include <Interface_Static.hxx>
#include <Message.hxx>
#include <Message_Messenger.hxx>
#include <NCollection_HArray1.hxx>
#include <Quantity_Color.hxx>
#include <STEPCAFControl_Reader.hxx>
#include <STEPCAFControl_Writer.hxx>
#include <STEPConstruct.hxx>
#include <STEPConstruct_RenderingProperties.hxx>
#include <STEPConstruct_Styles.hxx>
#include <STEPControl_Reader.hxx>
#include <STEPControl_StepModelType.hxx>
#include <StepData_StepModel.hxx>
#include <StepRepr_RepresentationItem.hxx>
#include <StepVisual_FillAreaStyle.hxx>
#include <StepVisual_FillAreaStyleColour.hxx>
#include <StepVisual_FillStyleSelect.hxx>
#include <StepVisual_PresentationStyleAssignment.hxx>
#include <StepVisual_PresentationStyleSelect.hxx>
#include <StepVisual_RenderingPropertiesSelect.hxx>
#include <StepVisual_StyledItem.hxx>
#include <StepVisual_SurfaceSideStyle.hxx>
#include <StepVisual_SurfaceStyleElementSelect.hxx>
#include <StepVisual_SurfaceStyleFillArea.hxx>
#include <StepVisual_SurfaceStyleRenderingWithProperties.hxx>
#include <StepVisual_SurfaceStyleUsage.hxx>
#include <TCollection_HAsciiString.hxx>
#include <TDF_AttributeIterator.hxx>
#include <TDF_Label.hxx>
#include <TDF_Tool.hxx>
#include <TNaming_NamedShape.hxx>
#include <TopExp_Explorer.hxx>
#include <TopLoc_Location.hxx>
#include <TopoDS_Shape.hxx>
#include <Transfer_FinderProcess.hxx>
#include <XCAFDoc_DocumentTool.hxx>
#include <XCAFDoc_Location.hxx>
#include <XCAFDoc_ShapeTool.hxx>
#include <XCAFDoc_VisMaterial.hxx>
#include <XCAFDoc_VisMaterialTool.hxx>
#include <XSControl_TransferWriter.hxx>
#include <XSControl_WorkSession.hxx>
#include <XSControl_Writer.hxx>

#include "core.hpp"

namespace vc {

namespace {

const char* SCHEMA = "AP242DIS";
const char* WRITTEN_STAMP = "2000-01-01T00:00:00";

std::string entry(const TDF_Label& label) {
  TCollection_AsciiString text;
  TDF_Tool::Entry(label, text);
  return text.ToCString();
}

// The kernel's translators report to its default messenger, which prints: no printer.
void quiet() {
  static bool done = false;
  if (done) return;
  occ::handle<Message_Messenger> messenger = Message::DefaultMessenger();
  messenger->ChangePrinters().Clear();
  done = true;
}

// step._usages_apart: each usage of a prototype that another usage of it at the same placement datum would be
// confused with is given a datum of its own (the same transformation) while the writer transfers the document,
// and set back after.
class UsagesApart {
 public:
  explicit UsagesApart(const occ::handle<TDocStd_Document>& doc) {
    tool_ = XCAFDoc_DocumentTool::ShapeTool(doc->Main());
    NCollection_Sequence<TDF_Label> labels;
    tool_->GetShapes(labels);
    std::map<std::pair<std::string, size_t>, std::vector<TopLoc_Location>> placed;
    std::vector<TDF_Label> assemblies;
    for (int at = 1; at <= labels.Length(); ++at) {
      const TDF_Label& assembly = labels.Value(at);
      if (!XCAFDoc_ShapeTool::IsAssembly(assembly)) continue;
      assemblies.push_back(assembly);
      NCollection_Sequence<TDF_Label> components;
      XCAFDoc_ShapeTool::GetComponents(assembly, components, false);
      for (int place = 1; place <= components.Length(); ++place) {
        const TDF_Label& component = components.Value(place);
        TDF_Label referred;
        XCAFDoc_ShapeTool::GetReferredShape(component, referred);
        TopLoc_Location location = XCAFDoc_ShapeTool::GetLocation(component);
        auto& others = placed[{entry(referred), location.HashCode()}];
        bool same = false;
        for (const TopLoc_Location& other : others) same = same || location.IsEqual(other);
        if (same) {
          moved_.emplace_back(component, location);
          location = TopLoc_Location(location.Transformation());
          XCAFDoc_Location::Set(component, location);
        }
        others.push_back(location);
      }
    }
    if (!moved_.empty()) {
      for (const TDF_Label& assembly : assemblies) {
        for (TDF_AttributeIterator it(assembly); it.More(); it.Next()) {
          occ::handle<TNaming_NamedShape> named = occ::handle<TNaming_NamedShape>::DownCast(it.Value());
          if (!named.IsNull()) versions_.emplace_back(named, named->Version());
        }
      }
      tool_->UpdateAssemblies();
    }
  }
  ~UsagesApart() {
    if (moved_.empty()) return;
    for (const auto& [component, location] : moved_) XCAFDoc_Location::Set(component, location);
    tool_->UpdateAssemblies();
    for (const auto& [named, version] : versions_) named->SetVersion(version);
  }

 private:
  occ::handle<XCAFDoc_ShapeTool> tool_;
  std::vector<std::pair<TDF_Label, TopLoc_Location>> moved_;
  std::vector<std::pair<occ::handle<TNaming_NamedShape>, int>> versions_;
};

// --- step_style.write_visual_styles ------------------------------------------------------------------------------

using StyleSurface = std::tuple<occ::handle<StepVisual_PresentationStyleAssignment>, int,
                                occ::handle<StepVisual_SurfaceStyleUsage>>;

// step_style._surface: a styled item's first surface style usage, with its assignment and place.
bool surface_of(const occ::handle<StepVisual_StyledItem>& style, StyleSurface& found) {
  for (int i = 1; i <= style->NbStyles(); ++i) {
    occ::handle<StepVisual_PresentationStyleAssignment> assignment = style->StylesValue(i);
    if (assignment.IsNull()) continue;
    for (int j = 1; j <= assignment->NbStyles(); ++j) {
      occ::handle<StepVisual_SurfaceStyleUsage> usage = assignment->StylesValue(j).SurfaceStyleUsage();
      if (!usage.IsNull()) {
        found = {assignment, j, usage};
        return true;
      }
    }
  }
  return false;
}

// step_style._fill_colour: whether a surface side style fills with a colour.
bool fills(const occ::handle<StepVisual_SurfaceSideStyle>& side) {
  if (side.IsNull()) return false;
  for (int i = 1; i <= side->NbStyles(); ++i) {
    occ::handle<StepVisual_SurfaceStyleFillArea> fill = side->StylesValue(i).SurfaceStyleFillArea();
    if (fill.IsNull()) continue;
    occ::handle<StepVisual_FillAreaStyle> area = fill->FillArea();
    if (area.IsNull()) continue;
    for (int j = 1; j <= area->NbFillStyles(); ++j) {
      occ::handle<StepVisual_FillAreaStyleColour> colour = area->FillStylesValue(j).FillAreaStyleColour();
      if (!colour.IsNull() && !colour->FillColour().IsNull()) return true;
    }
  }
  return false;
}

double linear_to_srgb(double channel) {
  return channel <= 0.0031308 ? channel * 12.92 : 1.055 * std::pow(channel, 1 / 2.4) - 0.055;
}

struct Look {
  double ambient, diffuse, specular, exponent;
  std::array<double, 3> rgb;
  bool operator<(const Look& o) const {
    return std::tie(ambient, diffuse, specular, exponent, rgb) < std::tie(o.ambient, o.diffuse, o.specular, o.exponent, o.rgb);
  }
};

// step_style._template: the reflectance records OCCT has no class for, parsed from a small STEP text, so they are
// written back as read.
std::vector<occ::handle<Standard_Transient>> reflectance_records(const std::vector<Look>& looks) {
  std::string text = "ISO-10303-21;\nHEADER;\nFILE_DESCRIPTION((''),'2;1');\nFILE_NAME('','',(''),(''),'','','');\n"
                     "FILE_SCHEMA(('AP242_MANAGED_MODEL_BASED_3D_ENGINEERING_MIM_LF'));\nENDSEC;\nDATA;\n";
  char line[512];
  for (size_t i = 0; i < looks.size(); ++i) {
    const Look& l = looks[i];
    int a = 2 * (int)i + 1, b = 2 * (int)i + 2;
    std::snprintf(line, sizeof line, "#%d=SURFACE_STYLE_REFLECTANCE_AMBIENT_DIFFUSE_SPECULAR(%.12e,%.12e,%.12e,%.12e,#%d);",
                  a, l.ambient, l.diffuse, l.specular, l.exponent, b);
    text += line;
    text += '\n';
    std::snprintf(line, sizeof line, "#%d=COLOUR_RGB('',%.12e,%.12e,%.12e);", b, l.rgb[0], l.rgb[1], l.rgb[2]);
    text += line;
    if (i + 1 < looks.size()) text += '\n';
  }
  text += "\nENDSEC;\nEND-ISO-10303-21;";
  std::istringstream stream(text);
  STEPCAFControl_Reader reader;
  if (reader.ReadStream("appearance", stream) != IFSelect_RetDone)
    throw std::runtime_error("could not construct STEP appearance records");
  occ::handle<StepData_StepModel> model = reader.Reader().StepModel();
  std::vector<occ::handle<Standard_Transient>> found;
  for (size_t i = 0; i < looks.size(); ++i) found.push_back(model->Value(2 * (int)i + 1));
  return found;
}

bool write_visual_styles(STEPCAFControl_Writer& writer, const occ::handle<TDocStd_Document>& doc) {
  occ::handle<XSControl_WorkSession> ws = writer.ChangeWriter().WS();
  STEPConstruct_Styles styles(ws);
  styles.LoadStyles();
  std::map<const Standard_Transient*, std::vector<occ::handle<StepVisual_StyledItem>>> by_item;
  for (int i = 1; i <= styles.NbStyles(); ++i) {
    occ::handle<StepVisual_StyledItem> style = styles.Style(i);
    if (!style->Item().IsNull()) by_item[style->Item().get()].push_back(style);
  }
  occ::handle<XCAFDoc_ShapeTool> tool = XCAFDoc_DocumentTool::ShapeTool(doc->Main());
  NCollection_Sequence<TDF_Label> labels;
  tool->GetShapes(labels);
  occ::handle<Transfer_FinderProcess> finder = ws->TransferWriter()->FinderProcess();
  struct Target { occ::handle<StepVisual_StyledItem> styled; StyleSurface surface; occ::handle<XCAFDoc_VisMaterial> visual; };
  std::vector<Target> targets;  // a dict by styled item, in insertion order
  for (int i = 1; i <= labels.Length(); ++i) {
    const TDF_Label& part = labels.Value(i);
    if (XCAFDoc_ShapeTool::IsAssembly(part)) continue;
    NCollection_Sequence<TDF_Label> subs;
    XCAFDoc_ShapeTool::GetSubShapes(part, subs);
    std::vector<TDF_Label> held{part};
    for (int j = 1; j <= subs.Length(); ++j) held.push_back(subs.Value(j));
    for (const TDF_Label& label : held) {
      occ::handle<XCAFDoc_VisMaterial> visual = XCAFDoc_VisMaterialTool::GetShapeMaterial(label);
      if (visual.IsNull() || !visual->HasPbrMaterial()) continue;
      TopoDS_Shape shape = XCAFDoc_ShapeTool::GetShape(label);
      std::vector<TopoDS_Shape> shapes;
      if (label == part || shape.ShapeType() == TopAbs_COMPOUND || shape.ShapeType() == TopAbs_COMPSOLID) {
        for (TopExp_Explorer e(shape, TopAbs_SOLID); e.More(); e.Next()) shapes.push_back(e.Current());
        if (shapes.empty())
          for (TopExp_Explorer e(shape, TopAbs_FACE); e.More(); e.Next()) shapes.push_back(e.Current());
        if (shapes.empty()) shapes.push_back(shape);
      } else {
        shapes.push_back(shape);
      }
      for (const TopoDS_Shape& one : shapes) {
        occ::handle<StepRepr_RepresentationItem> item = STEPConstruct::FindEntity(finder, one);
        if (item.IsNull()) continue;
        auto styled_items = by_item.find(item.get());
        if (styled_items == by_item.end()) continue;
        for (const occ::handle<StepVisual_StyledItem>& styled : styled_items->second) {
          StyleSurface surface;
          if (!surface_of(styled, surface)) continue;
          if (std::string(std::get<0>(surface)->DynamicType()->Name()) == "StepVisual_PresentationStyleByContext") continue;
          if (!fills(std::get<2>(surface)->Style())) continue;
          // A material on a solid or face wins over its parent's when both map to one styled item.
          bool replaced = false;
          for (Target& t : targets)
            if (t.styled == styled) { t.surface = surface; t.visual = visual; replaced = true; }
          if (!replaced) targets.push_back({styled, surface, visual});
        }
      }
    }
  }
  if (targets.empty()) return false;

  std::map<Look, size_t> look_at;
  std::vector<Look> looks;
  struct Detail { Target target; std::array<double, 3> diffuse; Look look; };
  std::vector<Detail> details;
  for (const Target& t : targets) {
    const XCAFDoc_VisMaterialPBR& pbr = t.visual->PbrMaterial();
    const Quantity_Color& color = pbr.BaseColor.GetRGB();
    const std::array<double, 3> base = {color.Red(), color.Green(), color.Blue()};
    double metal = std::max(0., std::min(1., (double)pbr.Metallic));
    double rough = std::max(0., std::min(1., (double)pbr.Roughness));
    std::array<double, 3> spec;
    for (int c = 0; c < 3; ++c) spec[c] = .04 * (1. - metal) + base[c] * metal;
    double remaining = 1. - std::max({spec[0], spec[1], spec[2]});
    double diffuse_factor = std::max(0., std::min(1., .96 * (1. - metal) / std::max(remaining, 1e-6)));
    Look look{0.2, diffuse_factor, 1., 128. * (1. - rough),
              {linear_to_srgb(spec[0]), linear_to_srgb(spec[1]), linear_to_srgb(spec[2])}};
    if (!look_at.count(look)) {
      look_at[look] = looks.size();
      looks.push_back(look);
    }
    details.push_back({t, base, look});
  }
  std::vector<occ::handle<Standard_Transient>> records = reflectance_records(looks);
  occ::handle<Interface_InterfaceModel> model = writer.ChangeWriter().Model();
  for (const Detail& d : details) {
    const auto& [assignment, selected, usage] = d.target.surface;
    Quantity_Color color(d.diffuse[0], d.diffuse[1], d.diffuse[2], Quantity_TOC_RGB);
    occ::handle<StepVisual_Colour> encoded = STEPConstruct_Styles::EncodeColor(color);
    STEPConstruct_RenderingProperties props;
    props.Init(color, 1. - d.target.visual->PbrMaterial().BaseColor.Alpha());
    props.SetAmbientDiffuseAndSpecularReflectance(d.look.ambient, d.look.diffuse, d.look.specular, d.look.exponent,
                                                  Quantity_Color(d.look.rgb[0], d.look.rgb[1], d.look.rgb[2],
                                                                 Quantity_TOC_RGB));
    occ::handle<StepVisual_SurfaceStyleRenderingWithProperties> rendering = props.CreateRenderingProperties(encoded);
    occ::handle<NCollection_HArray1<StepVisual_RenderingPropertiesSelect>> selectors = rendering->Properties();
    StepVisual_RenderingPropertiesSelect selector;
    selector.SetValue(records[look_at[d.look]]);
    selectors->SetValue(selectors->Length(), selector);
    // The assignment's path cloned: the writer may share a style between objects.
    occ::handle<StepVisual_SurfaceSideStyle> original_side = usage->Style();
    std::vector<StepVisual_SurfaceStyleElementSelect> old;
    for (int i = 1; i <= original_side->NbStyles(); ++i)
      if (original_side->StylesValue(i).SurfaceStyleRendering().IsNull()) old.push_back(original_side->StylesValue(i));
    StepVisual_SurfaceStyleElementSelect rendering_select;
    rendering_select.SetValue(rendering);
    old.push_back(rendering_select);
    auto values = new NCollection_HArray1<StepVisual_SurfaceStyleElementSelect>(1, (int)old.size());
    for (size_t i = 0; i < old.size(); ++i) values->SetValue((int)i + 1, old[i]);
    occ::handle<StepVisual_SurfaceSideStyle> side = new StepVisual_SurfaceSideStyle();
    side->Init(original_side->Name(), values);
    occ::handle<StepVisual_SurfaceStyleUsage> replacement_usage = new StepVisual_SurfaceStyleUsage();
    replacement_usage->Init(usage->Side(), side);
    StepVisual_PresentationStyleSelect newselect;
    newselect.SetValue(replacement_usage);
    auto choices = new NCollection_HArray1<StepVisual_PresentationStyleSelect>(1, assignment->NbStyles());
    for (int i = 1; i <= assignment->NbStyles(); ++i)
      choices->SetValue(i, i == selected ? newselect : assignment->StylesValue(i));
    occ::handle<StepVisual_PresentationStyleAssignment> replacement = new StepVisual_PresentationStyleAssignment();
    replacement->Init(choices);
    const occ::handle<StepVisual_StyledItem>& styled = d.target.styled;
    auto assignments = new NCollection_HArray1<occ::handle<StepVisual_PresentationStyleAssignment>>(1, styled->NbStyles());
    for (int i = 1; i <= styled->NbStyles(); ++i)
      assignments->SetValue(i, styled->StylesValue(i) == assignment ? replacement : styled->StylesValue(i));
    styled->SetStyles(assignments);
    model->AddWithRefs(replacement);
  }
  return true;
}

// --- step._settle: the written bytes made a function of the document alone --------------------------------------

const std::string PRESENTATION = "MECHANICAL_DESIGN_GEOMETRIC_PRESENTATION_REPRESENTATION";

bool digit(char c) { return c >= '0' && c <= '9'; }
bool space(char c) { return c == ' ' || c == '\t' || c == '\n' || c == '\r' || c == '\f' || c == '\v'; }

// _QUOTED's end: from an opening quote at `at`, past its closing quote ('' inside a string is a quote).
size_t quoted_end(const std::string& s, size_t at) {
  size_t i = at + 1;
  while (i < s.size()) {
    if (s[i] == '\'') {
      if (i + 1 < s.size() && s[i + 1] == '\'') { i += 2; continue; }
      return i + 1;
    }
    ++i;
  }
  return std::string::npos;  // an unclosed quote is no string (the regex would not match it)
}

// _QUOTED.sub(b"''", text): every string blanked.
std::string blanked(const std::string& s) {
  std::string out;
  out.reserve(s.size());
  size_t i = 0;
  while (i < s.size()) {
    if (s[i] == '\'') {
      size_t end = quoted_end(s, i);
      if (end != std::string::npos) { out += "''"; i = end; continue; }
    }
    out += s[i++];
  }
  return out;
}

// _REFERENCE.findall: every #n's number.
std::vector<long> references(const std::string& s) {
  std::vector<long> found;
  for (size_t i = 0; i < s.size(); ++i) {
    if (s[i] == '#' && i + 1 < s.size() && digit(s[i + 1])) {
      size_t j = i + 1;
      long n = 0;
      while (j < s.size() && digit(s[j])) n = n * 10 + (s[j++] - '0');
      found.push_back(n);
      i = j - 1;
    }
  }
  return found;
}

// _one_line: the writer's line breaks taken out of a record's text (see step.py).
std::string one_line(const std::string& text) {
  if (text.find('\n') == std::string::npos) return text;
  std::string out;
  bool inside = false;  // pieces between quotes, alternately outside and inside a string
  size_t i = 0;
  while (i < text.size()) {
    char c = text[i];
    if (c == '\'') { inside = !inside; out += c; ++i; continue; }
    if (!inside) {
      // _BREAK: \r?\n then spaces.
      if (c == '\r' && i + 1 < text.size() && text[i + 1] == '\n') { i += 2; while (i < text.size() && text[i] == ' ') ++i; continue; }
      if (c == '\n') { ++i; while (i < text.size() && text[i] == ' ') ++i; continue; }
    } else if (c == '\r' || c == '\n') {
      ++i;
      continue;
    }
    out += c;
    ++i;
  }
  return out;
}

struct Records {
  size_t start = 0, end = 0;     // the tail's place in the data
  std::vector<long> order;       // record numbers, in the file's order
  std::map<long, std::string> text;
  std::map<long, std::vector<long>> refs;
};

// The file's records from the first presentation on, to ENDSEC: _RECORD's heads, each record to the next head.
bool tail_records(const std::string& data, Records& r) {
  size_t found = data.find(PRESENTATION);
  if (found == std::string::npos) return false;
  size_t nl = data.rfind("\n#", found);
  r.start = nl == std::string::npos ? 0 : nl + 1;
  r.end = data.find("ENDSEC;", found);
  if (r.end == std::string::npos) r.end = data.size();
  // Heads: at a line's start (the tail's start too), '#', digits, spaces, '='.
  std::vector<std::pair<size_t, long>> heads;
  for (size_t i = r.start; i < r.end; ++i) {
    if ((i == r.start || data[i - 1] == '\n') && data[i] == '#') {
      size_t j = i + 1;
      long n = 0;
      if (j >= r.end || !digit(data[j])) continue;
      while (j < r.end && digit(data[j])) n = n * 10 + (data[j++] - '0');
      while (j < r.end && space(data[j])) ++j;
      if (j < r.end && data[j] == '=') heads.emplace_back(i, n);
    }
  }
  for (size_t at = 0; at < heads.size(); ++at) {
    size_t from = heads[at].first, to = at + 1 < heads.size() ? heads[at + 1].first : r.end;
    long n = heads[at].second;
    std::string text = data.substr(from, to - from);
    r.text[n] = text;
    r.order.push_back(n);
    r.refs[n] = references(blanked(text.substr(text.find('=') + 1)));
  }
  return true;
}

std::string rstrip_newlines(const std::string& s) {
  size_t n = s.size();
  while (n && (s[n - 1] == '\r' || s[n - 1] == '\n')) --n;
  return s.substr(0, n);
}

bool starts_after_equals(const std::string& record, const char* word) {
  size_t eq = record.find('=');
  size_t i = eq + 1;
  while (i < record.size() && space(record[i])) ++i;
  return record.compare(i, std::strlen(word), word) == 0;
}

// step._prune_unused_styles
std::string prune_unused_styles(const std::string& data) {
  Records r;
  if (!tail_records(data, r)) return data;
  std::map<long, int> counts;
  for (const auto& [n, refs] : r.refs)
    for (long ref : refs) counts[ref] += 1;
  std::vector<long> pending;
  for (long n : r.order)
    if (starts_after_equals(r.text[n], "PRESENTATION_STYLE_ASSIGNMENT(")) pending.push_back(n);
  std::set<long> removed;
  while (!pending.empty()) {
    long n = pending.back();
    pending.pop_back();
    if (removed.count(n) || !r.text.count(n) || counts[n]) continue;
    removed.insert(n);
    for (long ref : r.refs[n])
      if (--counts[ref] == 0) pending.push_back(ref);
  }
  std::string out = data.substr(0, r.start);
  for (long n : r.order)
    if (!removed.count(n)) out += r.text[n];
  out += data.substr(r.end);
  return out;
}

// step._presentations
std::string presentations(const std::string& data) {
  Records r;
  if (!tail_records(data, r)) return data;
  auto arguments = [&](long n) {
    std::string text = blanked(r.text.at(n));
    size_t open = text.find('(', text.find('='));
    size_t close = text.rfind(')');
    if (open == std::string::npos || close == std::string::npos) throw std::invalid_argument("no arguments");
    std::string body = text.substr(open + 1, close - open - 1);
    std::vector<std::string> split;
    int depth = 0;
    size_t begun = 0;
    for (size_t at = 0; at < body.size(); ++at) {
      if (body[at] == '(') ++depth;
      else if (body[at] == ')') --depth;
      else if (body[at] == ',' && depth == 0) { split.push_back(body.substr(begun, at - begun)); begun = at + 1; }
    }
    split.push_back(body.substr(begun));
    return split;
  };
  auto first_ref = [](const std::string& argument) -> long {
    std::vector<long> found = references(argument);
    return found.empty() ? 0 : found[0];
  };
  using Key = std::pair<long, std::vector<long>>;
  auto styled = [&](long n) -> Key {
    std::vector<std::string> given = arguments(n);
    std::vector<long> targets;
    for (long item : references(given.size() > 1 ? given[1] : std::string())) {
      if (!r.text.count(item)) { targets.push_back(item); continue; }
      try {
        std::vector<std::string> inner = arguments(item);
        if (inner.size() < 3) throw std::invalid_argument("short");
        targets.push_back(first_ref(inner[2]));
      } catch (const std::invalid_argument&) {
        targets.push_back(item);
      }
    }
    return {first_ref(given.back()), targets};
  };
  std::vector<std::pair<Key, long>> keyed;
  for (long n : r.order)
    if (r.text[n].substr(0, 120).find(PRESENTATION) != std::string::npos) keyed.push_back({styled(n), n});
  std::stable_sort(keyed.begin(), keyed.end(), [](const auto& a, const auto& b) { return a.first < b.first; });
  std::map<long, long> placed;
  std::vector<long> by_place;
  long first = r.order.empty() ? 0 : r.order[0];
  auto place = [&](long number) {
    std::vector<long> stack{number};
    while (!stack.empty()) {
      long current = stack.back();
      stack.pop_back();
      if (placed.count(current) || !r.text.count(current)) continue;
      placed[current] = first + (long)placed.size();
      by_place.push_back(current);
      const std::vector<long>& refs = r.refs[current];
      for (auto it = refs.rbegin(); it != refs.rend(); ++it) stack.push_back(*it);
    }
  };
  for (const auto& [key, n] : keyed) place(n);
  for (long n : r.order) place(n);
  auto renumber = [&](const std::string& piece, std::string& out) {
    for (size_t i = 0; i < piece.size(); ++i) {
      if (piece[i] == '#' && i + 1 < piece.size() && digit(piece[i + 1])) {
        size_t j = i + 1;
        long n = 0;
        while (j < piece.size() && digit(piece[j])) n = n * 10 + (piece[j++] - '0');
        auto found = placed.find(n);
        out += '#';
        out += std::to_string(found == placed.end() ? n : found->second);
        i = j - 1;
      } else {
        out += piece[i];
      }
    }
  };
  std::string settled;
  for (long n : by_place) {
    const std::string& text = r.text[n];
    std::string body = rstrip_newlines(text);
    std::string rewritten;
    size_t at = 0;
    while (at < body.size()) {
      size_t quote = body.find('\'', at);
      size_t end = quote == std::string::npos ? std::string::npos : quoted_end(body, quote);
      if (quote == std::string::npos || end == std::string::npos) {
        renumber(body.substr(at), rewritten);
        break;
      }
      renumber(body.substr(at, quote - at), rewritten);
      rewritten += body.substr(quote, end - quote);
      at = end;
    }
    settled += one_line(rewritten) + text.substr(body.size());
  }
  return data.substr(0, r.start) + settled + data.substr(r.end);
}

// step._occurrences: NEXT_ASSEMBLY_USAGE_OCCURRENCE('<id>', ...) numbered from 1 in the file's order, each on one
// line.
std::string occurrences(const std::string& data) {
  static const std::string NAME = "NEXT_ASSEMBLY_USAGE_OCCURRENCE";
  std::string out;
  out.reserve(data.size());
  size_t at = 0;
  long counter = 1;
  while (true) {
    size_t found = data.find(NAME, at);
    if (found == std::string::npos) break;
    // \s*\(\s*'\d*'
    size_t i = found + NAME.size();
    while (i < data.size() && space(data[i])) ++i;
    bool ok = i < data.size() && data[i] == '(';
    if (ok) { ++i; while (i < data.size() && space(data[i])) ++i; ok = i < data.size() && data[i] == '\''; }
    if (ok) { ++i; while (i < data.size() && digit(data[i])) ++i; ok = i < data.size() && data[i] == '\''; }
    size_t rest = i + 1, end = std::string::npos;
    if (ok) {
      // ((?:'(?:[^']|'')*'|[^';])*;)
      size_t j = rest;
      while (j < data.size()) {
        if (data[j] == '\'') {
          size_t q = quoted_end(data, j);
          if (q == std::string::npos) break;
          j = q;
        } else if (data[j] == ';') {
          end = j + 1;
          break;
        } else {
          ++j;
        }
      }
    }
    if (!ok || end == std::string::npos) {
      out.append(data, at, found + NAME.size() - at);
      at = found + NAME.size();
      continue;
    }
    out.append(data, at, found - at);
    out += NAME + "('" + std::to_string(counter++) + "'" + one_line(data.substr(rest, end - rest));
    at = end;
  }
  out.append(data, at, std::string::npos);
  return out;
}

// step._density_units: each density typed and its unit stated as its number is (g/cm3, the gram as 0.001 kg).
std::string density_units(std::string data) {
  if (data.find("DERIVED_UNIT_ELEMENT") == std::string::npos) return data;
  // The patterns, each tried where its first word stands, on a window of the text after it (a record or two).
  static const std::regex VALUE(R"(^(MEASURE_REPRESENTATION_ITEM\s*\(\s*'density'\s*,\s*)([-+]?[0-9.]+(?:[eE][-+]?[0-9]+)?)(\s*,))");
  static const std::regex MASS(R"(^(DERIVED_UNIT_ELEMENT\s*\(\s*#(\d+)\s*,\s*)3\.(\s*\)\s*;\s*#\2\s*=\s*)\(\s*MASS_UNIT\s*\(\s*\)\s*NAMED_UNIT\s*\(\s*\*\s*\)\s*SI_UNIT\s*\(\s*\$\s*,\s*\.GRAM\.\s*\)\s*\))");
  static const std::regex LENGTH(R"(^(DERIVED_UNIT_ELEMENT\s*\(\s*#(\d+)\s*,\s*)2\.(\s*\)\s*;\s*#\2\s*=\s*\(\s*LENGTH_UNIT\s*\(\s*\)\s*NAMED_UNIT\s*\(\s*\*\s*\)\s*SI_UNIT\s*\(\s*\.CENTI\.\s*,\s*\.METRE\.\s*\)\s*\)))");
  const size_t WINDOW = 512;
  auto substitute = [&](const std::string& text, const char* word, const std::regex& pattern,
                        const std::function<std::string(const std::smatch&)>& replace, int* count) {
    std::string out;
    out.reserve(text.size() + 1024);
    size_t at = 0;
    while (true) {
      size_t found = text.find(word, at);
      if (found == std::string::npos) break;
      std::string window = text.substr(found, WINDOW);
      std::smatch match;
      if (std::regex_search(window, match, pattern)) {
        out.append(text, at, found - at);
        out += replace(match);
        at = found + match.length(0);
        if (count) ++*count;
      } else {
        out.append(text, at, found + 1 - at);
        at = found + 1;
      }
    }
    out.append(text, at, std::string::npos);
    return out;
  };
  data = substitute(data, "MEASURE_REPRESENTATION_ITEM", VALUE,
                    [](const std::smatch& m) { return m.str(1) + "POSITIVE_RATIO_MEASURE(" + m.str(2) + ")" + m.str(3); },
                    nullptr);
  // The last record's number: the kilogram, its measure and the exponents of a mass come after it.
  long last = 0;
  for (size_t i = 0; i < data.size(); ++i) {
    if ((i == 0 || data[i - 1] == '\n') && data[i] == '#' && i + 1 < data.size() && digit(data[i + 1])) {
      size_t j = i + 1;
      long n = 0;
      while (j < data.size() && digit(data[j])) n = n * 10 + (data[j++] - '0');
      while (j < data.size() && space(data[j])) ++j;
      if (j < data.size() && data[j] == '=') last = std::max(last, n);
    }
  }
  long kilogram = last + 1, measure = last + 2, exponents = last + 3;
  std::string gram = "( CONVERSION_BASED_UNIT('gram',#" + std::to_string(measure) + ") MASS_UNIT() NAMED_UNIT(#" +
                     std::to_string(exponents) + ") )";
  int grams = 0;
  data = substitute(data, "DERIVED_UNIT_ELEMENT", MASS,
                    [&](const std::smatch& m) { return m.str(1) + "1." + m.str(3) + gram; }, &grams);
  data = substitute(data, "DERIVED_UNIT_ELEMENT", LENGTH,
                    [](const std::smatch& m) { return m.str(1) + "-3." + m.str(3); }, nullptr);
  if (!grams) return data;
  size_t end = data.rfind("ENDSEC;");
  return data.substr(0, end) + "#" + std::to_string(kilogram) + " = ( MASS_UNIT() NAMED_UNIT(*) SI_UNIT(.KILO.,.GRAM.) );\n" +
         "#" + std::to_string(measure) + " = MASS_MEASURE_WITH_UNIT(MASS_MEASURE(0.001),#" + std::to_string(kilogram) + ");\n" +
         "#" + std::to_string(exponents) + " = DIMENSIONAL_EXPONENTS(0.,1.,0.,0.,0.,0.,0.);\n" + data.substr(end);
}

}  // namespace

std::string step_bytes(Document& doc) {
  if (doc.xcaf.IsNull()) throw std::runtime_error("the document holds no XCAF document to write");
  quiet();
  std::ostringstream stream(std::ios::out | std::ios::binary);
  bool changed_styles = false;
  {
    // The writer defines the translator's parameters: set them once it exists.
    STEPCAFControl_Writer writer;
    Interface_Static::SetCVal("write.step.unit", "MM");
    Interface_Static::SetIVal("write.stepcaf.subshapes.name", 1);
    Interface_Static::SetCVal("write.step.schema", SCHEMA);
    writer.SetNameMode(true);
    writer.SetColorMode(true);
    writer.SetMaterialMode(true);
    writer.SetLayerMode(false);
    {
      UsagesApart apart(doc.xcaf);
      if (!writer.Transfer(doc.xcaf, STEPControl_AsIs)) throw std::runtime_error("could not write the STEP");
    }
    changed_styles = write_visual_styles(writer, doc.xcaf);
    occ::handle<StepData_StepModel> model = occ::handle<StepData_StepModel>::DownCast(writer.ChangeWriter().Model());
    APIHeaderSection_MakeHeader header(model);
    header.SetTimeStamp(new TCollection_HAsciiString(WRITTEN_STAMP));
    header.Apply(model);
    if (writer.WriteStream(stream) != IFSelect_RetDone) throw std::runtime_error("could not write the STEP");
  }
  std::string data = stream.str();
  if (changed_styles) data = prune_unused_styles(data);
  return density_units(occurrences(presentations(data)));
}

}  // namespace vc
