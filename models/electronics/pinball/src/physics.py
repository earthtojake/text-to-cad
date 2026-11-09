"""SHORT CIRCUIT's physics at its scale, in numbers: the ball, the playfield's pitch, the flippers, the
plunger and the power budget. Plain arithmetic from the parts' data and layout.py; run it to print them.

    python3 src/physics.py

Sources: Takaha CA0730 catalogue drawing and force-stroke graph (6 % duty, 24 V: 8.2 N at the 4 mm nominal
stroke; coil CA07300160, 16 ohm: rated 6 V at 100 %, 12 V at 25 %, 24 V at 6 %); AISI 52100 density 7.81 g/cm3;
Worldsemi/Opsco SK6812MINI-E 12 mA a channel; ISSI IS31FL3741 datasheet; Maxim MAX98357A datasheet.
"""
from __future__ import annotations

import math

import layout as L

G = 9.81

# ----------------------------------------------------------------------------------------------- the ball
STEEL = 7810.0                              # kg/m3, AISI 52100
r = L.BALL_R / 1000
m_ball = STEEL * 4 / 3 * math.pi * r ** 3   # kg
theta = math.radians(L.TILT_DEG)
a_roll = 5 / 7 * G * math.sin(theta)        # a solid sphere rolling down the pitch
field = (L.TOP_LANE_Y[0] - L.FLIPPER_Y) / 1000   # top lanes to the flippers, m
t_drop = math.sqrt(2 * field / a_roll)      # from rest at the lanes to the flippers
v_drop = a_roll * t_drop


def ball():
    return {"diameter_mm": L.BALL_D, "mass_g": m_ball * 1000, "pitch_deg": L.TILT_DEG,
            "rolling_accel_m_s2": a_roll, "lanes_to_flippers_s": t_drop, "arrives_m_s": v_drop}


# ----------------------------------------------------------------------------------------------- the flippers
# Pull force against the air gap g (mm), F = K / (g + G0)^2, fitted to the catalogue's 6 % point (8.2 N at
# 4 mm, 36 W) and scaled by electrical power (force goes with (N I)^2, so with V^2 / R for one coil).
COIL_R = 16.0                                # ohm, CA07300160
G0 = 3.0                                     # mm: the curve's knee (the graph's shape near closure)
K_36W = 8.2 * (4.0 + G0) ** 2
STROKE = 4.0                                 # mm, nominal
CRANK = 4.3                                  # mm: 4 mm of pull turns the bat 55 degrees
BAT_MASS = 1.1e-3                            # kg: resin bat with rubber, steel shaft, crank (as modelled)
BAT_I = 1.6e-7                               # kg m2 about the pivot (bat ~1.0e-7, crank, shaft, plunger reflected)
PLUNGER_MASS = 5.6e-3                        # kg: a 7 mm steel plunger, ~20 mm long


def coil_force(gap_mm, volts):
    power = volts ** 2 / COIL_R
    return K_36W * (power / 36.0) / (gap_mm + G0) ** 2


def coil_energy(volts, stroke=STROKE):
    """Work over the stroke (J): the integral of K/(g+G0)^2 from 0 to the stroke."""
    power = volts ** 2 / COIL_R
    k = K_36W * (power / 36.0)
    return k * (1 / G0 - 1 / (stroke + G0)) / 1000      # N*mm -> J


def flipper(volts=9.0):
    e = coil_energy(volts)
    # the hit: the ball meets the bat 15 mm from the pivot; the coil's work is shared by the bat, the
    # plunger (reflected through the crank) and the ball riding the bat (reflected through 15/4.3)
    r_hit = 15.0e-3
    m_eff_plunger = PLUNGER_MASS + BAT_I / (CRANK / 1000) ** 2
    m_eff_ball = m_ball * (r_hit / (CRANK / 1000)) ** 2
    v_plunger = math.sqrt(2 * e / (m_eff_plunger + m_eff_ball))
    omega = v_plunger / (CRANK / 1000)
    v_ball = omega * r_hit
    t_stroke = 2 * (STROKE / 1000) / v_plunger       # from rest under ~uniform push
    return {"coil_V": volts, "coil_A": volts / COIL_R, "coil_W": volts ** 2 / COIL_R,
            "force_at_4mm_N": coil_force(4.0, volts), "force_at_1mm_N": coil_force(1.0, volts),
            "work_per_stroke_mJ": e * 1000, "ball_off_bat_m_s": v_ball, "bat_rad_s": omega,
            "stroke_ms": t_stroke * 1000, "rotation_deg": math.degrees(2 * math.asin(STROKE / 2 / CRANK)),
            "ball_needs_to_reach_top_m_s": math.sqrt(2 * a_roll * (L.ARCH_TOP - L.FLIPPER_Y) / 1000)}


