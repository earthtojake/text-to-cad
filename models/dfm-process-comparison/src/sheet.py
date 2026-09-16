from cadgen import step, stl
from lib.tray_geometry import tray

@step(out="../STEP/sheet.step")
@stl(out="../STL/sheet.stl")
def sheet():
    return tray("sheet")

if __name__ == "__main__":
    sheet()
