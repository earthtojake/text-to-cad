"""Opt-in modal/structural FEA for STEP geometry via Netgen + ngsolve.

The heavy solver stack (``ngsolve``, ``netgen``) is imported lazily inside
``cadpy_fea.modal`` so the CLI, ``--help``, and the material table stay usable
without it. Install the extras to enable solving::

    pip install ngsolve netgen-occt

This is a first-pass linear-elastic modal estimate for design iteration, not a
certified structural analysis.
"""
