#!/usr/bin/env bash
set -euo pipefail

# Blender as a Python module (bpy), where the `cad` command runs it: the render skill's helper
# (skills/render/scripts/cad_glb.py) in the blender integration's environment, which `cad run` makes for a
# script that imports bpy (bpy 5.2.3 on Python 3.13, without cad: about 430 MB from PyPI on Linux the first
# time, uv's cache after). A model with a motion, an animation and a nested sub-assembly is built and exported
# to a GLB by this checkout's cad; a script beside a copy of the helper loads it, plays its clips in both orders
# and renders a 64x64 Cycles still on the CPU, and an EEVEE one. The suite, tests/python/packages/blender, is
# this job's alone: the package jobs make no bpy environment. The runner gives each test file its own engine,
# state and cache folders. No person's Blender, no GPU.

# shellcheck source=scripts/test/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

cd "$REPO_ROOT"

run_python_unittest "Blender (bpy) render helper tests" "tests/python/packages/blender" "${PACKAGE_SOURCES[@]}"
