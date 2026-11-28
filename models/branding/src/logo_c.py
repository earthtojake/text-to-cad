from cad import xbf

from lib.logo_shape import make_logo


@xbf
def logo_c():
    return make_logo("C")


if __name__ == "__main__":
    logo_c()
