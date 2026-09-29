from cadgen import step
from lib.logo_shape import make_logo


@step(out="../STEP/logo_text2cad.step")
def logo_text2cad():
    return make_logo("TEXT2CAD")


if __name__ == "__main__":
    logo_text2cad()
