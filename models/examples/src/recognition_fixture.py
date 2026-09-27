"""Read-only recognition test: one slot, one hole, and an exterior boss."""
from cadgen import step


@step(out="../STEP/recognition-fixture.step")
def recognition_fixture():
    from cadgen import build123d as bd
    with bd.BuildPart() as part:
        bd.Box(70, 36, 6)
        with bd.BuildSketch(bd.Plane.XY.offset(-4)):
            with bd.Locations((-12, 0)):
                bd.SlotOverall(30, 8)
        bd.extrude(amount=8, mode=bd.Mode.SUBTRACT)
        with bd.Locations((22, 0, 0)):
            bd.Cylinder(3, 10, mode=bd.Mode.SUBTRACT)
        with bd.Locations((22, 12, 5)):
            bd.Cylinder(3, 4)
    return part.part


if __name__ == "__main__":
    recognition_fixture()
    # Recognition must work on the imported artifact, without recipe history.
    from pathlib import Path
    from build123d import import_step
    from cadgen._internal.surface_extract import extract_surface_component

    step_path = Path(__file__).resolve().parent.parent / "STEP" / "recognition-fixture.step"
    imported = import_step(step_path)
    assert imported.is_valid and len(imported.solids()) == 1
    step_path.with_suffix(".surf").write_bytes(extract_surface_component(imported.wrapped))
