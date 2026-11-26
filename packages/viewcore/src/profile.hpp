// profile.hpp: where a call's time goes, by fact component (compiled in with -DVC_PROFILE, off by default).
//
// VC_TIMED(ID, statement) runs the statement and charges its wall time to ID; scopes nest, and each is charged only
// its own time (its children's are taken out), so the categories add up to the calls' total. vc_profile() (exported
// only by a profiling build) answers the seconds and counts so far as JSON and starts again. Without VC_PROFILE the
// macros are the bare statement.
//
// The cheaper variants, each its own define, all off by default (each changes an answer; tools/profile.py measures
// them): VC_SHARED_PART, VC_NO_CHECK, VC_NO_FACE_BOX, VC_PLAIN_BOX, VC_OPTIMAL_BOX, VC_UNION_BOX, VC_GPROP_EPS=<eps>
// (see topology.cpp and viewcore.cpp).
#pragma once

#ifdef VC_PROFILE
#include <chrono>
#include <cstdint>
#include <optional>
#include <string>

namespace vc::profile {

#define VC_PROFILE_IDS(X)                                                                                              \
  X(read) X(maps)                                                                                                      \
  X(face_gprop) X(face_gprop_freeform) X(face_adaptor) X(box_scan) X(box_analytic) X(box_analytic_torus) X(box_plain) X(box_support_setup) X(box_support_distance) \
  X(check_analyzer) X(check_probed)                                                                                    \
  X(edge_encode) X(edge_ancestors) X(edge_owners) X(edge_class) X(edge_gprop) X(edge_curve) X(edge_ends) X(vertex)    \
  X(groups_encode) X(groups_ancestors) X(groups_solids) X(groups_edges) X(groups_chains)                              \
  X(measure_solids) X(measure_volume)                                                                                  \
  X(mesh_deflection) X(mesh_brepmesh) X(mesh_extract) X(mesh_assemble)                                                 \
  X(elements_rest) X(groups_rest) X(measure_rest) X(mesh_rest) X(fact_rest) X(open_rest)

enum Id {
#define VC_ID(name) name,
  VC_PROFILE_IDS(VC_ID)
#undef VC_ID
  COUNT
};

struct Scope {
  Id id;
  std::chrono::steady_clock::time_point start;
  double children = 0;
  Scope* parent;
  explicit Scope(Id i);
  ~Scope();
};

std::string dump_and_reset();

}  // namespace vc::profile

#define VC_TIMED(ID, ...)                         \
  do {                                            \
    ::vc::profile::Scope vc_scope_(::vc::profile::ID); \
    __VA_ARGS__;                                  \
  } while (0)
#define VC_SCOPE(ID) ::vc::profile::Scope vc_scope_whole_(::vc::profile::ID)
// VC_TIMED with the category chosen at run time (`using namespace vc::profile` in the expression).
#define VC_TIMED_AS(EXPR, ...)                                                   \
  do {                                                                           \
    ::vc::profile::Scope vc_scope_([&] { using namespace ::vc::profile; return EXPR; }()); \
    __VA_ARGS__;                                                                 \
  } while (0)
// Consecutive phases of one function: each VC_PHASE ends the one before (no other scope may be open across it).
#define VC_PHASES() std::optional<::vc::profile::Scope> vc_phase_
#define VC_PHASE(ID) (vc_phase_.reset(), vc_phase_.emplace(::vc::profile::ID))
#else
#define VC_TIMED(ID, ...) \
  do {                    \
    __VA_ARGS__;          \
  } while (0)
#define VC_SCOPE(ID) ((void)0)
#define VC_TIMED_AS(EXPR, ...) \
  do {                         \
    __VA_ARGS__;               \
  } while (0)
#define VC_PHASES() ((void)0)
#define VC_PHASE(ID) ((void)0)
#endif
