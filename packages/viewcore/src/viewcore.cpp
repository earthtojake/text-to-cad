// viewcore.cpp: the C ABI (include/viewcore.h). Every call catches what the kernel throws and answers NULL (or 0)
// with vc_last_error set; the only state is the table of open documents and the last error.
#include <cstdlib>
#include <cstring>
#include <map>
#include <memory>
#include <new>
#include <stdexcept>
#include <string>

#include <Standard_Failure.hxx>
#include <Standard_Version.hxx>

#include "../include/viewcore.h"
#include "core.hpp"
#include "exports.hpp"
#include "profile.hpp"
#include "render.hpp"

namespace {

std::map<int32_t, std::unique_ptr<vc::Document>> documents;
int32_t next_handle = 1;
std::string last_error;

uint8_t* result(const std::string& data, uint32_t* out_len) {
  uint8_t* out = static_cast<uint8_t*>(std::malloc(data.size() ? data.size() : 1));
  if (!out) throw std::bad_alloc();
  std::memcpy(out, data.data(), data.size());
  if (out_len) *out_len = (uint32_t)data.size();
  return out;
}

vc::Document& document(int32_t doc) {
  auto found = documents.find(doc);
  if (found == documents.end()) throw std::invalid_argument("no open document " + std::to_string(doc));
  return *found->second;
}

vc::Part& part(int32_t doc, int32_t index) {
  vc::Document& d = document(doc);
  if (index < 0 || index >= (int32_t)d.parts.size())
    throw std::out_of_range("the document has no part " + std::to_string(index) + " (it has " +
                            std::to_string(d.parts.size()) + ")");
  return *d.parts[index];
}

// Runs one call; any exception becomes `fallback` with the last error said.
template <typename T, typename F>
T guarded(T fallback, F&& call) {
  try {
    last_error.clear();
    return call();
  } catch (const Standard_Failure& failure) {
    last_error = std::string(failure.ExceptionType()) + ": " + failure.what();
  } catch (const std::exception& error) {
    last_error = error.what();
  } catch (...) {
    last_error = "unknown error";
  }
  if (last_error.empty()) last_error = "error";
  return fallback;
}

// The part's topology kept for its picks and, under VC_SHARED_PART (the default), its whole table, groups and measures.
static vc::Topology& kept(vc::Part& p) {
  if (!p.topology) p.topology = std::make_unique<vc::Topology>(p.bytes);
  return *p.topology;
}

// A whole-part answer from the part's one topology (VC_SHARED_PART), or from its own read (VC_FACTS_V1).
template <typename F>
static uint8_t* with_topology(int32_t doc, int32_t index, uint32_t* out_len, F&& answer) {
  vc::Part& p = part(doc, index);
  vc::Json out;
#if defined(VC_SHARED_PART)
  answer(kept(p), out, p);
#else
  vc::Topology topology(p.bytes);
  answer(topology, out, p);
#endif
  return result(out.out, out_len);
}

}  // namespace

