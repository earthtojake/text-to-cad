"""A servo extension: the board's servo 1 header to a servo's three-wire lead.

The board connector's pins are read from the board model's netlist, so a re-pinned header
on the board reaches this cable on its next build.
"""

from cadgen import harness

from servo_power import servo_power


@harness(out="../HARNESS/servo_cable.harness.yml")
def servo_cable():
    h = harness.Harness(title="Servo 1 extension")
    board = h.connector(servo_power(), "J2", name="BOARD_J2", type="Dupont 2.54 mm housing, 1x3",
                        subtype="female",
                        additional_components=[{"type": "Dupont crimp terminal, female", "qty_multiplier": "populated"}])
    servo = h.connector("SERVO", pinlabels=["PWM", "+5V", "GND"], type="Futaba J housing, 3 pin", subtype="male")
    lead = h.cable("W1", colors=["OG", "RD", "BN"], gauge="26 AWG", length=250)
    h.connect(board.pins, lead.wires, servo.pins)
    return h


if __name__ == "__main__":
    servo_cable()
