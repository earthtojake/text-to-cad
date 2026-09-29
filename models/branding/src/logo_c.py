from cadgen import step
from lib.logo_shape import make_logo


@step(out="../STEP/logo_c.step")
def logo_c():
    return make_logo("C")


if __name__ == "__main__":
    logo_c()
