"""Checkpoint 1 review assembly: reference envelopes only."""

from cadpy.assembly import AssemblyHelper

from vehicle_reference import build_reference_subassembly, make_coordinate_reference


def gen_step():
    assembly = AssemblyHelper("R1T_TOPPER_ASSEMBLY")
    assembly.add(build_reference_subassembly(), "00_REFERENCE")
    assembly.add(make_coordinate_reference(), "90_REVIEW_COORDINATE_REFERENCE")
    return assembly.build()