# ----------------------------------------------------------------------------------------------- the plunger
SPRING_K = 0.08                              # N/mm: a close-wound extension spring, music wire 0.42 mm on a
                                             # 5.5 mm mean diameter, 22 coils: G d^4 / (8 D^3 n) = 0.084
PULL = 14.0                                  # mm of pull at full
ROD_MASS = 4.2e-3                            # kg: brass rod 3 x 32 mm (2.0 g), knob, collar, tip
COR = 0.8                                    # tip on ball


def plunger(pull=PULL):
    e = 0.5 * SPRING_K * 1000 * (pull / 1000) ** 2      # J
    e_rod = 0.75 * e                         # friction in the bushing, the spring's own mass
    v_rod = math.sqrt(2 * e_rod / ROD_MASS)
    v_ball = (1 + COR) * ROD_MASS / (ROD_MASS + m_ball) * v_rod
    lane = (L.SHOOTER_WALL_Y[1] - L.BALL_READY_Y + (L.ARCH_TOP - L.SHOOTER_WALL_Y[1])) / 1000
    v_min = math.sqrt(2 * a_roll * lane)
    return {"spring_N_mm": SPRING_K, "pull_mm": pull, "stored_mJ": e * 1000, "ball_m_s": v_ball,
            "needs_m_s_to_round_the_arch": v_min, "pull_for_min_mm": pull * v_min / v_ball}


# ----------------------------------------------------------------------------------------------- power
def power():
    """The worst moment and the steady state, at the board's input (USB-C PD 9 V)."""
    leds = 18 + 3 + 2 + 3 + 12                # inserts and lamps, bumpers, slings, targets, underglow
    led_full = leds * 3 * 0.012               # A at 5 V, every LED white
    led_cap = 0.35 * led_full                  # firmware caps brightness at 35 %
    dmd = 351 * 0.005 * (60 / 351)             # ~60 lit dots at 5 mA average (IS31FL3741, 1/9 scan)
    audio_peak = 2.5 / 5.0 / 0.85              # 2.5 W into 4 ohm, 85 % class D
    audio_avg = 0.25 / 5.0 / 0.85
    logic = 0.060 + 0.020                      # RP2040 + flash, accelerometer, CH224K...
    five_peak = led_cap + dmd + audio_peak + logic
    five_avg = led_cap * 0.6 + dmd + audio_avg + logic
    buck_eff = 0.9
    coils_peak = 2 * 9.0 / COIL_R              # both flippers kicked at once
    coils_hold = 2 * 0.3 * 9.0 / COIL_R        # held at 30 % PWM
    p_peak = 9.0 * coils_peak + 5.0 * five_peak / buck_eff
    p_avg = 9.0 * coils_hold * 0.2 + 5.0 * five_avg / buck_eff
    return {"leds": leds, "led_full_A_5V": led_full, "led_capped_A_5V": led_cap, "five_volt_peak_A": five_peak,
            "coils_peak_A_9V": coils_peak, "peak_W": p_peak, "peak_A_9V": p_peak / 9.0, "typical_W": p_avg,
            "source": "USB-C PD 9 V, 2.22 A (20 W) minimum"}


if __name__ == "__main__":
    for name, fn in (("ball", ball), ("flipper @9 V", flipper), ("flipper @5 V (no PD)", lambda: flipper(5.0)),
                     ("plunger", plunger), ("power", power)):
        print(f"{name}:")
        for k, val in fn().items():
            print(f"  {k}: {val:.3f}" if isinstance(val, float) else f"  {k}: {val}")
