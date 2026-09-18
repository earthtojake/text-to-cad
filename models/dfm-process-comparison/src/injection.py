from cadgen import step, stl
from lib.tray_geometry import tray

@step(out="../STEP/injection.step")
@stl(out="../STL/injection.stl")
def injection():
    return tray("injection")

if __name__ == "__main__":
    injection()
