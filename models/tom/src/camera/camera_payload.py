"""SO-101 BOM camera: four front M2 x 6 socket caps, with nuts behind the PCB."""
from cadgen import memo
from purchased.innomaker_u20cam import innomaker_u20cam
from hardware.hex_socket_cap import hex_socket_m2x6
from hardware.hex_nut_m2 import hex_nut_m2
from lib.camera_payload_geometry import build_payload

@memo
def camera_payload():
    return build_payload(innomaker_u20cam(),hex_socket_m2x6(),hex_nut_m2())
