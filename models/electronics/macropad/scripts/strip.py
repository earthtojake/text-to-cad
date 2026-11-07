"""Where the back strip's parts go (all on the bottom): ref -> (x, y, degrees, side).
Angles are as the part reads from above: mirrored by the flip, then turned (board_common)."""
STRIP = {
    # MCU and its own parts
    "U1": (100.0, 65.0, 0, "B"),
    "U2": (107.0, 54.5, 270, "B"),     # flash beside the QSPI corner
    "Y1": (104.2, 72.0, 180, "B"),      # crystal at XIN/XOUT (front, right of centre)
    "C5": (101.3, 71.0, 90, "B"),
    "C6": (107.15, 72.9, 90, "B"),
    "R5": (101.3, 74.3, 0, "B"),
    # USB path: J1 -> U4 (ESD) -> R3/R4 (27R) -> U1
    "U4": (91.0, 58.6, 180, "B"),
    "R3": (94.4, 58.3, 180, "B"),
    "R4": (96.3, 57.65, 180, "B"),
    "R1": (88.1, 57.9, 90, "B"),
    "R2": (95.8, 52.7, 90, "B"),
    # power
    "F1": (81.4, 53.6, 0, "B"),
    "U3": (77.6, 57.6, 0, "B"),
    "C1": (77.6, 54.4, 0, "B"),
    "C2": (74.4, 58.0, 90, "B"),
    "C3": (74.4, 55.3, 270, "B"),
    # boot (by the flash's CS), reset and SWD (in the pocket left of U1)
    "SW11": (114.0, 50.4, 180, "B"),
    "R6": (111.1, 58.6, 180, "B"),
    "SW12": (92.5, 69.6, 90, "B"),
    "R7": (95.2, 68.2, 90, "B"),
    "TP1": (98.08, 73.3, 0, "B"),
    "TP2": (95.54, 73.3, 0, "B"),
    "TP3": (93.0, 73.3, 0, "B"),
    "TP4": (84.0, 64.6, 0, "B"),
    # LED level shifter, by the first LED
    "U5": (74.6, 85.9, 90, "B"),
    "C28": (72.4, 85.9, 270, "B"),
}
# decoupling: each cap beside the pin it serves
STRIP.update({
    "C4": (110.4, 51.4, 90, "B"),    # flash VCC
    "C7": (105.3, 61.6, 180, "B"),     # IOVDD pin 1
    "C8": (105.6, 66.0, 180, "B"),    # IOVDD pin 10
    "C9": (94.8, 65.05, 0, "B"),     # IOVDD pin 22
    "C10": (94.8, 66.0, 0, "B"),     # IOVDD pin 33
    "C11": (94.6, 61.4, 0, "B"),     # IOVDD pin 42
    "C12": (95.08, 59.75, 270, "B"),   # IOVDD pin 49
    "C13": (99.9, 57.2, 0, "B"),    # USB_VDD pin 48
    "C14": (96.03, 59.75, 270, "B"),    # ADC_AVDD pin 43
    "C15": (96.98, 59.75, 270, "B"),    # VREG_VIN pin 44 (1 uF)
    "C16": (97.93, 59.75, 270, "B"),    # VREG_VOUT pin 45 (1 uF)
    "C17": (99.6, 70.1, 90, "B"),    # DVDD pin 23
})
# a 100 nF at each LED, just outside its VDD pad
from board_common import LED_DOWN, LED_KEY, key_xy  # noqa: E402

for k, key in enumerate(LED_KEY):
    x, y = key_xy(key)
    y += LED_DOWN
    if (key // 3) % 2 == 0:   # rows 1 and 3: VDD bottom right; the cap lies under it, +5V pad first
        STRIP[f"C{19 + k}"] = (x + 2.9, y + 2.4, 180, "B")
    else:                      # row 2: VDD top left; the cap stands beside it
        STRIP[f"C{19 + k}"] = (x - 4.475, y - 0.75, 90, "B")
