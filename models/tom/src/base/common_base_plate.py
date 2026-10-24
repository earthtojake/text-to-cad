"""Manufacture two identical copies for the Tom base and servo carrier."""
from cadgen import memo
from lib.common_base_plate import common_base_plate as make_plate


@memo
def common_base_plate():
    return make_plate()
