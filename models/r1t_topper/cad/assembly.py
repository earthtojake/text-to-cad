"""Phase 2 review assembly: vehicle references plus concept topper envelope."""

from cadpy.assembly import AssemblyHelper

from topper_envelope import build_topper_concept_subassembly
from vehicle_reference import build_reference_subassembly, make_coordinate_reference


def gen_step():
    assembly = AssemblyHelper("R1T_TOPPER_ASSEMBLY")
    assembly.add(build_reference_subassembly(), "00_REFERENCE")
    assembly.add(build_topper_concept_subassembly(), "10_TOPPER_CONCEPT")
    assembly.add(make_coordinate_reference(), "90_REVIEW_COORDINATE_REFERENCE")
    return assembly.build()
