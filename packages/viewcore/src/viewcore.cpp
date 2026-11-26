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

}  // namespace

extern "C" {

uint32_t vc_abi_version(void) { return VC_ABI_VERSION; }

const char* vc_occt_version(void) { return OCC_VERSION_COMPLETE; }

const char* vc_last_error(void) { return last_error.c_str(); }

void* vc_alloc(uint32_t size) { return std::malloc(size ? size : 1); }

void vc_free(void* ptr) { std::free(ptr); }

int32_t vc_open_xbf(const uint8_t* data, uint32_t size) {
  return guarded<int32_t>(0, [&] {
    if (!data && size) throw std::invalid_argument("no data");
    auto doc = vc::open_xbf(data, size);
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

uint8_t* vc_structure(int32_t doc, uint32_t* out_len) {
  return guarded<uint8_t*>(nullptr, [&] { return result(vc::structure(document(doc)), out_len); });
}

uint8_t* vc_shape_bytes(int32_t doc, int32_t index, uint32_t* out_len) {
  return guarded<uint8_t*>(nullptr, [&] { return result(part(doc, index).bytes, out_len); });
}

uint8_t* vc_mesh(int32_t doc, int32_t index, uint32_t* out_len) {
  return guarded<uint8_t*>(nullptr, [&] { return result(vc::mesh_bytes(part(doc, index).bytes), out_len); });
}

uint8_t* vc_fact(int32_t doc, int32_t index, int32_t kind, int32_t ordinal, uint32_t* out_len) {
  return guarded<uint8_t*>(nullptr, [&] {
    vc::Part& p = part(doc, index);
    if (!p.topology) p.topology = std::make_unique<vc::Topology>(p.bytes);
    vc::Json out;
    switch (kind) {
      case VC_FACE: p.topology->face(out, ordinal); break;
      case VC_EDGE: p.topology->edge(out, ordinal); break;
      case VC_VERTEX: p.topology->vertex(out, ordinal); break;
      default: throw std::invalid_argument("no element kind " + std::to_string(kind));
    }
    return result(out.out, out_len);
  });
}

uint8_t* vc_groups(int32_t doc, int32_t index, uint32_t* out_len) {
  return guarded<uint8_t*>(nullptr, [&] {
    vc::Topology topology(part(doc, index).bytes);
    vc::Json out;
    topology.groups(out);
    return result(out.out, out_len);
  });
}

uint8_t* vc_elements(int32_t doc, int32_t index, uint32_t* out_len) {
  return guarded<uint8_t*>(nullptr, [&] {
    vc::Topology topology(part(doc, index).bytes);
    vc::Json out;
    topology.elements(out);
    return result(out.out, out_len);
  });
}

uint8_t* vc_measure(int32_t doc, int32_t index, uint32_t* out_len) {
  return guarded<uint8_t*>(nullptr, [&] {
    vc::Json out;
    vc::measured(out, part(doc, index).bytes);
    return result(out.out, out_len);
  });
}

}  // extern "C"
