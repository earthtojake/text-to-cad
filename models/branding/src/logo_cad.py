from cadgen import step
from lib.logo_shape import make_logo


@step(out="../STEP/logo_cad.step")
def logo_cad():
    return make_logo("CAD")


if __name__ == "__main__":
    logo_cad()
