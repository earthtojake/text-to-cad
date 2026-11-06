"""Build guide for the planetary gear assembly ($work-instructions sample).

A manual sample, not a test fixture, at the default `simple` rigor: a picture
guide anyone can follow. It calls the assembly's model, which the engine
replays when it already holds it.
"""

from cad.work_instruction import Instruction, work_instruction
from planetary_gear_assembly import planetary_gear_assembly


@work_instruction(out="../../PDF/planetary_gear_assembly/planetary_gear_assembly_wi.pdf")
def planetary_gear_assembly_wi():
    wi = Instruction(planetary_gear_assembly(), title="Planetary gear set",
                     scope="Three small gears turning inside a big one.",
                     names={"Carrier plate": ["carrier_plate"],
                            "Pin": ["planet_pin_1", "planet_pin_2", "planet_pin_3"],
                            "Small gear": ["planet_gear_1_18_teeth", "planet_gear_2_18_teeth", "planet_gear_3_18_teeth"],
                            "Center gear": ["sun_gear_24_teeth"],
                            "Ring gear": ["ring_gear_60_internal_teeth"]})

    wi.step("Lay the plate flat", install=["carrier_plate"])
    wi.step("Push a pin into each hole", arrow="down",
            install=["planet_pin_1", "planet_pin_2", "planet_pin_3"]).caution(
        "Hold the plate from underneath while you push.")
    wi.step("Slide a small gear onto each pin", arrow="down",
            install=["planet_gear_1_18_teeth", "planet_gear_2_18_teeth", "planet_gear_3_18_teeth"])
    wi.step("Drop the center gear in the middle", arrow="down", install=["sun_gear_24_teeth"]).instruct(
        "Turn it a little until its teeth catch all three small gears.")
    wi.step("Fit the ring around the outside", arrow="down", install=["ring_gear_60_internal_teeth"]).inspect(
        "Spin the plate one full turn. Everything should turn smoothly.")
    return wi


if __name__ == "__main__":
    planetary_gear_assembly_wi()
