from cadgen import model

from lib.logo_shape import make_logo


@model
def logo_c():
    return make_logo("C")


if __name__ == "__main__":
    logo_c()
