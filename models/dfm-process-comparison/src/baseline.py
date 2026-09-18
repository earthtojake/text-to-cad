from cadgen import step, stl
from lib.tray_geometry import tray

@step(out="../STEP/baseline.step")
@stl(out="../STL/baseline.stl")
def baseline():
    return tray("baseline")

if __name__ == "__main__":
    baseline()
