---
title: Blender
description: Blender as a Python module, which text-to-cad loads a model's GLB into so a script can light, frame and render it.
---

[Blender](https://www.blender.org) is a free, open source 3D creation suite. Its modelling, shading, lighting and rendering are also available as a Python module, `bpy`, which needs no window.

## What it does, and what text-to-cad adds

Blender already does everything about a scene: cameras, lights, worlds, materials, animation and rendering. A script uses `bpy` as it is, and text-to-cad adds no rendering code and no command.

It adds one helper, `cad.blender.load`. It loads the GLB that cad exported into Blender's scene with every part where the file places it, each part's object reachable by its name, and each motion or animation as a clip that plays alone. The framing, the lights and the render are your script's, written in `bpy`. You ask your agent for a hero shot or a turntable, and it writes and runs that script.

## How it reaches your computer

A script run with `cad run` that imports `bpy` gets `cad[blender]` automatically, in an environment of its own on Python 3.13, which uv fetches. It downloads about 260 MB on a Mac and 430 MB on Linux, and takes about 730 MB on disk. It has no build for Intel Macs or Linux on ARM, where `cad run` refuses such a script by name.

Nothing starts the Blender app. Your own Blender preferences and add-ons never load into a run.

## Related

[Renders](/docs/skills/renders) goes from a model to a finished image or video, starting from a [GLB](/docs/document-types/glb). See the [render skill](repo:skills/render/SKILL.md).
