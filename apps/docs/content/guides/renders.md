---
title: Renders
description: Photoreal stills, turntables and films of a model with Blender, drafted in EEVEE and finished in Cycles, with no Blender app needed.
---

A render is a picture for people: a hero shot, a README image, a product post, a turntable or a film of a mechanism moving. Your agent exports the model to a GLB (a binary glTF 3D file), loads it into Blender as a Python module, lights and frames it in a script, and renders it. You end up with a PNG, an mp4, or a `.blend` file you can keep working on.

Renders are for looking, not measuring. A lens, lighting and depth of field make a poor ruler, so geometry is checked with `cad model snapshot` instead.

## What to ask

- "Render a hero shot of the enclosure at 1080p on a plain light background."
- "Make a transparent PNG of the bracket for the README."
- "Do a four-second turntable of the gearbox as an mp4."
- "Render a film of the hinge sweeping through its motion, draft first so I can check the framing."
- "Save the scene as a `.blend` so I can adjust the lighting in Blender myself."

## What your agent does

1. Exports the model to a GLB, meshed finer than the viewer's mesh so facets do not show in a close-up:

   ```bash
   cad model export "$ID" scene.glb --tolerance 0.02 --angle 5
   ```

   `$ID` is the model's id, which running its script prints. A STEP file exports the same way with `cad step export`. The GLB is a copy, so it is exported again after every model change.
2. Writes a `render.py` that starts from an empty scene (`bpy.ops.wm.read_factory_settings(use_empty=True)`), loads the GLB with `cad.blender.load`, and adds a camera, lights and a world. The camera is framed from the model's box (`model.center`, `model.size`).
3. Runs a draft in EEVEE, Blender's fast engine, at the final's size. A 1080p frame takes about 2 seconds:

   ```bash
   cad run render.py
   ```

4. Looks at the draft for framing, camera height, light direction and anything missing, and adjusts.
5. Runs the final in Cycles, Blender's path tracer, with the same scene:

   ```bash
   cad run render.py --final
   ```

   Cycles uses the GPU where there is one (Metal, CUDA, OptiX, HIP or oneAPI) and the CPU otherwise, with OpenImageDenoise cleaning the noise.
6. For a turntable or a film, checks three frames (first, middle, last) as EEVEE stills before rendering every frame. A turntable turns the camera once around the model. A film plays a motion or animation clip with `model.play(name)` and writes an H.264 mp4.

Your agent always loads the GLB with `cad.blender.load` rather than Blender's own glTF importer alone. Blender's importer poses every moving part at its clip's first frame and leaves only the first clip live. `load` puts parts back where the model places them and plays the clip asked for.

Looks come from the model, not the render script. If a render shows the wrong finish, change it in the model and export again.

## What you need

- Nothing beyond text-to-cad. The first `cad run` of a script that imports `bpy` makes an environment on Python 3.13 holding Blender 5.2 LTS as a Python module (the `blender` integration, `cad[blender]`). It downloads about 262 MB on a Mac, 356 MB on Windows or 430 MB on Linux, plus a Python 3.13 (65 MB), once. The Blender app is never started.
- A supported platform: macOS on Apple silicon, Linux x86-64, Windows x86-64 or Windows arm64. There is no build for Intel Macs or Linux on ARM, and `cad run` refuses a Blender script there by name.
- A GPU is optional. Cycles on the GPU is far quicker, but the CPU works. In the skill's measurements, a 1080p frame of a 537-part assembly took 23 to 26 seconds on an M1 Max's GPU and 2.5 to 3.5 minutes on its CPU.
- Your own Blender settings and add-ons are not used.

## What you get

- A PNG at the path the script sets, such as `hero.png` and `hero-draft.png`, or an mp4 for a film. A transparent background is one setting for a page or a post.
- Optionally `scene.blend`, saved at the end of the script, with the model, its clips, camera, lights and render settings. You can open it in Blender 5.2.
- The script stays the source. The images, films and `.blend` are outputs that running it makes again, so they are not committed.

The first `import bpy` takes 11 to 18 seconds, and the first Cycles render on a Mac's GPU compiles kernels once, about 3.5 minutes.

## Limits

- A render is not evidence for geometry or dimensions.
- EEVEE and Cycles disagree about glass, lenses, diffusers and glow. For those, your agent drafts in Cycles at 32 to 64 samples instead of trusting an EEVEE draft.
- A machine with no graphics driver, such as a headless Linux server or container without `libEGL`, cannot run EEVEE: the process ends with no Python error. The agent drafts in Cycles on the CPU there.
- Smoked glass written as a dark colour with partial transmission renders black. The model should write it as `transmission=1` with the tint as its colour.
- A film costs every frame's render, and a Cycles film on the CPU takes hours. Blender keeps a Cycles render's memory until its process ends, so each final gets a run of its own.

## Go deeper

- [The render skill](repo:skills/render/SKILL.md), [the scene script reference](repo:skills/render/references/scene-script.md) (framing, lights, GPU setup) and [shots](repo:skills/render/references/shots.md) (turntables, films, motion blur, glow, a `.blend`).
- [The Blender integration](/docs/integrations/blender), and [the GLB document type](/docs/document-types/glb).
- [Mechanisms](/docs/guides/mechanisms): the motions a film can play.
- [The CAD Viewer](/docs/guides/cad-viewer), for looking at a model without a render.
