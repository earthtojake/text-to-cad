"""Body panels and saddle, all lofted from the spec section tables.

Leg shield (apron), steering cover (head-tube shroud), under-seat body, seat,
and rear fender. Cream panels, deep-cream rear body, brown saddle.
"""

import _lib as L
import _spec as S


def build_leg_shield():
    shield = L.loft_path_xz(
        S.LEG_SHIELD_SECTIONS, S.LEG_SHIELD_TH, S.LEG_SHIELD_CORNER,
    )
    return L.paint(shield, "leg_shield", "apron", color=S.CREAM)


def build_steering_cover():
    cover = L.loft_path_xz(
        S.FRONT_COVER_SECTIONS, S.FRONT_COVER_TH, 6.0,
    )
    return L.paint(cover, "steering_cover", "head_tube", color=S.CREAM_DEEP)


def build_under_seat_body():
    body = L.loft_x_sections(S.REAR_BODY_SECTIONS, S.REAR_BODY_CORNER)
    return L.paint(body, "under_seat_body", color=S.CREAM_DEEP)


def build_rear_fender():
    r_mid = (S.REAR_FENDER_R0 + S.REAR_FENDER_R1) / 2
    band = L.revolve_band(
        S.REAR_AXLE, r_mid,
        S.REAR_FENDER_R1 - S.REAR_FENDER_R0, S.REAR_FENDER_HALF_WIDTH,
        S.REAR_FENDER_ANGLES[0], S.REAR_FENDER_ANGLES[1],
        corner=3.0,
    )
    return L.paint(band, "rear_fender", color=S.CREAM)


def build_seat():
    seat = L.loft_x_sections(S.SEAT_SECTIONS, S.SEAT_CORNER)
    return L.paint(seat, "seat", "saddle", color=S.SEAT_BROWN)
