from cad import xbf

from lib.logo_shape import make_logo


@xbf
def logo_texttocad():
    # "TO" (letters 5 and 6) is the lighter blue.
    return make_logo("TEXTTOCAD", lighter=(4, 5))


if __name__ == "__main__":
    logo_texttocad()
