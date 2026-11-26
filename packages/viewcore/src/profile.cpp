// profile.cpp: the profile's clock and table (see profile.hpp); empty unless built with -DVC_PROFILE.
#ifdef VC_PROFILE
#include "profile.hpp"

#include <cstdlib>
#include <cstring>

#include "core.hpp"
#include "json.hpp"

namespace vc::profile {

namespace {
const char* NAMES[] = {
#define VC_NAME(name) #name,
    VC_PROFILE_IDS(VC_NAME)
#undef VC_NAME
};
double seconds[COUNT];
long counts[COUNT];
Scope* current = nullptr;
}  // namespace

Scope::Scope(Id i) : id(i), start(std::chrono::steady_clock::now()), parent(current) { current = this; }

Scope::~Scope() {
  double elapsed = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
  seconds[id] += elapsed - children;
  counts[id] += 1;
  if (parent) parent->children += elapsed;
  current = parent;
}

std::string dump_and_reset() {
  Json j;
  j.open().key("switches").open_list();
#ifdef VC_FACTS_V1
  j.str("VC_FACTS_V1");
#endif
#ifdef VC_SHARED_PART
  j.str("VC_SHARED_PART");
#endif
#ifdef VC_NO_CHECK
  j.str("VC_NO_CHECK");
#endif
#ifdef VC_NO_FACE_BOX
  j.str("VC_NO_FACE_BOX");
#endif
#ifdef VC_PLAIN_BOX
  j.str("VC_PLAIN_BOX");
#endif
#ifdef VC_OPTIMAL_BOX
  j.str("VC_OPTIMAL_BOX");
#endif
#ifdef VC_UNION_BOX
  j.str("VC_UNION_BOX");
#endif
#ifdef VC_GPROP_EPS
  j.str("VC_GPROP_EPS");
#endif
  j.close_list();
  for (int i = 0; i < COUNT; ++i) {
    if (!counts[i]) continue;
    j.key(NAMES[i]).open_list().num(seconds[i]).integer(counts[i]).close_list();
    seconds[i] = 0;
    counts[i] = 0;
  }
  j.close();
  return j.out;
}

}  // namespace vc::profile

extern "C" uint8_t* vc_profile(uint32_t* out_len) {
  std::string text = vc::profile::dump_and_reset();
  uint8_t* out = static_cast<uint8_t*>(std::malloc(text.size()));
  if (!out) return nullptr;
  std::memcpy(out, text.data(), text.size());
  *out_len = (uint32_t)text.size();
  return out;
}
#endif
