---
title: Integrations
description: What an integration is in text-to-cad, how each is named, and how the tools behind them reach your computer.
---

An integration is text-to-cad's support for one third-party tool. It is named for the tool, such as `kicad` or `mujoco`, and never for a capability, and it has one extra, `cad[<name>]`, that groups the packages the support needs.

The tool stays the tool's. Its Python API and its command line are not renamed or repeated: a script imports the tool as it is, and `cad run <command>` runs its own commands. text-to-cad adds only what is missing without it, such as a result shape every check shares, a guarantee the tool does not give, or the tie between the tool's objects and your model.

Integrations install on first need. You install none of them. The first time something needs one, the `cad` command makes an environment for it and keeps it. A script run with `cad run` gets the extras its imports use. [What a model runs in](/docs/install#what-a-model-runs-in) explains the environments.
