"""Finishing-vocabulary sampler: one coupon exercising every shared helper.

Not part of the watch — a pipeline smoke test and a standing macro coupon
for judging the finishing vocabulary (anglage, stripes, perlage, snailing,
screws, jewels, wheels, heart cam) before it is spent on real parts.
"""

from build123d import Color, Compound, Pos, Rot

import _spec as S
import _finishing as F


def gen_step():
    parts = []

    # striped, anglage-beveled bridge coupon
    bridge = F._box(14.0, 8.0, 1.0)
    bridge = Pos(0, 0, -0.5) * bridge  # top at z=0
    stripes = F.geneva_stripes_cutter(14.0, 8.0)
    bridge = bridge - stripes
    bridge, applied = F.anglage_top(bridge, S.ANGLAGE_WIDTH)
    bridge = bridge - Pos(4.0, 2.0, 0) * F.jewel_countersink_cut()
    bridge.color = Color(*S.COPPER_GOLD)
    bridge.label = "striped_bridge_coupon"
    parts.append(bridge)

    ruby = F.jeweled_bearing()
    ruby = Pos(4.0, 2.0, 0) * ruby
    ruby.label = "bridge_jewel"
    parts.append(ruby)

    screw = F.slotted_screw()
    screw = Pos(-4.5, -2.0, 0) * screw
    screw.label = "blued_screw"
    parts.append(screw)

    # perlage plate coupon
    plate = Pos(0, -11.0, -0.6) * F._box(14.0, 8.0, 1.2)
    plate = plate - [Pos(0, -11.0, 0) * s for s in F.perlage_cutter(14.0, 8.0)]
    plate.color = Color(*S.COPPER_GOLD)
    plate.label = "perlage_plate_coupon"
    parts.append(plate)

    # snailed ratchet-style wheel
    snailed = F.train_wheel(48, 9.0, web_thickness=0.4, spoke_count=0, color=S.GILT)
    snailed = snailed - Pos(0, 0, 0.2) * F.snailing_cutter(8.2, 1.6)
    snailed = Pos(12.0, -6.0, 0.2) * snailed
    snailed.label = "snailed_wheel"
    parts.append(snailed)

    # crossed-out train wheel + pinion
    wheel = F.train_wheel(64, 8.0)
    wheel = Pos(12.5, 4.0, 0.09) * wheel
    wheel.label = "train_wheel"
    parts.append(wheel)

    pin = F.pinion(8, 1.6, 1.6)
    pin = Pos(12.5, 4.0, 0.8) * pin
    pin.label = "pinion"
    parts.append(pin)

    cam = F.heart_cam()
    cam = Pos(-11.0, 3.0, 0) * cam
    cam.label = "heart_cam"
    parts.append(cam)

    return Compound(children=parts, label="finishing_sampler")