extern "C" {

uint32_t vc_abi_version(void) { return VC_ABI_VERSION; }

const char* vc_occt_version(void) { return OCC_VERSION_COMPLETE; }

const char* vc_last_error(void) { return last_error.c_str(); }

void* vc_alloc(uint32_t size) { return std::malloc(size ? size : 1); }

void vc_free(void* ptr) { std::free(ptr); }

int32_t vc_open_xbf(const uint8_t* data, uint32_t size, const char* stem, uint32_t stem_len) {
  return guarded<int32_t>(0, [&] {
    VC_SCOPE(open_rest);
    if (!data && size) throw std::invalid_argument("no data");
    auto doc = vc::open_xbf(data, size, stem && stem_len ? std::string(stem, stem_len) : std::string());
    int32_t handle = next_handle++;
    documents[handle] = std::move(doc);
    return handle;
  });
}

int32_t vc_open_shape(const uint8_t* data, uint32_t size) {
  return guarded<int32_t>(0, [&] {
    if (!data || !size) throw std::invalid_argument("no data");
    auto doc = vc::open_shape(data, size);
    int32_t handle = next_handle++;
    documents[handle] = std::move(doc);
    return handle;
  });
}

void vc_close(int32_t doc) {
  guarded<int>(0, [&] {
    documents.erase(doc);
    return 0;
  });
}

// A document read from a file: one opened from shape bytes alone has no structure and nothing to export.
static vc::Document& whole(int32_t doc) {
  vc::Document& d = document(doc);
  if (d.loose) throw std::invalid_argument("the handle is of shape bytes alone (vc_open_shape): it holds no document");
  return d;
}

uint8_t* vc_structure(int32_t doc, uint32_t* out_len) {
  return guarded<uint8_t*>(nullptr, [&] { return result(vc::structure(whole(doc)), out_len); });
}

uint8_t* vc_shape_bytes(int32_t doc, int32_t index, uint32_t* out_len) {
  return guarded<uint8_t*>(nullptr, [&] { return result(part(doc, index).bytes, out_len); });
}

uint8_t* vc_mesh(int32_t doc, int32_t index, uint32_t* out_len) {
  return guarded<uint8_t*>(nullptr, [&] {
    VC_SCOPE(mesh_rest);
    // Kept on the part: its exports read it again, and its whole table checks the faces it left unmeshed.
    vc::Part& p = part(doc, index);
    const std::string& body = vc::part_mesh(p);
    p.last_said = p.unmeshed_said;
    return result(body, out_len);
  });
}

uint8_t* vc_mesh_at(int32_t doc, int32_t index, double tolerance, double angle, uint32_t* out_len) {
  return guarded<uint8_t*>(nullptr, [&] {
    VC_SCOPE(mesh_rest);
    vc::Part& p = part(doc, index);
    // Never kept: the part's own mesh is the engine's one tessellation, this one an export's.
    std::map<int, std::string> said;
    std::string body = vc::mesh_bytes(p.bytes, &said, tolerance > 0 ? std::optional<double>(tolerance) : std::nullopt,
                                      angle > 0 ? std::optional<double>(angle) : std::nullopt);
    p.last_said = std::move(said);
    return result(body, out_len);
  });
}

uint8_t* vc_unmeshed(int32_t doc, int32_t index, uint32_t* out_len) {
  return guarded<uint8_t*>(nullptr, [&] {
    vc::Json out;
    out.open();
    for (const auto& [ordinal, text] : part(doc, index).last_said) out.key(ordinal).str(text);
    out.close();
    return result(out.out, out_len);
  });
}

uint8_t* vc_fact(int32_t doc, int32_t index, int32_t kind, int32_t ordinal, uint32_t* out_len) {
  return guarded<uint8_t*>(nullptr, [&] {
    VC_SCOPE(fact_rest);
    vc::Topology& topology = kept(part(doc, index));
    vc::Json out;
    switch (kind) {
      case VC_FACE: topology.face(out, ordinal); break;
      case VC_EDGE: topology.edge(out, ordinal); break;
      case VC_VERTEX: topology.vertex(out, ordinal); break;
      default: throw std::invalid_argument("no element kind " + std::to_string(kind));
    }
    return result(out.out, out_len);
  });
}

uint8_t* vc_groups(int32_t doc, int32_t index, uint32_t* out_len) {
  return guarded<uint8_t*>(nullptr, [&] {
    VC_SCOPE(groups_rest);
    return with_topology(doc, index, out_len, [](vc::Topology& t, vc::Json& out, vc::Part&) { t.groups(out); });
  });
}

uint8_t* vc_elements(int32_t doc, int32_t index, uint32_t* out_len) {
  return guarded<uint8_t*>(nullptr, [&] {
    VC_SCOPE(elements_rest);
    return with_topology(doc, index, out_len,
                         [](vc::Topology& t, vc::Json& out, vc::Part& p) { t.elements(out, p.unmeshed); });
  });
}

uint8_t* vc_table(int32_t doc, int32_t index, const int32_t* unmeshed, uint32_t count, uint32_t* out_len) {
  return guarded<uint8_t*>(nullptr, [&] {
    VC_SCOPE(elements_rest);
    if (!unmeshed && count) throw std::invalid_argument("no ordinals");
    std::set<int> given(unmeshed, unmeshed + count);
    return with_topology(doc, index, out_len,
                         [&](vc::Topology& t, vc::Json& out, vc::Part&) { t.elements(out, given); });
  });
}

uint8_t* vc_measure(int32_t doc, int32_t index, uint32_t* out_len) {
  return guarded<uint8_t*>(nullptr, [&] {
    VC_SCOPE(measure_rest);
    vc::Part& p = part(doc, index);
    vc::Json out;
#if defined(VC_SHARED_PART)
    vc::measured(out, p.bytes, &kept(p));
#else
    vc::measured(out, p.bytes);
#endif
    return result(out.out, out_len);
  });
}

uint8_t* vc_step(int32_t doc, uint32_t* out_len) {
  return guarded<uint8_t*>(nullptr, [&] { return result(vc::step_bytes(whole(doc)), out_len); });
}

uint8_t* vc_stl(int32_t doc, uint32_t* out_len) {
  return guarded<uint8_t*>(nullptr, [&] { return result(vc::stl_bytes(whole(doc)), out_len); });
}

uint8_t* vc_3mf(int32_t doc, uint32_t* out_len) {
  return guarded<uint8_t*>(nullptr, [&] { return result(vc::threemf_bytes(whole(doc)), out_len); });
}

uint8_t* vc_glb(int32_t doc, uint32_t* out_len) {
  return guarded<uint8_t*>(nullptr, [&] { return result(vc::glb_bytes(whole(doc)), out_len); });
}

uint8_t* vc_render(const char* scene, uint32_t scene_len, const uint8_t* blob, uint32_t blob_len, uint32_t* out_len) {
  return guarded<uint8_t*>(nullptr, [&] {
    if (!scene) throw std::invalid_argument("no scene");
    if (!blob && blob_len) throw std::invalid_argument("no payloads");
    return result(vc::render(std::string(scene, scene_len), blob, blob_len), out_len);
  });
}

}  // extern "C"
