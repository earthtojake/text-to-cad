---
title: Renders
description: The render skill makes photoreal stills, turntables and films of a model with Blender, drafted in EEVEE and finished in Cycles, with no Blender app needed.
---

A render is a picture for people: a hero shot, a README image, a product post, a turntable or a film of a mechanism moving. The `render` skill makes them with Blender, loaded as a Python module, from a scene script your agent writes.

Renders are for looking, not measuring. A lens, lighting and depth of field make a poor ruler, so a render is not evidence for geometry or dimensions: those are checked with `cad model snapshot`.

## What it makes

- A PNG at the path the script sets, such as `hero.png` and `hero-draft.png`, or an mp4 for a film. A transparent background is one setting.
- Optionally `scene.blend`, with the model, its clips, camera, lights and render settings, to keep working on in Blender 5.2.

The script is the source. Its images, films and `.blend` are outputs that running it makes again, so they are not committed.

## How it works

The model is exported to a GLB (a binary glTF 3D file), meshed finer than the viewer's mesh so facets do not show in a close-up:

```bash
cad model export "$ID" scene.glb --tolerance 0.02 --angle 5
```

`$ID` is the model's id, which running its script prints. A STEP file exports the same way with `cad step export`. The GLB is a copy, so it is exported again after every model change.

Your agent writes a `render.py` that starts from an empty scene (`bpy.ops.wm.read_factory_settings(use_empty=True)`), loads the GLB with `cad.blender.load`, and adds a camera, lights and a world framed from the model's box (`model.center`, `model.size`). Blender's own glTF importer poses every moving part at its clip's first frame and leaves only the first clip live; `load` puts parts back where the model places them and plays the clip asked for.

The same scene runs twice, as a draft and as a final:

```bash
cad run render.py
cad run render.py --final
```

The draft is EEVEE, Blender's fast engine, at the final's size; a 1080p frame takes about 2 seconds. Your agent checks it for framing, camera height, light direction and anything missing. The final is Cycles, Blender's path tracer, on the GPU where there is one (Metal, CUDA, OptiX, HIP or oneAPI) and the CPU otherwise, with OpenImageDenoise cleaning the noise.

A turntable turns the camera once around the model. A film plays a motion or animation clip with `model.play(name)` and writes an H.264 mp4. For either, the first, middle and last frames are checked as EEVEE stills before every frame is rendered.

Looks come from the model, not the render script. A wrong finish is changed in the model and exported again.

## What it needs

- Nothing beyond text-to-cad. The first `cad run` of a script that imports `bpy` makes an environment on Python 3.13 holding Blender 5.2 LTS as a Python module (the `blender` integration, `cad[blender]`). It downloads about 262 MB on a Mac, 356 MB on Windows or 430 MB on Linux, plus a Python 3.13 (65 MB), once. The Blender app is never started, and your own Blender settings and add-ons are not used.
- A supported platform: macOS on Apple silicon, Linux x86-64, Windows x86-64 or Windows arm64. There is no build for Intel Macs or Linux on ARM.
- A GPU is optional. In the skill's measurements, a 1080p frame of a 537-part assembly took 23 to 26 seconds on an M1 Max's GPU and 2.5 to 3.5 minutes on its CPU.

The first `import bpy` takes 11 to 18 seconds, and the first Cycles render on a Mac's GPU compiles kernels once, about 3.5 minutes.

## Ask for it

- "Render a hero shot of the enclosure at 1080p on a plain light background."
- "Do a four-second turntable of the gearbox as an mp4."
- "Render a film of the hinge sweeping through its motion, draft first so I can check the framing."
- "Save the scene as a `.blend` so I can adjust the lighting in Blender myself."

## Limits

- EEVEE and Cycles disagree about glass, lenses, diffusers and glow. For those, the draft is a Cycles render at 32 to 64 samples.
- A machine with no graphics driver, such as a headless Linux server or container without `libEGL`, cannot run EEVEE: the process ends with no Python error. Drafts there are Cycles on the CPU.
- A film costs every frame's render, and a Cycles film on the CPU takes hours. Blender keeps a Cycles render's memory until its process ends, so each final gets a run of its own.

## The skill

The skill is [`render`](repo:skills/render/SKILL.md). Its references:

- [The scene script](repo:skills/render/references/scene-script.md): framing, lights, GPU setup
- [Shots](repo:skills/render/references/shots.md): turntables, films, motion blur, glow, a `.blend`

Related pages: [the Blender integration](/docs/integrations/blender), [the GLB document type](/docs/document-types/glb), [mechanisms and animation](/docs/skills/parts-and-assemblies#mechanisms-and-animation) for the motions a film can play, and [the CAD Viewer](/docs/viewer) for looking at a model without a render.
