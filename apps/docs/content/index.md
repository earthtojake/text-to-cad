---
title: Introduction
description: What text-to-cad is, what it can make, how it works on your computer, and where to start reading.
---

text-to-cad is a plugin for AI agents such as Claude Code, Codex and Cursor. It gives your agent local workflows for CAD: you describe a part, a board or a drawing, and the agent models it, checks it and shows it to you. The CAD work runs on your computer.

It works with any agent that supports plugins or skills. See [supported agents](/docs/agents) for what each one gets.

## What it can make

- **Parts and assemblies**: models written as Python scripts with build123d and OpenCASCADE, exported as STEP, STL, 3MF or GLB, with joints and animations for mechanisms. See [cad](/docs/cad).
- **Circuit boards**: KiCad schematics and boards, placed, routed and checked with electrical and design rule checks (ERC and DRC). See [pcb](/docs/pcb).
- **Manufacturing checks**: whether a part can be machined, cut and bent, moulded or 3D printed, and what to change where it cannot. See [manufacturing checks](/docs/cad#manufacturing-checks).
- **Stress checks**: whether a part, or an assembly of bonded parts, holds under its loads, solved with CalculiX. See [fea](/docs/fea).
- **Engineering drawings**: dimensioned PDF sheets projected from the part's geometry. See [engineering-drawing](/docs/engineering-drawing).
- **Renders**: photoreal stills, turntables and films made with Blender. See [render](/docs/render).
- **Fabrication services**: checks of DXF and STEP files against SendCutSend's guide, and sliced 3D prints sent to Bambu Connect or Bambu Studio. See [sendcutsend](/docs/sendcutsend) and [print3d](/docs/print3d).
- **Robotics and simulation**: URDF for ROS, SRDF for MoveIt and MJCF for MuJoCo. See [robot-simulation](/docs/robot-simulation).

## How it works

Your agent follows the plugin's skills and writes a Python script that describes the model. The `cad` command builds that script on your computer, through a server that stays warm between runs so a change rebuilds only what it touched. The viewer shows the result in your browser, or inside your agent app, and updates as the model is rebuilt.

Files such as STEP or STL are made when you ask for them, not on every run.

## Where to go next

- [Install](/docs/install): one command sets up text-to-cad in every agent app on your computer.
- [Your first model](/docs/first-model): a walk-through from a fresh install to a part on screen.
- Skills: start with [cad](/docs/cad), then see [the viewer](/docs/viewer).
- [The cad command](/docs/reference/cli): the command line, for running things yourself.
- [The cad library](/docs/reference/library): the Python library a model is written with.

text-to-cad is MIT-licensed and built in the open. To take part, see [contributing](/docs/contributing).
