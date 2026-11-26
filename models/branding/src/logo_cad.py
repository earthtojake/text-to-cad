from cad import xbf

from lib.logo_shape import make_logo


@xbf
def logo_cad():
    return make_logo("CAD")


if __name__ == "__main__":
    logo_cad()
