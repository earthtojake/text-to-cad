"""Imported parts: STEP files read back as models, through `read_step`.

The read the old `electronics_enclosure_base_drawing.py` made (the drawing calls
the enclosure's model now): the STEP that `electronics_enclosure_base.py` exports,
as a document of its own, and the mating fixture's STEP (an assembly) the same
way, which exercises the names and colours an imported tree keeps.
Running the script exports both models into the project's `STEP/` first (gitignored,
as every export is; Git holds no CAD files) and reads them back from there, so run it
before opening either import model.
"""

from cad import export, model, read_step

from pathlib import Path

from basic_shape_mating_test_fixture import basic_shape_mating_test_fixture
from electronics_enclosure_base import electronics_enclosure_base

ENCLOSURE_STEP = Path(__file__).parent / "../STEP/electronics_enclosure_base.step"
FIXTURE_STEP = Path(__file__).parent / "../STEP/basic_shape_mating_test_fixture.step"


@model
def electronics_enclosure_base_import():
    return read_step(ENCLOSURE_STEP)


@model
def basic_shape_mating_test_fixture_import():
    return read_step(FIXTURE_STEP)


if __name__ == "__main__":
    export(electronics_enclosure_base, ENCLOSURE_STEP)
    export(basic_shape_mating_test_fixture, FIXTURE_STEP)
    electronics_enclosure_base_import()
    basic_shape_mating_test_fixture_import()
