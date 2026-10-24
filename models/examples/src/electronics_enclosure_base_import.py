"""Imported parts: STEP files read back as models, through `read_step`.

The read the old `electronics_enclosure_base_drawing.py` made (the drawing calls
the enclosure's model now): the STEP that `electronics_enclosure_base.py` exported,
as a document of its own, and the mating fixture's STEP (an assembly) the same
way, which exercises the names and colours an imported tree keeps.
Both are fixed inputs committed in `../vendor/`, exported once from the two
source models; no model writes them.
"""

from cadgen import model, read_step

from pathlib import Path

ENCLOSURE_STEP = Path(__file__).parent / "../vendor/electronics_enclosure_base.step"
FIXTURE_STEP = Path(__file__).parent / "../vendor/basic_shape_mating_test_fixture.step"


@model
def electronics_enclosure_base_import():
    return read_step(ENCLOSURE_STEP)


@model
def basic_shape_mating_test_fixture_import():
    return read_step(FIXTURE_STEP)


if __name__ == "__main__":
    electronics_enclosure_base_import()
