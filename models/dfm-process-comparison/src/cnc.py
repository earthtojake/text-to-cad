from cadgen import step, stl
from lib.tray_geometry import tray

@step(out="../STEP/cnc.step")
@stl(out="../STL/cnc.stl")
def cnc():
    return tray("cnc")

if __name__ == "__main__":
    cnc()
