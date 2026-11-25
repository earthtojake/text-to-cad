"""Every part's place, board-local millimetres (x right, y down from the board's top-left corner):
ref -> (x, y, rotation, side). LFO A's parts (1xx); board_02_place.py puts each LFO B twin (2xx) 25 mm right.

Zones (LFO-local): the panel column at x = 11.5; between the pots (y 12-31) the TL074 and the Schmitt
trigger; beside the jacks, right (x 12.8-22.3), the LM13700, the exponential converter and the OTA drive;
beside the jacks, left (x 0.3-10.2), the output resistors and the LED's. Lanes: x 0.6-5 (left) and
x 18-22 (right) carry the signals between the zones; the rails run at x 22.3 (F.Cu +12 V) and 22.4 (B.Cu -12 V)."""

from boardlib import JACK_Y

PLACE = {
    # --- the panel parts, front: one column at x = 11.5 -----------------------------------------
    "RV101": (14.0, 2.5, 270, "F"),        # RATE: shaft at (11.5, 10), pins above it
    "RV102": (9.0, 40.5, 90, "F"),         # SHAPE: shaft at (11.5, 33), pins below it
    "D103": (12.77, 46.0, 180, "F"),       # bicolour LED, centre (11.5, 46); LED_A pad toward the left
    "J101": (11.5, JACK_Y[0], 0, "F"),     # CV in
    "J102": (11.5, JACK_Y[1], 0, "F"),     # TRI out
    "J103": (11.5, JACK_Y[2], 0, "F"),     # SQR out
    "J104": (11.5, JACK_Y[3], 0, "F"),     # MIX out
    # --- TL074 between the pots ----------------------------------------------------------------------
    "U101": (11.5, 21.5, 90, "B"),         # upper edge 8-14: mix, V-, buffer; lower edge 7-1: Schmitt, V+, servo
    "C104": (9.95, 13.6, 180, "B"),        # V- (pin 11), on the -12 V drop
    "C103": (11.5, 28.4, 270, "B"),        # V+ (pin 4), under its via
    "C102": (17.6, 15.0, 90, "B"),         # integrator capacitor (C0G 1206), on the INTEG run
    "R110": (7.69, 27.0, 270, "B"),        # COMP -> SQ
    "R107": (5.2, 30.6, 0, "B"),           # SQ -> SCH_IN
    "R106": (8.9, 30.6, 0, "B"),           # TRI -> SCH_IN
    "D102": (4.0, 26.6, 0, "B"),           # SQ clamp
    # --- LM13700, exponential converter and OTA drive, right of the jacks ----------------------------
    "U102": (17.55, 58.0, 270, "B"),       # OTA pins 1-8 on its upper edge
    "C106": (21.2, 63.4, 90, "B"),         # V- (pin 10), lower edge
    "C105": (19.2, 63.4, 270, "B"),        # V+ (pin 11), lower edge
    "R113": (15.645, 52.6, 270, "B"),      # OTA drive -> GND, its GND pad over U102 pin 3
    "R111": (19.4, 53.0, 0, "B"),          # SQ -> OTA drive
    "R101": (14.6, 43.0, 90, "B"),         # wiper -> QB
    "Q101": (17.2, 43.4, 90, "B"),
    "Q102": (20.8, 43.4, 90, "B"),
    "R103": (14.6, 46.8, 90, "B"),         # QB -> GND
    "C101": (17.6, 46.8, 0, "B"),          # servo compensation
    "R104": (21.0, 47.2, 90, "B"),         # servo out -> emitters
    "R105": (13.4, 50.4, 90, "B"),         # 5.6M to -12 V
    "D101": (18.4, 49.85, 0, "B"),         # emitter clamp
    "R102": (14.6, 64.2, 90, "B"),         # CV -> QB
    # --- outputs, left of the jacks -------------------------------------------------------------------
    "R109": (7.6, 46.0, 0, "B"),           # TRI -> LED
    "R108": (8.4, 75.8, 0, "B"),           # TRI -> J102 tip
    "R112": (8.4, 90.2, 0, "B"),           # SQ -> J103 tip
    "R114": (8.4, 104.6, 0, "B"),          # MIX -> J104 tip
}
SHARED = {
    "J1": (24.0 - 1.27, 98.0, 0, "B"),     # Eurorack header, centred on the board, pin 1 (-12 V) bottom right
    "D1": (24.0, 73.0, 90, "B"),           # +12 V reverse-polarity Schottky
    "D2": (24.0, 66.0, 90, "B"),           # -12 V reverse-polarity Schottky
    "FB1": (24.0, 60.5, 90, "B"),
    "FB2": (24.0, 57.0, 90, "B"),
    "C1": (24.0, 52.5, 90, "B"),           # +12 V bulk
    "C2": (24.0, 47.5, 90, "B"),           # -12 V bulk
    "TP1": (24.0, 34.0, 0, "B"),
    "TP2": (24.0, 38.2, 0, "B"),
    "TP3": (24.0, 79.3, 0, "B"),
}
