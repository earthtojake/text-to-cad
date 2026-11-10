#!/usr/bin/env bash
set -euo pipefail

# Blender as a Python module (bpy), where the `cad` command runs it: cad.blender.load in the environment
# `cad run` makes for a script that imports bpy -- cad's blender integration, cad[blender], on Python 3.13,
# the one bpy is built for (about 430 MB from PyPI on Linux the first time, uv's cache after). A model with a
# motion, an animation and a nested sub-assembly is built and exported to a GLB by this checkout's cad; one
# script that imports cad, build123d and bpy then builds a part, loads each GLB, plays the clips in both
# orders and renders a 64x64 Cycles still on the CPU, and an EEVEE one. Open in's Blender script
# (cad_server/_internal/open_in_blender.py) imports a GLB and an STL, removing the startup scene's objects only
# once the import has finished, and leaves the scene as it was for a file it cannot open. The suite,
# tests/python/packages/blender, is this job's alone: the package jobs make no bpy environment. The runner gives
# each test file its own engine, state and cache folders. No person's Blender, no GPU.
#
# On CI the job exists to run this suite whole, so a test that skips there (no build of bpy for the platform, no
# OpenGL for EEVEE) fails the run; a developer's machine without either still skips, saying why.

# shellcheck source=scripts/test/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

cd "$REPO_ROOT"

if [ "${CI:-}" = "true" ]; then
  export PYTHON_TEST_NO_SKIPS=1
fi

run_python_unittest "Blender (bpy) load, render and Open in tests" "tests/python/packages/blender" "${PACKAGE_SOURCES[@]}"
