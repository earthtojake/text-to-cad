from kicad_enclosure import build_assembly


def gen_step():
    return {"shape": build_assembly(with_usb_cutout=True)}
