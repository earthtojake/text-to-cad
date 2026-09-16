from cadgen import step, stl
from lib.tray_geometry import tray

@step(out="../STEP/fdm.step")
@stl(out="../STL/fdm.stl")
def fdm():
    return tray("fdm")

if __name__ == "__main__":
    fdm()
