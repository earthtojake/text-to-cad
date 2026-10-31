"""Work instruction for the planetary gear assembly ($work-instructions sample).

A manual sample, not a test fixture, laid out at the default `production`
rigor. It cites no process spec, because this demo assembly has none, so it
states no torque, adhesive or cure value either. It calls the assembly's
model, which the engine replays when it already holds it.
"""

from cadgen.work_instruction import Instruction, work_instruction
from planetary_gear_assembly import planetary_gear_assembly


@work_instruction(out="../../PDF/planetary_gear_assembly/planetary_gear_assembly_wi.pdf")
def planetary_gear_assembly_wi():
    wi = Instruction(planetary_gear_assembly(),
                     title="PLANETARY GEAR ASSEMBLY", number="WI-DEMO-001", revision="A",
                     scope="Assembly of the demo planetary gear stage from its machined parts.",
                     revisions=[("A", "2026-10-23", "First issue")])

    wi.operation("Prepare the carrier")
    wi.step("Place the carrier plate on the bench, pin bosses up", install=["carrier_plate"])

    wi.operation("Install the planet pins")
    for n in (1, 2, 3):
        wi.step(f"Press planet pin {n} into the carrier", install=[f"planet_pin_{n}"]).caution(
            "Support the carrier under the boss while pressing.")

    wi.operation("Install the gears")
    for n in (1, 2, 3):
        wi.step(f"Slide planet gear {n} onto its pin", install=[f"planet_gear_{n}_18_teeth"])
    wi.step("Insert the sun gear between the planets", install=["sun_gear_24_teeth"]).instruct(
        "Rotate the sun gear until it meshes with all three planets.")
    (wi.step("Fit the ring gear over the planets", install=["ring_gear_60_internal_teeth"])
       .inspect("The stage turns through one full carrier revolution without binding"))
    return wi


if __name__ == "__main__":
    planetary_gear_assembly_wi()
